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
    2: [1, 2],
    3: [1, 2],
}
_LOCAL_IMAGES: dict[int, list[int]] = {
    1: [1, 2],
    4: [1, 2],
}

_MAX_SEED = 2_147_483_647


def _wav_duration(path: Path) -> float:
    """WAV 파일 재생 시간(초). 읽기 실패 시 0 반환."""
    try:
        with wave.open(str(path), "rb") as f:
            return f.getnframes() / f.getframerate()
    except Exception:
        return 0.0


def _wav_image_delay(path: Path) -> int:
    """WAV duration divided by the scene image count. Returns 1 on read failure."""
    duration = _wav_duration(path)
    if duration <= 0:
        return 1
    return max(1, round(duration / settings.images_per_scene))


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
        Branch A (worker): batch TTS (narration/dialogue split) with auto VRAM release, then assigned scene images
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

        # Branch A (5080 Worker): batch TTS (split) + assigned images
        async def _worker_branch():
            # ── TTS: 배치 요청으로 cover + 모든 scene 한번에 생성 (narration/dialogue 분할) ──
            tts_started_at = time.time()
            print("[WORKER] TTS batch on 5080 (cover + scenes, narration/dialogue split)...")

            # 배치 아이템 구성
            tts_items = [
                {
                    "scene_no": 0,
                    "narration": story.title,
                    "dialogue": "",
                    "narration_emotion": "",
                    "dialogue_emotion": "",
                },
            ]
            for scene in story.scenes:
                tts_items.append({
                    "scene_no": scene.scene_no,
                    "narration": scene.narration,
                    "dialogue": scene.dialogue,
                    "narration_emotion": "",
                    "dialogue_emotion": "",
                })

            # 배치 TTS 실행 — 실패해도 이미지 생성은 계속 진행
            tts_results: dict[str, bytes] = {}
            try:
                tts_results = await worker.generate_tts_batch(tts_items)
                print(f"[WORKER] TTS batch done in {time.time() - tts_started_at:.1f}s")
            except Exception as tts_exc:
                print(f"[WORKER] TTS batch failed (non-fatal, continuing to images): {tts_exc!r}")

            # ── Cover audio (0_0) ──
            cover_key = "0_0"
            if cover_key in tts_results:
                cover_audio = "cover.wav"
                cover_audio_path = run_dir / "audio" / cover_audio
                cover_audio_path.parent.mkdir(parents=True, exist_ok=True)
                cover_audio_path.write_bytes(tts_results[cover_key])
                run_state.set_cover_audio(cover_audio)
                await _emit(
                    run_state,
                    {
                        "cover_audio": cover_audio,
                        "cover_audio_url": f"/api/runs/{run_state.run_id}/audio/{cover_audio}",
                    },
                )
                print("[WORKER] TTS cover applied")

            # ── Scene audio (_0=narration, _1=dialogue) ──
            for scene in story.scenes:
                scene_no = scene.scene_no
                narr_key = f"{scene_no}_0"
                dial_key = f"{scene_no}_1"

                # narration audio (_0)
                if narr_key in tts_results:
                    narr_filename = f"scene_{scene_no:02d}_0.wav"
                    narr_path = run_dir / "audio" / narr_filename
                    narr_path.parent.mkdir(parents=True, exist_ok=True)
                    narr_path.write_bytes(tts_results[narr_key])
                    image_delay = _wav_image_delay(narr_path)
                    run_state.set_scene_audio(scene_no, narr_filename, image_delay)
                    await _emit(
                        run_state,
                        {
                            "scene_no": scene_no,
                            "audio": narr_filename,
                            "audio_url": f"/api/runs/{run_state.run_id}/audio/{narr_filename}",
                        },
                    )
                    print(f"[WORKER] TTS scene {scene_no} narration applied → {narr_filename}")

                # dialogue audio (_1)
                if dial_key in tts_results:
                    dial_filename = f"scene_{scene_no:02d}_1.wav"
                    dial_path = run_dir / "audio" / dial_filename
                    dial_path.parent.mkdir(parents=True, exist_ok=True)
                    dial_path.write_bytes(tts_results[dial_key])
                    run_state.set_scene_dialogue_audio(scene_no, dial_filename)
                    await _emit(
                        run_state,
                        {
                            "scene_no": scene_no,
                            "dialogue_audio": dial_filename,
                            "dialogue_audio_url": f"/api/runs/{run_state.run_id}/audio/{dial_filename}",
                        },
                    )
                    print(f"[WORKER] TTS scene {scene_no} dialogue applied → {dial_filename}")

            # ── 이미지 생성 (TTS VRAM은 이미 해제된 상태) ──
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
            cover_image = await loop.run_in_executor(
                None, generate_cover_image,
                story.cover_prompt, run_dir, base_seed, None, local_client,
            )
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
                    filename = await loop.run_in_executor(
                        None, generate_scene_image_at,
                        scene, run_dir, base_seed, idx, None, local_client,
                    )
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

        branch_results = await asyncio.gather(
            _worker_branch(), _local_branch(), return_exceptions=True
        )
        branch_errors = [r for r in branch_results if isinstance(r, BaseException)]
        if branch_errors:
            raise branch_errors[0]

        await _cleanup_system("generation-complete VRAM cleanup", worker=worker)
        cleanup_done = True

        # ── Done ──────────────────────────────────────────────────────────────
        run_state.status = RunStatus.DONE
        run_state.stage = RunStage.IMAGE
        await _emit(run_state)

    except Exception as exc:
        import traceback
        traceback.print_exc()
        error = f"{type(exc).__name__}: {exc!r}"
        run_state.status = RunStatus.FAILED
        run_state.error = error
        await _emit(run_state, {"error": error})

    finally:
        if not cleanup_done:
            await _cleanup_system("post-pipeline cleanup", worker=worker)
