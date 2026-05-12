"""voxcpm2 TTS client."""
import re
import sys
import threading
import concurrent.futures
import gc
from pathlib import Path

import numpy as np

from app.core.config import settings
from app.core.exceptions import TTSError

_WHITESPACE_RE = re.compile(r"\s+")
_BRACKETED_TTS_NOTE_RE = re.compile(r"[\(\[\{<（［｛【「『][^)\]\}>）］｝】」』]*[\)\]\}>）］｝】」』]")
_ALLOWED_TTS_PUNCTUATION = {"?"}
_PEAK_CEILING = 0.95
_TARGET_RMS = 10 ** (-20 / 20)
_WAV_EPSILON = 1e-8
_TTS_WARMUP_TEXT = "옛날 옛적에 작은 마을에 용감한 소년이 살고 있었습니다. 어느 날 소년은 신비로운 숲 속에서 길을 잃고 말았습니다. 두려웠지만 포기하지 않고 앞으로 나아갔습니다."


def _is_tts_text_char(ch: str) -> bool:
    if ch.isspace() or ch in _ALLOWED_TTS_PUNCTUATION:
        return True
    cp = ord(ch)
    return (
        "0" <= ch <= "9"
        or "A" <= ch <= "Z"
        or "a" <= ch <= "z"
        or 0xAC00 <= cp <= 0xD7A3
        or 0x1100 <= cp <= 0x11FF
        or 0x3130 <= cp <= 0x318F
    )


def _clean_tts_text(text: str) -> str:
    text = _BRACKETED_TTS_NOTE_RE.sub(" ", text)
    cleaned = "".join(ch for ch in text if _is_tts_text_char(ch))
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def _join_clean_tts_text(*parts: str) -> str:
    cleaned_parts = [_clean_tts_text(part) for part in parts if part]
    return _WHITESPACE_RE.sub(" ", " ".join(part for part in cleaned_parts if part)).strip()


def _normalize_wav(wav) -> np.ndarray:
    audio = np.asarray(wav, dtype=np.float32)
    if audio.size == 0:
        return audio

    audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
    peak = float(np.max(np.abs(audio)))
    if peak < _WAV_EPSILON:
        return audio

    rms = float(np.sqrt(np.mean(np.square(audio))))
    gain = (_TARGET_RMS / rms) if rms > _WAV_EPSILON else 1.0
    if peak * gain > _PEAK_CEILING:
        gain = _PEAK_CEILING / peak

    audio = audio * gain
    return np.clip(audio, -_PEAK_CEILING, _PEAK_CEILING)


def _write_wav(output_path: Path, wav, sample_rate: int) -> None:
    try:
        import soundfile as sf
    except ImportError as e:
        raise TTSError(f"soundfile not installed: {e}") from e

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_path), _normalize_wav(wav), sample_rate)


# TTS는 torch.compile + CUDA graph가 스레드 TLS에 바인딩되므로
# 항상 동일한 단일 스레드에서 실행해야 한다.
_tts_executor: concurrent.futures.ThreadPoolExecutor | None = None
_tts_executor_lock = threading.Lock()
_tts_warmed_up = False
_tts_warmup_lock = threading.Lock()


def _format_bytes(value: int) -> str:
    return f"{value / (1024 ** 3):.2f}GB"


def _log_cuda_memory(label: str) -> None:
    if not settings.tts_vram_log_enabled:
        return
    try:
        import torch
        if not torch.cuda.is_available():
            return
        allocated = torch.cuda.memory_allocated()
        reserved = torch.cuda.memory_reserved()
        peak = torch.cuda.max_memory_allocated()
        print(
            f"[TTS VRAM] {label} "
            f"allocated={_format_bytes(allocated)} "
            f"reserved={_format_bytes(reserved)} "
            f"peak={_format_bytes(peak)}"
        )
    except Exception as e:
        print(f"[TTS VRAM] {label} unavailable: {e}")


def _cleanup_after_tts(label: str) -> None:
    gc.collect()
    if not settings.tts_cleanup_each_scene:
        _log_cuda_memory(f"{label} gc-only")
        return
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
            torch.cuda.reset_peak_memory_stats()
    except Exception as e:
        print(f"[TTS] post-scene cleanup failed: {e}")
    _log_cuda_memory(f"{label} cleanup")


def get_tts_executor() -> concurrent.futures.ThreadPoolExecutor:
    """항상 같은 1개 스레드를 재사용하는 executor 반환."""
    global _tts_executor
    with _tts_executor_lock:
        if _tts_executor is None:
            _tts_executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="tts-worker"
            )
    return _tts_executor


def reset_tts_executor() -> None:
    """hang된 TTS 스레드를 버리고 새 executor를 생성."""
    global _tts_executor, _tts_warmed_up
    old_executor = None
    with _tts_executor_lock:
        old_executor = _tts_executor
        _tts_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="tts-worker"
        )
        _tts_warmed_up = False
    if old_executor is not None:
        old_executor.shutdown(wait=False, cancel_futures=True)
    print("[TTS] executor reset (previous thread abandoned)")


