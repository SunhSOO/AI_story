"""Worker server (5080): exposes LLM generation, ComfyUI image generation, and TTS via HTTP API."""
import asyncio
import base64
import gc
import time
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


class TTSBatchRequest(BaseModel):
    items: list[TTSRequest]


class ComfyUIFreeRequest(BaseModel):
    unload_models: bool = False


class CleanupRequest(BaseModel):
    unload_comfyui_models: bool = False


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


_TTS_SCENE_TIMEOUT = 600
_TTS_BATCH_TIMEOUT_PER_ITEM = 180


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
    print(
        f"[WORKER TTS] /tts/generate received scene={req.scene_no} "
        f"narration_len={len(req.narration)} dialogue_len={len(req.dialogue)}"
    )
    loop = asyncio.get_event_loop()
    from app.clients.voxcpm2_client import get_tts_executor, reset_tts_executor

    for attempt in range(2):
        try:
            wav_bytes = await asyncio.wait_for(
                loop.run_in_executor(get_tts_executor(), _generate_tts_bytes, req),
                timeout=_TTS_SCENE_TIMEOUT,
            )
            await _maybe_unload_tts_after_request(req.scene_no)
            print(f"[WORKER TTS] response scene={req.scene_no} bytes={len(wav_bytes)}")
            return Response(content=wav_bytes, media_type="audio/wav")
        except AssertionError as exc:
            # torch.compile / CUDA graph TLS 충돌 — executor 리셋 후 1회 재시도
            print(
                f"[WORKER TTS] AssertionError scene={req.scene_no} attempt={attempt}: {exc!r}"
                + (" → resetting executor and retrying" if attempt == 0 else " → giving up")
            )
            reset_tts_executor()
            if attempt == 0:
                continue
            raise HTTPException(
                status_code=500,
                detail=f"TTS scene={req.scene_no} AssertionError after retry: {exc}",
            ) from exc
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


@app.post("/tts/batch")
async def tts_batch_generate(req: TTSBatchRequest):
    """여러 TTS를 한 번에 생성 (narration/dialogue 분할).

    반환 형식: {"scene_no_0": base64_wav, "scene_no_1": base64_wav, ...}
      - scene_no_0: narration WAV
      - scene_no_1: dialogue WAV (dialogue가 비어있으면 키 없음)

    완료 후 자동으로 모델을 언로드하여 VRAM 해제.
    """
    loop = asyncio.get_event_loop()
    from app.clients.voxcpm2_client import get_tts_executor, reset_tts_executor

    total_timeout = _TTS_BATCH_TIMEOUT_PER_ITEM * len(req.items)
    batch_start = time.time()
    print(f"[WORKER TTS BATCH] start items={len(req.items)} timeout={total_timeout}s")

    results = None
    for attempt in range(2):
        try:
            results = await asyncio.wait_for(
                loop.run_in_executor(
                    get_tts_executor(),
                    _generate_tts_bytes_batch_split,
                    req.items,
                ),
                timeout=total_timeout,
            )
            break
        except AssertionError as exc:
            # torch.compile / CUDA graph TLS 충돌 — executor 리셋 후 1회 재시도
            print(
                f"[WORKER TTS BATCH] AssertionError attempt={attempt}: {exc!r}"
                + (" → resetting executor and retrying" if attempt == 0 else " → giving up")
            )
            reset_tts_executor()
            if attempt == 0:
                continue
            try:
                await loop.run_in_executor(None, _unload_tts)
            except Exception as e:
                print(f"[WORKER TTS BATCH] unload after AssertionError failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"TTS batch AssertionError after retry: {exc}",
            ) from exc
        except asyncio.TimeoutError:
            reset_tts_executor()
            try:
                await loop.run_in_executor(None, _unload_tts)
            except Exception as e:
                print(f"[WORKER TTS BATCH] unload after timeout failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"TTS batch timed out after {total_timeout}s",
            )
        except Exception as exc:
            import traceback
            traceback.print_exc()
            try:
                await loop.run_in_executor(None, _unload_tts)
            except Exception as e:
                print(f"[WORKER TTS BATCH] unload after failure failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"TTS batch failed: {type(exc).__name__}: {exc}",
            ) from exc

    # 성공 시 TTS 모델 언로드 → VRAM 해제
    unload_start = time.time()
    await loop.run_in_executor(None, _unload_tts)
    print(
        f"[WORKER TTS BATCH] done items={len(req.items)} "
        f"total={time.time() - batch_start:.1f}s "
        f"unload={time.time() - unload_start:.1f}s"
    )

    # base64 인코딩으로 반환 (키: "scene_no_0", "scene_no_1")
    encoded = {}
    for key, wav_bytes in results.items():
        encoded[key] = base64.b64encode(wav_bytes).decode("ascii")
    return encoded


