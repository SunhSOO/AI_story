"""Main pipeline job: LLM(5080) → [5080 images ‖ 3080 TTS + 3080 images], with SSE events."""
import asyncio
import gc
import random
import subprocess
import sys
import time

from app.core.config import settings
from app.schemas.run_schema import RunStage, RunStatus
from app.services import storage_service
from app.services.event_service import event_bus
from app.services.run_service import RunRegistry, RunState

# ── 이미지 분배 정의 ──────────────────────────────────────────────────────────
# {scene_no: [img_idx, ...]}  img_idx는 1-based
_WORKER_IMAGES: dict[int, list[int]] = {
    1: [1, 2, 3],   # 5080: scene1 전체
    2: [1, 2, 3],
    3: [3],   # 5080: scene2 전체
    4: [2,3],   # 5080: scene3 
}
_LOCAL_IMAGES: dict[int, list[int]] = {
    3: [1, 2],
    4: [1]   # 3080: scene4 전체
}


async def _emit(run_state: RunState, extra: dict | None = None) -> None:
    data = {
        "run_id": run_state.run_id,
        "status": run_state.status.value,
        "stage": run_state.stage.value,
    }
    if extra:
        data.update(extra)
    storage_service.append_event(run_state.run_id, data)
    await event_bus.emit(run_state.run_id, data)


async def _cleanup_system(reason: str, worker=None) -> None:
    print(f"[CLEANUP] {reason}")
    loop = asyncio.get_event_loop()

    await asyncio.sleep(1.0)

    try:
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception as e:
        print(f"[CLEANUP] torch: {e}")

    try:
        from app.clients.comfyui_client import ComfyUIClient
        await loop.run_in_executor(None, ComfyUIClient().free_memory)
    except Exception as e:
        print(f"[CLEANUP] ComfyUI: {e}")

    try:
        from app.clients.voxcpm2_client import unload_model
        await loop.run_in_executor(None, unload_model)
    except Exception as e:
        print(f"[CLEANUP] voxcpm2: {e}")

    # 워커 GPU 메모리도 해제
    if worker is not None:
        await worker.cleanup()

    try:
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception as e:
        print(f"[CLEANUP] torch final: {e}")


