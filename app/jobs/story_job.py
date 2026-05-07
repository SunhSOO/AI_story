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
    3: [1, 3],      # 5080: scene3 img1, img3
    4: [1, 3],      # 5080: scene4 img1, img3
}
_LOCAL_IMAGES: dict[int, list[int]] = {
    2: [1, 2, 3],   # 3080: scene2 전체 (TTS 완료 후)
    3: [2],         # 3080: scene3 img2
    4: [2],         # 3080: scene4 img2
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


async def _cleanup_system(reason: str) -> None:
    print(f"[CLEANUP] {reason}")
    loop = asyncio.get_event_loop()

    try:
        if sys.platform == "win32":
            await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["taskkill", "/F", "/IM", "llama-cli.exe"], capture_output=True, check=False
                ),
            )
    except Exception as e:
        print(f"[CLEANUP] llama-cli kill: {e}")

    await asyncio.sleep(1.5)

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
        Branch A (5080): cover + scene1(1,2,3) + scene3(1,3) + scene4(1,3)
        Branch B (3080): TTS(all 4 scenes) → scene2(1,2,3) + scene3(2) + scene4(2)
    """
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
        from app.clients.worker_client import WorkerClient
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

        # Branch A: 5080 워커 이미지 (cover + _WORKER_IMAGES)
        async def _worker_branch():
            # 표지
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

        # Branch B: 3080 로컬 — TTS 먼저, 그 후 ComfyUI 이미지
        async def _local_branch():
            # TTS (4개 전 장면)
            run_state.stage = RunStage.TTS
            from app.services.tts_service import generate_scene_audio
            from app.clients.voxcpm2_client import get_tts_executor, unload_model as unload_tts

            tts_executor = get_tts_executor()
            for scene in story.scenes:
                print(f"[LOCAL] TTS scene {scene.scene_no}...")
                filename = await loop.run_in_executor(
                    tts_executor, generate_scene_audio, scene, run_dir
                )
                run_state.set_scene_audio(scene.scene_no, filename)
                await _emit(run_state, {"scene_no": scene.scene_no, "audio": filename})

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
        await _cleanup_system("post-pipeline cleanup")