@app.post("/tts/unload")
async def tts_unload():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _unload_tts)
    return {"status": "ok"}


@app.post("/comfyui/free")
async def comfyui_free(req: ComfyUIFreeRequest | None = None):
    loop = asyncio.get_event_loop()
    unload_models = req.unload_models if req is not None else False
    await loop.run_in_executor(None, _free_comfyui, unload_models)
    return {"status": "ok"}


@app.post("/cleanup")
async def cleanup(req: CleanupRequest | None = None):
    loop = asyncio.get_event_loop()
    unload_comfyui_models = req.unload_comfyui_models if req is not None else False
    await loop.run_in_executor(None, _do_cleanup, unload_comfyui_models)
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


def _generate_tts_bytes_batch_split(items: list) -> dict:
    """TTS 전용 스레드에서 narration/dialogue를 분할 생성.

    반환 형식: {"scene_no_0": bytes, "scene_no_1": bytes}
      - _0: narration WAV
      - _1: dialogue WAV (dialogue가 비어있으면 생략)
    """
    import tempfile
    from pathlib import Path
    from app.clients.voxcpm2_client import synthesize, synthesize_split

    results: dict[str, bytes] = {}

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_dir = Path(tmpdir) / "audio"
        audio_dir.mkdir()

        for req in items:
            scene_start = time.time()

            print(
                f"[WORKER TTS BATCH] generating scene={req.scene_no} "
                f"narration_len={len(req.narration)} dialogue_len={len(req.dialogue)}"
            )

            if req.dialogue:
                # narration + dialogue 분할 생성
                narr_path = audio_dir / f"scene_{req.scene_no:02d}_0.wav"
                dial_path = audio_dir / f"scene_{req.scene_no:02d}_1.wav"

                narr_ok, dial_ok = synthesize_split(
                    narration=req.narration,
                    dialogue=req.dialogue,
                    narration_emotion=None,
                    dialogue_emotion=None,
                    narration_output_path=narr_path,
                    dialogue_output_path=dial_path,
                )

                if narr_ok:
                    results[f"{req.scene_no}_0"] = narr_path.read_bytes()
                if dial_ok:
                    results[f"{req.scene_no}_1"] = dial_path.read_bytes()
            else:
                # narration만 있는 경우 (cover 등)
                narr_path = audio_dir / f"scene_{req.scene_no:02d}_0.wav"
                synthesize(text=req.narration, emotion=None, output_path=narr_path)
                results[f"{req.scene_no}_0"] = narr_path.read_bytes()

            total_bytes = sum(
                len(results[k]) for k in results
                if k.startswith(f"{req.scene_no}_")
            )
            print(
                f"[WORKER TTS BATCH] scene={req.scene_no} done "
                f"bytes={total_bytes} elapsed={time.time() - scene_start:.1f}s"
            )

    return results


def _free_comfyui(unload_models: bool = False) -> None:
    try:
        import gc
        from app.clients.comfyui_client import ComfyUIClient
        ComfyUIClient().free_memory(unload_models=unload_models)
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print(f"[WORKER] ComfyUI VRAM freed unload_models={unload_models}")
    except Exception as e:
        print(f"[WORKER] ComfyUI free: {e}")


def _unload_tts() -> None:
    import gc
    from app.clients.voxcpm2_client import unload_model

    # CUDA cleanup은 unload_model() 내부에서 TTS 스레드 안에 실행됨
    unload_model()
    gc.collect()
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


def _do_cleanup(unload_comfyui_models: bool = False) -> None:
    _cleanup_llm()

    _unload_tts()

    try:
        from app.clients.comfyui_client import ComfyUIClient
        ComfyUIClient().free_memory(unload_models=unload_comfyui_models)
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
