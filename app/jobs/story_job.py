"""Main pipeline job: master-only LLM, TTS, and image generation with SSE events."""
import asyncio
import gc
import os
import random
import subprocess
import time
import wave
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.schemas.run_schema import RunStage, RunStatus
from app.services import storage_service
from app.services.event_service import event_bus
from app.services.run_service import RunRegistry, RunState

_SCENE_IMAGE_INDEXES: dict[int, list[int]] = {
    1: [1, 2],
    2: [1, 2],
    3: [1, 2],
    4: [1, 2],
}

_MAX_SEED = 2_147_483_647


def _wav_duration(path: Path) -> float:
    """Return WAV duration in seconds, or 0 on read failure."""
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


def _clear_python_cuda_cache(label: str) -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            print(f"[CLEANUP] CUDA cache cleared: {label}")
    except Exception as e:
        print(f"[CLEANUP] torch: {e}")
    gc.collect()


def _cleanup_llama_processes() -> None:
    """Kill any leftover llama-cli process so GGUF VRAM is released."""
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/F", "/IM", "llama-cli.exe"],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            result = subprocess.run(
                ["pkill", "-f", "llama-cli"],
                capture_output=True,
                text=True,
                check=False,
            )
        if result.returncode == 0:
            print("[CLEANUP] leftover llama-cli process killed")
    except Exception as e:
        print(f"[CLEANUP] llama-cli kill skipped: {e}")


def _free_local_comfyui(unload_models: bool) -> None:
    try:
        from app.clients.comfyui_client import ComfyUIClient

        ok = ComfyUIClient().free_memory(unload_models=unload_models)
        print(f"[CLEANUP] ComfyUI free_memory ok={ok} unload_models={unload_models}")
    except Exception as e:
        print(f"[CLEANUP] ComfyUI: {e}")


async def _cleanup_system(
    reason: str,
    *,
    unload_local_comfyui: bool = False,
    kill_llm: bool = False,
) -> None:
    print(f"[CLEANUP] {reason}")
    loop = asyncio.get_running_loop()

    await asyncio.sleep(0.5)

    if kill_llm:
        await loop.run_in_executor(None, _cleanup_llama_processes)

    await loop.run_in_executor(None, _clear_python_cuda_cache, reason)

    if unload_local_comfyui:
        await loop.run_in_executor(None, _free_local_comfyui, True)
        await loop.run_in_executor(None, _clear_python_cuda_cache, f"{reason} final")


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


