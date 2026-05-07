"""Worker server (5080): exposes LLM generation, ComfyUI image generation, and TTS via HTTP API."""
import asyncio
import gc
from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel

app = FastAPI(title="Story Worker", version="1.0.0")


class LLMRequest(BaseModel):
    era_ko: str
    place_ko: str
    characters_ko: str
    topic_ko: str


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
    story = await loop.run_in_executor(
        None, generate_story, req.era_ko, req.place_ko, req.characters_ko, req.topic_ko
    )
    return story.model_dump()


@app.post("/image/generate")
async def image_generate(req: ImageRequest):
    loop = asyncio.get_event_loop()
    img_bytes = await loop.run_in_executor(None, _generate_image_bytes, req.prompt, req.seed, req.stem)
    return Response(content=img_bytes, media_type="image/png")


@app.post("/tts/generate")
async def tts_generate(req: TTSRequest):
    loop = asyncio.get_event_loop()
    wav_bytes = await loop.run_in_executor(None, _generate_tts_bytes, req)
    return Response(content=wav_bytes, media_type="audio/wav")


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
    import numpy as np
    from pathlib import Path
    from app.clients.voxcpm2_client import get_tts_executor, synthesize, synthesize_narration_dialogue

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_dir = Path(tmpdir) / "audio"
        audio_dir.mkdir()
        output_path = audio_dir / f"scene_{req.scene_no:02d}.wav"

        if req.dialogue:
            synthesize_narration_dialogue(
                narration=req.narration,
                dialogue=req.dialogue,
                narration_emotion=req.narration_emotion,
                dialogue_emotion=req.dialogue_emotion,
                output_path=output_path,
            )
        else:
            synthesize(text=req.narration, emotion=req.narration_emotion, output_path=output_path)

        return output_path.read_bytes()


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
    try:
        import gc
        from app.clients.voxcpm2_client import unload_model
        unload_model()
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("[WORKER] TTS model unloaded from VRAM")
    except Exception as e:
        print(f"[CLEANUP] TTS unload: {e}")


def _do_cleanup() -> None:
    import subprocess, sys

    # llama-cli 프로세스 강제 종료 (혹시 남아있을 경우)
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/F", "/IM", "llama-cli.exe"], capture_output=True, check=False)
        except Exception as e:
            print(f"[CLEANUP] llama-cli kill: {e}")

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
