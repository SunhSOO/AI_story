"""Worker server (5080): exposes LLM generation, ComfyUI image generation, and TTS via HTTP API."""
import asyncio
import gc
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

app = FastAPI(title="Story Worker", version="1.0.0")


class LLMRequest(BaseModel):
    era_ko: str
    place_ko: str
    characters_ko: str
    topic_ko: str
    seed: int | None = None


class ImageRequest(BaseModel):
    prompt: str
    seed: int
    stem: str


class TTSRequest(BaseModel):
    scene_no: int
    narration: str
    dialogue: str
    narration_emotion: str
    dialogue_emotion: str


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/llm/generate")
async def llm_generate(req: LLMRequest):
    loop = asyncio.get_event_loop()
    from app.services.story_service import generate_story
    try:
        story = await loop.run_in_executor(
            None, generate_story, req.era_ko, req.place_ko, req.characters_ko, req.topic_ko, req.seed
        )
        return story.model_dump()
    finally:
        await loop.run_in_executor(None, _cleanup_llm)


@app.post("/image/generate")
async def image_generate(req: ImageRequest):
    loop = asyncio.get_event_loop()
    img_bytes = await loop.run_in_executor(None, _generate_image_bytes, req.prompt, req.seed, req.stem)
    return Response(content=img_bytes, media_type="image/png")


_TTS_SCENE_TIMEOUT = 660


async def _maybe_unload_tts_after_request(scene_no: int) -> None:
    from app.core.config import settings

    if not settings.tts_unload_after_each_request:
        return

    loop = asyncio.get_event_loop()
    print(f"[WORKER TTS] unload after scene={scene_no} start")
    await loop.run_in_executor(None, _unload_tts)
    print(f"[WORKER TTS] unload after scene={scene_no} done")


@app.post("/tts/generate")
async def tts_generate(req: TTSRequest):
    loop = asyncio.get_event_loop()
    from app.clients.voxcpm2_client import get_tts_executor, reset_tts_executor
    try:
        wav_bytes = await asyncio.wait_for(
            loop.run_in_executor(get_tts_executor(), _generate_tts_bytes, req),
            timeout=_TTS_SCENE_TIMEOUT,
        )
        await _maybe_unload_tts_after_request(req.scene_no)
        print(f"[WORKER TTS] response scene={req.scene_no} bytes={len(wav_bytes)}")
        return Response(content=wav_bytes, media_type="audio/wav")
    except asyncio.TimeoutError:
        reset_tts_executor()
        try:
            await _maybe_unload_tts_after_request(req.scene_no)
        except Exception as cleanup_exc:
            print(f"[WORKER TTS] unload after timeout failed: {cleanup_exc}")
        raise HTTPException(
            status_code=500,
            detail=f"TTS scene={req.scene_no} timed out after {_TTS_SCENE_TIMEOUT}s",
        )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        try:
            await _maybe_unload_tts_after_request(req.scene_no)
        except Exception as cleanup_exc:
            print(f"[WORKER TTS] unload after failure failed: {cleanup_exc}")
        raise HTTPException(
            status_code=500,
            detail=f"TTS scene={req.scene_no} failed: {type(exc).__name__}: {exc}",
        ) from exc


@app.post("/tts/unload")
async def tts_unload():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _unload_tts)
    return {"status": "ok"}


@app.post("/comfyui/free")
async def comfyui_free():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _free_comfyui)
    return {"status": "ok"}


@app.post("/cleanup")
async def cleanup():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _do_cleanup)
    return {"status": "ok"}


def _generate_image_bytes(prompt: str, seed: int, stem: str) -> bytes:
    from app.clients.comfyui_client import ComfyUIClient, generate_image_bytes
    from app.core.config import settings
    client = ComfyUIClient()
    return generate_image_bytes(
        prompt=prompt,
        seed=seed,
        stem=stem,
        workflow_path=settings.workflow_path,
        client=client,
    )


def _generate_tts_bytes(req: TTSRequest) -> bytes:
    import tempfile
    from pathlib import Path
    from app.clients.voxcpm2_client import synthesize, synthesize_narration_dialogue

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_dir = Path(tmpdir) / "audio"
        audio_dir.mkdir()
        output_path = audio_dir / f"scene_{req.scene_no:02d}.wav"

        print(
            f"[WORKER TTS] start scene={req.scene_no} "
            f"narration_len={len(req.narration)} dialogue_len={len(req.dialogue)}"
        )
        if req.dialogue:
            synthesize_narration_dialogue(
                narration=req.narration,
                dialogue=req.dialogue,
                narration_emotion=None,
                dialogue_emotion=None,
                output_path=output_path,
            )
        else:
            synthesize(text=req.narration, emotion=None, output_path=output_path)

        wav_bytes = output_path.read_bytes()
        print(f"[WORKER TTS] done scene={req.scene_no} bytes={len(wav_bytes)}")
        return wav_bytes


def _free_comfyui() -> None:
    try:
        import gc
        from app.clients.comfyui_client import ComfyUIClient
        ComfyUIClient().free_memory()
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("[WORKER] ComfyUI VRAM freed")
    except Exception as e:
        print(f"[WORKER] ComfyUI free: {e}")


def _unload_tts() -> None:
    import gc
    from app.clients.voxcpm2_client import unload_model

    unload_model()
    gc.collect()

    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
            torch.cuda.reset_peak_memory_stats()
    except Exception as e:
        raise RuntimeError(f"TTS CUDA cleanup failed: {e}") from e

    print("[WORKER] TTS model unloaded from VRAM")


def _cleanup_llm() -> None:
    import subprocess, sys

    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/F", "/IM", "llama-cli.exe"], capture_output=True, check=False)
        except Exception as e:
            print(f"[CLEANUP] llama-cli kill: {e}")

    try:
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("[WORKER] LLM VRAM/cache cleanup done")
    except Exception as e:
        print(f"[CLEANUP] LLM torch: {e}")


def _do_cleanup() -> None:
    _cleanup_llm()

    _unload_tts()

    try:
        from app.clients.comfyui_client import ComfyUIClient
        ComfyUIClient().free_memory()
    except Exception as e:
        print(f"[CLEANUP] ComfyUI free: {e}")

    try:
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception as e:
        print(f"[CLEANUP] torch: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.workers.worker_server:app", host="0.0.0.0", port=8001, reload=False)
