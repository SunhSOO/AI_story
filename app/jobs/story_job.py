"""Main pipeline job: worker LLM/images plus master TTS, with SSE events."""
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

# ── 워커 이미지 생성 정의 ─────────────────────────────────────────────────────
# {scene_no: [img_idx, ...]}  img_idx는 1-based
_WORKER_IMAGES: dict[int, list[int]] = {
    1: [1, 2],
    2: [1, 2],
    3: [1, 2],
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


async def _cleanup_system(
    reason: str,
    worker=None,
    unload_local_comfyui: bool = False,
    unload_worker_comfyui: bool | None = None,
) -> None:
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
        await loop.run_in_executor(
            None,
            ComfyUIClient().free_memory,
            unload_local_comfyui or settings.comfyui_unload_models_after_run,
        )
    except Exception as e:
        print(f"[CLEANUP] ComfyUI: {e}")

    # 워커 GPU 메모리도 해제
    if worker is not None:
        if unload_worker_comfyui is None:
            unload_worker_comfyui = settings.comfyui_unload_models_after_run
        await worker.cleanup(unload_comfyui_models=unload_worker_comfyui)

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
        Branch A (master): cover + scene TTS (narration/dialogue split)
        Branch B (worker): cover + all scene images
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
        await _cleanup_system("pre-pipeline cleanup", unload_local_comfyui=True)

        # ── Stage 1: LLM on 5080 worker ──────────────────────────────────────
        story_seed = random.randint(1, _MAX_SEED)
        print(f"[SEED] story seed: {story_seed}")
        print(f"\n[LLM] Requesting from worker: {settings.worker_url}")
        t0 = time.time()
        worker = WorkerClient(settings.worker_url)
        await worker.cleanup(unload_comfyui_models=False)

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

        # Branch A (Master): cover + per-scene TTS (split)
        async def _master_tts_branch():
            from app.clients.voxcpm2_client import get_tts_executor, synthesize, unload_model

            tts_started_at = time.time()
            print("[MASTER] TTS on master (cover + scenes, narration/dialogue split)...")

            def _synthesize_to_file(text: str, output_path: Path) -> None:
                synthesize(text=text, emotion=None, output_path=output_path)

            async def _generate_tts_file(
                scene_no: int,
                text: str,
                output_filename: str,
            ) -> Path | None:
                t0 = time.time()
                output_path = run_dir / "audio" / output_filename
                output_path.parent.mkdir(parents=True, exist_ok=True)
                print(
                    f"[MASTER TTS] -> {output_filename} "
                    f"(scene={scene_no} text_len={len(text)})"
                )
                try:
                    await loop.run_in_executor(
                        get_tts_executor(),
                        _synthesize_to_file,
                        text,
                        output_path,
                    )
                except Exception as exc:
                    print(
                        f"[MASTER TTS] {output_filename} failed after "
                        f"{time.time() - t0:.1f}s: {exc!r}"
                    )
                    raise
                print(
                    f"[MASTER TTS] <- {output_filename} bytes={output_path.stat().st_size} "
                    f"elapsed={time.time() - t0:.1f}s"
                )
                return output_path

            try:
                # ── Cover audio ──
                tts_items = [
                    {
                        "kind": "cover",
                        "scene_no": 0,
                        "text": story.title,
                        "filename": "cover.wav",
                    }
                ]

                for scene in story.scenes:
                    scene_no = scene.scene_no
                    tts_items.append(
                        {
                            "kind": "narration",
                            "scene_no": scene_no,
                            "text": scene.narration,
                            "filename": f"scene_{scene_no:02d}_0.wav",
                        }
                    )
                    if scene.dialogue:
                        tts_items.append(
                            {
                                "kind": "dialogue",
                                "scene_no": scene_no,
                                "text": scene.dialogue,
                                "filename": f"scene_{scene_no:02d}_1.wav",
                            }
                        )

                print(f"[MASTER TTS BATCH] start count={len(tts_items)}")
                for pos, item in enumerate(tts_items, start=1):
                    scene_no = int(item["scene_no"])
                    filename = str(item["filename"])
                    kind = str(item["kind"])
                    print(f"[MASTER TTS BATCH] generating {pos}/{len(tts_items)} {filename}")
                    audio_path = await _generate_tts_file(
                        scene_no=scene_no,
                        text=str(item["text"]),
                        output_filename=filename,
                    )
                    if audio_path is None:
                        continue

                    audio_delay = max(0, round(_wav_duration(audio_path)))
                    if kind == "cover":
                        run_state.set_cover_audio(filename, audio_delay=audio_delay)
                        await _emit(
                            run_state,
                            {
                                "cover_audio": filename,
                                "cover_audio_url": f"/api/runs/{run_state.run_id}/audio/{filename}",
                            },
                        )
                        print("[MASTER] TTS cover applied")
                    elif kind == "narration":
                        image_delay = _wav_image_delay(audio_path)
                        run_state.set_scene_audio(scene_no, filename, image_delay, audio_delay=audio_delay)
                        await _emit(
                            run_state,
                            {
                                "scene_no": scene_no,
                                "audio": filename,
                                "audio_url": f"/api/runs/{run_state.run_id}/audio/{filename}",
                            },
                        )
                        print(f"[MASTER] TTS scene {scene_no} narration applied -> {filename}")
                    elif kind == "dialogue":
                        run_state.set_scene_dialogue_audio(scene_no, filename, audio_delay=audio_delay)
                        await _emit(
                            run_state,
                            {
                                "scene_no": scene_no,
                                "dialogue_audio": filename,
                                "dialogue_audio_url": f"/api/runs/{run_state.run_id}/audio/{filename}",
                            },
                        )
                        print(f"[MASTER] TTS scene {scene_no} dialogue applied -> {filename}")
            finally:
                await loop.run_in_executor(None, unload_model)
                print(f"[MASTER] TTS unload done (all local TTS in {time.time() - tts_started_at:.1f}s)")

        # Branch B (5080 Worker): cover image plus all scene images
        async def _worker_image_branch():
            print("[WORKER] Generating all images on 5080 via sequential batch...")
            try:
                cover_filename = "cover.png"
                image_items = [
                    {
                        "prompt": story.cover_prompt,
                        "seed": base_seed,
                        "stem": "cover",
                    }
                ]
                scene_outputs: list[tuple[int, int, str, str]] = []

                for scene_no, img_idxs in _WORKER_IMAGES.items():
                    scene = story.scenes[scene_no - 1]
                    for idx in img_idxs:
                        stem = f"scene_{scene_no:02d}_img_{idx:02d}"
                        filename = f"{stem}.png"
                        image_items.append(
                            {
                                "prompt": scene.image_prompts[idx - 1],
                                "seed": base_seed,
                                "stem": stem,
                            }
                        )
                        scene_outputs.append((scene_no, idx, stem, filename))

                t0 = time.time()
                scene_output_by_stem = {
                    stem: (scene_no, idx, filename)
                    for scene_no, idx, stem, filename in scene_outputs
                }
                emitted_scene_no = None
                print(f"[WORKER] Streaming image batch from 5080 count={len(image_items)}")
                async for stem, img_bytes in worker.stream_image_batch(image_items):
                    if stem == "cover":
                        cover_path = run_dir / "images" / cover_filename
                        cover_path.parent.mkdir(parents=True, exist_ok=True)
                        cover_path.write_bytes(img_bytes)
                        run_state.set_cover_image(cover_filename)
                        await _emit(
                            run_state,
                            {
                                "cover_image": cover_filename,
                                "cover_image_url": f"/api/runs/{run_state.run_id}/images/{cover_filename}",
                            },
                        )
                        print("[WORKER] cover saved from stream")
                        continue

                    scene_no, idx, filename = scene_output_by_stem[stem]
                    if emitted_scene_no is not None and emitted_scene_no != scene_no:
                        await _emit(run_state, {"scene_no": emitted_scene_no})

                    img_path = run_dir / "images" / filename
                    img_path.parent.mkdir(parents=True, exist_ok=True)
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
                    print(f"[WORKER] scene {scene_no} img {idx} saved from stream")
                    emitted_scene_no = scene_no

                if emitted_scene_no is not None:
                    await _emit(run_state, {"scene_no": emitted_scene_no})
                print(f"[WORKER] Image stream finished in {time.time() - t0:.1f}s")
            finally:
                # 워커 이미지가 끝나거나 실패하면 ComfyUI 모델까지 내려 VRAM을 반환한다.
                await worker.free_comfyui(unload_models=True)
                print("[WORKER] ComfyUI VRAM freed after image branch")

        branch_results = await asyncio.gather(
            _master_tts_branch(), _worker_image_branch(), return_exceptions=True
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
            await _cleanup_system(
                "post-pipeline cleanup",
                worker=worker,
                unload_local_comfyui=True,
                unload_worker_comfyui=True,
            )