def unload_model() -> None:
    """TTS 스레드 안에서 모델·CUDA를 정리한 뒤 executor를 종료."""
    import gc
    global _tts_executor, _tts_warmed_up

    def _do_unload_in_tts_thread() -> None:
        """TTS 스레드(= CUDA 컨텍스트 소유 스레드)에서 실행."""
        _log_cuda_memory("unload-before")

        try:
            ml = sys.modules.get('model_loader')
            if ml is not None and getattr(ml, '_model', None) is not None:
                model = ml._model

                # 1) 모델을 CPU로 이동 (VRAM에서 제거)
                try:
                    if hasattr(model, "to"):
                        model.to("cpu")
                except Exception as e:
                    print(f"[TTS] model.to('cpu') skipped: {e}")

                # 2) 모델 내부 서브모듈/텐서 명시적 삭제
                try:
                    for attr_name in list(vars(model).keys()):
                        try:
                            delattr(model, attr_name)
                        except Exception:
                            pass
                except Exception as e:
                    print(f"[TTS] submodule cleanup: {e}")

                ml._model = None
                del model
                print("[TTS] voxcpm2 model unloaded from VRAM")
        except Exception as e:
            print(f"[TTS] model unload: {e}")

        # 3) 철저한 CUDA 메모리 해제
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
                torch.cuda.reset_peak_memory_stats()
                print("[TTS] CUDA cache cleared")
        except Exception as e:
            print(f"[TTS] CUDA cleanup: {e}")

        # 4) 2차 gc (순환 참조 잔여분 정리)
        gc.collect()

        _log_cuda_memory("unload-after")

    with _tts_executor_lock:
        if _tts_executor is not None:
            future = _tts_executor.submit(_do_unload_in_tts_thread)
            try:
                future.result(timeout=60)
            except Exception as e:
                print(f"[TTS] in-thread unload failed: {e}")
            _tts_executor.shutdown(wait=True)
            _tts_executor = None
        _tts_warmed_up = False


def _patch_tqdm() -> None:
    """tqdm 구버전 API(_lock) 누락 문제를 monkey-patch로 해결."""
    import threading
    try:
        import tqdm as _tqdm_mod
        if not hasattr(_tqdm_mod.tqdm, '_lock'):
            _tqdm_mod.tqdm._lock = threading.RLock()
    except Exception:
        pass


def _get_model():
    """Load the voxcpm2 model, adding its directory to sys.path as needed."""
    vox_dir = settings.voxcpm2_dir
    if not vox_dir.exists():
        raise TTSError(f"voxcpm2TTS directory not found: {vox_dir}")

    if str(vox_dir) not in sys.path:
        sys.path.insert(0, str(vox_dir))

    _patch_tqdm()

    try:
        from model_loader import get_model  # type: ignore[import]
        return get_model()
    except ImportError as e:
        raise TTSError(f"Cannot import voxcpm2 model_loader: {e}") from e


def _run_model_generate(model, text: str, ref_wav: Path):
    return model.generate(
        text=text,
        reference_wav_path=str(ref_wav),
        cfg_value=settings.tts_cfg_value,
        inference_timesteps=settings.tts_timesteps,
    )


def _warm_up_model(model, ref_wav: Path) -> None:
    global _tts_warmed_up
    if _tts_warmed_up:
        return

    with _tts_warmup_lock:
        if _tts_warmed_up:
            return
        try:
            _run_model_generate(model, _TTS_WARMUP_TEXT, ref_wav)
            print("[TTS] voxcpm2 warmup done")
        except Exception as e:
            print(f"[TTS] warmup failed (continuing without warmup): {e}")
        _tts_warmed_up = True


def _generate_wav(text: str, emotion: str | None, ref_wav: Path):
    """Internal: run model.generate and return (wav_array, sample_rate)."""
    tts_text = _clean_tts_text(text)
    if not tts_text:
        raise TTSError("TTS text is empty after sanitization")

    model = _get_model()
    if settings.tts_warmup_enabled:
        _warm_up_model(model, ref_wav)

    print(f"[TTS] generate chars={len(tts_text)} preview={tts_text[:80]}")
    _log_cuda_memory("before-generate")
    try:
        wav = _run_model_generate(model, tts_text, ref_wav)
    except Exception as e:
        raise TTSError(f"voxcpm2 generation failed: {e}") from e
    _log_cuda_memory("after-generate")

    return wav, model.tts_model.sample_rate


def synthesize(
    text: str,
    emotion: str | None,
    output_path: Path,
    reference_wav: Path | None = None,
) -> None:
    """Synthesize a single text segment and save to output_path."""
    ref_wav = reference_wav or settings.tts_reference_wav
    if not ref_wav.exists():
        raise TTSError(f"TTS reference WAV not found: {ref_wav}")

    wav = None
    try:
        wav, sr = _generate_wav(text, emotion, ref_wav)
        _write_wav(output_path, wav, sr)
    finally:
        del wav
        _cleanup_after_tts(f"single {output_path.name}")


def synthesize_narration_dialogue(
    narration: str,
    dialogue: str,
    narration_emotion: str | None,
    dialogue_emotion: str | None,
    output_path: Path,
    reference_wav: Path | None = None,
) -> None:
    """Clean and join narration/dialogue, then synthesize one scene WAV."""
    ref_wav = reference_wav or settings.tts_reference_wav
    if not ref_wav.exists():
        raise TTSError(f"TTS reference WAV not found: {ref_wav}")

    scene_text = _join_clean_tts_text(narration, dialogue)
    print(
        "[TTS] scene text prepared "
        f"narration_chars={len(_clean_tts_text(narration))} "
        f"dialogue_chars={len(_clean_tts_text(dialogue))} "
        f"total_chars={len(scene_text)}"
    )
    wav = None
    try:
        wav, sr = _generate_wav(scene_text, emotion=None, ref_wav=ref_wav)
        _write_wav(output_path, wav, sr)
    finally:
        del wav
        _cleanup_after_tts(f"scene {output_path.name}")
