"""Main pipeline job: worker LLM/TTS plus split image generation, with SSE events."""
import asyncio
import gc
import random
import time
import wave
from pathlib import Path

from app.core.config import settings
from app.schemas.run_schema import RunStage, RunStatus
from app.services import storage_service
from app.services.event_service import event_bus
from app.services.run_service import RunRegistry, RunState

# ── 이미지 분배 정의 ──────────────────────────────────────────────────────────
# {scene_no: [img_idx, ...]}  img_idx는 1-based
_WORKER_IMAGES: dict[int, list[int]] = {
    2: [1, 3],
    3: [2],  
    4: [1, 3],   
}
_LOCAL_IMAGES: dict[int, list[int]] = {
    1: [1, 2, 3],
    2: [2],
    3: [1, 3],
    4: [2]  
}

_MAX_SEED = 2_147_483_647


def _wav_image_delay(path: Path) -> int:
    """WAV 재생시간을 3으로 나눠 반올림한 이미지 딜레이(초) 반환. 읽기 실패 시 1."""
    try:
        with wave.open(str(path), "rb") as f:
            duration = f.getnframes() / f.getframerate()
        return max(1, round(duration / 3))
    except Exception:
        return 1


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
        Branch A (worker): cover TTS, all scene TTS, assigned scene images
        Branch B (local): cover image, assigned scene images
    """
    from app.clients.worker_client import WorkerClient
    worker: WorkerClient | None = None

    run_state = registry.get(run_id)
    if not run_state:
        return

    run_dir = registry.get_run_dir(run_id)
    loop = asyncio.get_event_loop()
    cleanup_done = False

    try:
        run_state.status = RunStatus.RUNNING
        run_state.stage = RunStage.LLM
        await _emit(run_state)
        await _cleanup_system("pre-pipeline cleanup")

        # ── Stage 1: LLM on 5080 worker ──────────────────────────────────────
        story_seed = random.randint(1, _MAX_SEED)
        print(f"[SEED] story seed: {story_seed}")
        print(f"\n[LLM] Requesting from worker: {settings.worker_url}")
        t0 = time.time()
        worker = WorkerClient(settings.worker_url)

        req = run_state.request
        story = await worker.generate_story(
            req.era_ko, req.place_ko, req.characters_ko, req.topic_ko, seed=story_seed
        )
        print(f"[LLM] Done in {time.time() - t0:.1f}s — '{story.title}'")

        run_state.set_story_title(story.title)
        run_state.init_scenes(settings.scene_count)
        for scene in story.scenes:
            run_state.update_scene_meta(
                scene.scene_no, scene.narration,
                scene.dialogue, scene.dialogue_emotion,
            )
        storage_service.save_story(run_id, story, seed=story_seed)
        await _emit(run_state)

        # ── Stage 2: 병렬 실행 ────────────────────────────────────────────────
        run_state.stage = RunStage.PARALLEL
        await _emit(run_state)

        base_seed = story_seed

        # Branch A (5080 Worker): all TTS plus assigned images
        async def _worker_branch():
            print("[WORKER] TTS cover on 5080...")
            cover_audio_bytes = await worker.generate_cover_tts(story.title)
            cover_audio = "cover.wav"
            cover_audio_path = run_dir / "audio" / cover_audio
            cover_audio_path.parent.mkdir(parents=True, exist_ok=True)
            cover_audio_path.write_bytes(cover_audio_bytes)
            run_state.set_cover_audio(cover_audio)
            await _emit(
                run_state,
                {
                    "cover_audio": cover_audio,
                    "cover_audio_url": f"/api/runs/{run_state.run_id}/audio/{cover_audio}",
                },
            )
            print("[WORKER] TTS cover done")

            for scene in story.scenes:
                scene_no = scene.scene_no
                print(f"[WORKER] TTS scene {scene_no} on 5080...")
                wav_bytes = await worker.generate_tts(
                    scene_no=scene_no,
                    narration=scene.narration,
                    dialogue=scene.dialogue,
                    narration_emotion="",
                    dialogue_emotion="",
                )
                filename = f"scene_{scene_no:02d}.wav"
                audio_path = run_dir / "audio" / filename
                audio_path.parent.mkdir(parents=True, exist_ok=True)
                audio_path.write_bytes(wav_bytes)
                image_delay = _wav_image_delay(audio_path)
                run_state.set_scene_audio(scene_no, filename, image_delay)
                await _emit(
                    run_state,
                    {
                        "scene_no": scene_no,
                        "audio": filename,
                        "audio_url": f"/api/runs/{run_state.run_id}/audio/{filename}",
                    },
                )
                print(f"[WORKER] TTS scene {scene_no} done")

            # TTS 모델 언로드 → ComfyUI VRAM 확보
            await worker.unload_tts()
            print("[WORKER] TTS model unloaded")

            # 씬별 이미지
            for scene_no, img_idxs in _WORKER_IMAGES.items():
                scene = story.scenes[scene_no - 1]
                for idx in img_idxs:
                    stem = f"scene_{scene_no:02d}_img_{idx:02d}"
                    filename = f"{stem}.png"
                    seed = base_seed
                    prompt = scene.image_prompts[idx - 1]
                    print(f"[WORKER] Generating scene {scene_no} img {idx} on 5080...")
                    img_bytes = await worker.generate_image(prompt, seed, stem)
                    img_path = run_dir / "images" / filename
                    img_path.write_bytes(img_bytes)
                    run_state.add_scene_image(scene_no, filename)
                    await _emit(
                        run_state,
                        {
                            "scene_no": scene_no,
                            "image": filename,
                            "image_url": f"/api/runs/{run_state.run_id}/images/{filename}",
                        },
                    )
                    print(f"[WORKER] scene {scene_no} img {idx} done")
                await _emit(run_state, {"scene_no": scene_no})

            # 워커 ComfyUI VRAM 해제
            await worker.free_comfyui()
            print("[WORKER] ComfyUI VRAM freed")

        # Branch B (3080 Master): cover image plus local ComfyUI images
        async def _local_branch():
            from app.services.image_service import generate_cover_image, generate_scene_image_at
            from app.clients.comfyui_client import ComfyUIClient

            local_client = ComfyUIClient()

            print("[LOCAL] Generating cover image on 3080...")
            try:
                cover_image = await loop.run_in_executor(
                    None, generate_cover_image,
                    story.cover_prompt, run_dir, base_seed, None, local_client,
                )
            finally:
                await loop.run_in_executor(None, local_client.free_memory, False)
            run_state.set_cover_image(cover_image)
            await _emit(
                run_state,
                {
                    "cover_image": cover_image,
                    "cover_image_url": f"/api/runs/{run_state.run_id}/images/{cover_image}",
                },
            )
            print("[LOCAL] cover done")

            for scene_no, img_idxs in _LOCAL_IMAGES.items():
                scene = story.scenes[scene_no - 1]
                for idx in img_idxs:
                    print(f"[LOCAL] Generating scene {scene_no} img {idx} on 3080...")
                    try:
                        filename = await loop.run_in_executor(
                            None, generate_scene_image_at,
                            scene, run_dir, base_seed, idx, None, local_client,
                        )
                    finally:
                        await loop.run_in_executor(None, local_client.free_memory, False)
                    run_state.add_scene_image(scene_no, filename)
                    await _emit(
                        run_state,
                        {
                            "scene_no": scene_no,
                            "image": filename,
                            "image_url": f"/api/runs/{run_state.run_id}/images/{filename}",
                        },
                    )
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

        await _cleanup_system("generation-complete VRAM cleanup", worker=worker)
        cleanup_done = True

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
        if not cleanup_done:
            await _cleanup_system("post-pipeline cleanup", worker=worker)