async def run_pipeline(run_id: str, registry: RunRegistry) -> None:
    """Run the full story pipeline on the master server only.

    LLM, TTS, and ComfyUI image generation are intentionally sequential so each
    model can release VRAM before the next GPU-heavy stage starts.
    """
    run_state = registry.get(run_id)
    if not run_state:
        return

    run_dir = registry.get_run_dir(run_id)
    loop = asyncio.get_running_loop()
    cleanup_done = False

    try:
        run_state.status = RunStatus.RUNNING
        run_state.stage = RunStage.LLM
        await _emit(run_state)

        await _cleanup_system(
            "pre-LLM VRAM cleanup",
            unload_local_comfyui=True,
            kill_llm=True,
        )

        story_seed = random.randint(1, _MAX_SEED)
        print(f"[SEED] story seed: {story_seed}")
        print("[LLM] Generating on master server")
        t0 = time.time()

        req = run_state.request
        from app.services.story_service import generate_story

        try:
            story = await loop.run_in_executor(
                None,
                generate_story,
                req.era_ko,
                req.place_ko,
                req.characters_ko,
                req.topic_ko,
                story_seed,
            )
        finally:
            await _cleanup_system("post-LLM VRAM cleanup", kill_llm=True)

        print(f"[LLM] Done in {time.time() - t0:.1f}s - '{story.title}'")

        run_state.set_story_title(story.title)
        run_state.init_scenes(settings.scene_count)
        for scene in story.scenes:
            run_state.update_scene_meta(
                scene.scene_no,
                scene.narration,
                scene.dialogue,
                scene.dialogue_emotion,
            )
        storage_service.save_story(run_id, story, seed=story_seed)
        await _emit(run_state)

        run_state.stage = RunStage.TTS
        await _emit(run_state)

        base_seed = story_seed

        async def _master_tts_stage() -> None:
            from app.clients.voxcpm2_client import get_tts_executor, synthesize, unload_model

            tts_started_at = time.time()
            print("[MASTER TTS] start cover + scenes")

            def _synthesize_to_file(text: str, output_path: Path) -> None:
                synthesize(text=text, emotion=None, output_path=output_path)

            async def _generate_tts_file(
                scene_no: int,
                text: str,
                output_filename: str,
            ) -> Path:
                file_started_at = time.time()
                output_path = run_dir / "audio" / output_filename
                output_path.parent.mkdir(parents=True, exist_ok=True)
                print(
                    f"[MASTER TTS] -> {output_filename} "
                    f"(scene={scene_no} text_len={len(text)})"
                )
                await loop.run_in_executor(
                    get_tts_executor(),
                    _synthesize_to_file,
                    text,
                    output_path,
                )
                print(
                    f"[MASTER TTS] <- {output_filename} bytes={output_path.stat().st_size} "
                    f"elapsed={time.time() - file_started_at:.1f}s"
                )
                return output_path

            try:
                tts_items: list[dict[str, Any]] = [
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
                        print("[MASTER TTS] cover applied")
                    elif kind == "narration":
                        image_delay = _wav_image_delay(audio_path)
                        run_state.set_scene_audio(
                            scene_no,
                            filename,
                            image_delay,
                            audio_delay=audio_delay,
                        )
                        await _emit(
                            run_state,
                            {
                                "scene_no": scene_no,
                                "audio": filename,
                                "audio_url": f"/api/runs/{run_state.run_id}/audio/{filename}",
                            },
                        )
                        print(f"[MASTER TTS] scene {scene_no} narration applied -> {filename}")
                    elif kind == "dialogue":
                        run_state.set_scene_dialogue_audio(
                            scene_no,
                            filename,
                            audio_delay=audio_delay,
                        )
                        await _emit(
                            run_state,
                            {
                                "scene_no": scene_no,
                                "dialogue_audio": filename,
                                "dialogue_audio_url": f"/api/runs/{run_state.run_id}/audio/{filename}",
                            },
                        )
                        print(f"[MASTER TTS] scene {scene_no} dialogue applied -> {filename}")
            finally:
                await loop.run_in_executor(None, unload_model)
                await loop.run_in_executor(None, _clear_python_cuda_cache, "post-TTS VRAM cleanup")
                print(f"[MASTER TTS] VRAM freed after TTS in {time.time() - tts_started_at:.1f}s")

        async def _master_image_stage() -> None:
            from app.clients.comfyui_client import ComfyUIClient, generate_image_bytes

            print("[MASTER IMAGE] start cover + scene images")
            image_started_at = time.time()
            client = ComfyUIClient()

            image_items: list[dict[str, Any]] = [
                {
                    "prompt": story.cover_prompt,
                    "seed": base_seed,
                    "stem": "cover",
                }
            ]
            scene_outputs: list[tuple[int, int, str, str]] = []

            for scene_no, img_idxs in _SCENE_IMAGE_INDEXES.items():
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

            scene_output_by_stem = {
                stem: (scene_no, idx, filename)
                for scene_no, idx, stem, filename in scene_outputs
            }
            emitted_scene_no = None

            try:
                print(f"[MASTER IMAGE BATCH] sequential count={len(image_items)}")
                for pos, item in enumerate(image_items, start=1):
                    stem = str(item["stem"])
                    print(f"[MASTER IMAGE BATCH] generating {pos}/{len(image_items)} {stem}")
                    img_bytes = await loop.run_in_executor(
                        None,
                        generate_image_bytes,
                        str(item["prompt"]),
                        int(item["seed"]),
                        stem,
                        settings.workflow_path,
                        client,
                    )

                    if stem == "cover":
                        cover_filename = "cover.png"
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
                        print("[MASTER IMAGE] cover saved")
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
                    print(f"[MASTER IMAGE] scene {scene_no} img {idx} saved")
                    emitted_scene_no = scene_no

                if emitted_scene_no is not None:
                    await _emit(run_state, {"scene_no": emitted_scene_no})
                print(f"[MASTER IMAGE] 9 images finished in {time.time() - image_started_at:.1f}s")
            finally:
                await _cleanup_system(
                    "post-image batch VRAM cleanup",
                    unload_local_comfyui=True,
                )
                print("[MASTER IMAGE] ComfyUI VRAM freed after image batch")

        await _master_tts_stage()
        run_state.stage = RunStage.IMAGE
        await _emit(run_state)
        await _master_image_stage()

        await _cleanup_system(
            "generation-complete VRAM cleanup",
            unload_local_comfyui=True,
            kill_llm=True,
        )
        cleanup_done = True

        run_state.status = RunStatus.DONE
        run_state.stage = RunStage.IMAGE
        await _emit(run_state)

    except Exception as exc:
        import traceback

        traceback.print_exc()
        error = f"{type(exc).__name__}: {exc!r}"
        run_state.status = RunStatus.FAILED
        run_state.error = error
        run_state.restart_required = True
        await _cleanup_system(
            "failure cleanup before fresh input",
            unload_local_comfyui=True,
            kill_llm=True,
        )
        cleanup_done = True
        await _emit(
            run_state,
            {
                "error": error,
                "restart_required": True,
                "cleanup_done": True,
            },
        )

    finally:
        if not cleanup_done:
            await _cleanup_system(
                "post-pipeline cleanup",
                unload_local_comfyui=True,
                kill_llm=True,
            )