async def run_pipeline(run_id: str, registry: RunRegistry) -> None:
    """Dual-machine pipeline:
      Stage 1: LLM on 5080 worker
      Stage 2 (parallel):
        Branch A (5080): Scene1,2 TTS → cover + scene1(1,2,3) + scene3(1,3) + scene4(1,3)
        Branch B (3080): cover TTS + Scene3,4 TTS → scene2(1,2,3) + scene3(2) + scene4(2)
    """
    from app.clients.worker_client import WorkerClient
    worker: WorkerClient | None = None

    run_state = registry.get(run_id)
    if not run_state:
        return

    run_dir = registry.get_run_dir(run_id)
    loop = asyncio.get_event_loop()

    try:
        run_state.status = RunStatus.RUNNING
        run_state.stage = RunStage.LLM
        await _emit(run_state)
        await _cleanup_system("pre-pipeline cleanup")

        # ── Stage 1: LLM on 5080 worker ──────────────────────────────────────
        print(f"\n[LLM] Requesting from worker: {settings.worker_url}")
        t0 = time.time()
        worker = WorkerClient(settings.worker_url)

        req = run_state.request
        story = await worker.generate_story(
            req.era_ko, req.place_ko, req.characters_ko, req.topic_ko
        )
        print(f"[LLM] Done in {time.time() - t0:.1f}s — '{story.title}'")

        run_state.set_story_title(story.title)
        run_state.init_scenes(settings.scene_count)
        for scene in story.scenes:
            run_state.update_scene_meta(
                scene.scene_no, scene.title, scene.narration,
                scene.dialogue, scene.narration_emotion, scene.dialogue_emotion,
            )
        storage_service.save_story(run_id, story)
        await _emit(run_state)

        # ── Stage 2: 병렬 실행 ────────────────────────────────────────────────
        run_state.stage = RunStage.PARALLEL
        await _emit(run_state)

        base_seed = random.randint(0, 9_999_999)

        # Branch A (5080 Worker): Scene 1,2 TTS → 표지+씬 이미지
        async def _worker_branch():
            # Scene 1, 2 TTS
            for scene_no in [1, 2]:
                scene = story.scenes[scene_no - 1]
                print(f"[WORKER] TTS scene {scene_no} on 5080...")
                wav_bytes = await worker.generate_tts(
                    scene_no=scene_no,
                    narration=scene.narration,
                    dialogue=scene.dialogue,
                    narration_emotion=scene.narration_emotion,
                    dialogue_emotion=scene.dialogue_emotion,
                )
                filename = f"scene_{scene_no:02d}.wav"
                audio_path = run_dir / "audio" / filename
                audio_path.parent.mkdir(parents=True, exist_ok=True)
                audio_path.write_bytes(wav_bytes)
                run_state.set_scene_audio(scene_no, filename)
                await _emit(run_state, {"scene_no": scene_no, "audio": filename})
                print(f"[WORKER] TTS scene {scene_no} done")

            # TTS 모델 언로드 → ComfyUI VRAM 확보
            await worker.unload_tts()
            print("[WORKER] TTS model unloaded")

            # 표지 이미지
            print("[WORKER] Generating cover image on 5080...")
            cover_bytes = await worker.generate_image(story.cover_prompt, base_seed, "cover")
            cover_path = run_dir / "images" / "cover.png"
            cover_path.parent.mkdir(parents=True, exist_ok=True)
            cover_path.write_bytes(cover_bytes)
            run_state.set_cover_image("cover.png")
            await _emit(run_state, {"cover_image": "cover.png"})
            print("[WORKER] cover done")

            # 씬별 이미지
            for scene_no, img_idxs in _WORKER_IMAGES.items():
                scene = story.scenes[scene_no - 1]
                for idx in img_idxs:
                    stem = f"scene_{scene_no:02d}_img_{idx:02d}"
                    filename = f"{stem}.png"
                    seed = base_seed + scene_no * 10 + idx
                    prompt = scene.image_prompts[idx - 1]
                    print(f"[WORKER] Generating scene {scene_no} img {idx} on 5080...")
                    img_bytes = await worker.generate_image(prompt, seed, stem)
                    img_path = run_dir / "images" / filename
                    img_path.write_bytes(img_bytes)
                    run_state.add_scene_image(scene_no, filename)
                    print(f"[WORKER] scene {scene_no} img {idx} done")
                await _emit(run_state, {"scene_no": scene_no})

            # 워커 ComfyUI VRAM 해제
            await worker.free_comfyui()
            print("[WORKER] ComfyUI VRAM freed")

        # Branch B (3080 Master): 표지 TTS + Scene 3,4 TTS → 로컬 ComfyUI 이미지
        async def _local_branch():
            run_state.stage = RunStage.TTS
            from app.services.tts_service import generate_cover_audio, generate_scene_audio
            from app.clients.voxcpm2_client import get_tts_executor, unload_model as unload_tts

            tts_executor = get_tts_executor()

            # 표지 TTS (제목)
            print("[LOCAL] TTS cover...")
            cover_audio = await loop.run_in_executor(
                tts_executor, generate_cover_audio, story.title, run_dir
            )
            run_state.set_cover_audio(cover_audio)
            await _emit(run_state, {"cover_audio": cover_audio})

            # Scene 3, 4 TTS
            for scene_no in [3, 4]:
                scene = story.scenes[scene_no - 1]
                print(f"[LOCAL] TTS scene {scene_no}...")
                filename = await loop.run_in_executor(
                    tts_executor, generate_scene_audio, scene, run_dir
                )
                run_state.set_scene_audio(scene_no, filename)
                await _emit(run_state, {"scene_no": scene_no, "audio": filename})

            # TTS 모델 언로드 → ComfyUI VRAM 확보
            await loop.run_in_executor(None, unload_tts)
            print("[LOCAL] TTS done, model unloaded")

            # 3080 로컬 ComfyUI 이미지
            run_state.stage = RunStage.IMAGE
            from app.services.image_service import generate_scene_image_at
            from app.clients.comfyui_client import ComfyUIClient

            local_client = ComfyUIClient()
            for scene_no, img_idxs in _LOCAL_IMAGES.items():
                scene = story.scenes[scene_no - 1]
                for idx in img_idxs:
                    print(f"[LOCAL] Generating scene {scene_no} img {idx} on 3080...")
                    filename = await loop.run_in_executor(
                        None, generate_scene_image_at,
                        scene, run_dir, base_seed, idx, None, local_client,
                    )
                    run_state.add_scene_image(scene_no, filename)
                    print(f"[LOCAL] scene {scene_no} img {idx} done")
                await _emit(run_state, {"scene_no": scene_no})

            await loop.run_in_executor(None, local_client.free_memory)

            # CUDA 캐시까지 명시적으로 반환
            def _local_cuda_cleanup():
                import gc, torch
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                print("[LOCAL] ComfyUI VRAM freed")

            await loop.run_in_executor(None, _local_cuda_cleanup)

        await asyncio.gather(_worker_branch(), _local_branch())

        # ── Done ──────────────────────────────────────────────────────────────
        run_state.status = RunStatus.DONE
        run_state.stage = RunStage.IMAGE
        await _emit(run_state)

    except Exception as exc:
        import traceback
        traceback.print_exc()
        run_state.status = RunStatus.FAILED
        run_state.error = str(exc)
        await _emit(run_state, {"error": str(exc)})

    finally:
        await _cleanup_system("post-pipeline cleanup", worker=worker)
