"""voxcpm2 TTS client."""
import re
import sys
import threading
import concurrent.futures
from pathlib import Path

import numpy as np

from app.core.config import settings
from app.core.exceptions import TTSError

_WHITESPACE_RE = re.compile(r"\s+")
_BRACKETED_TTS_NOTE_RE = re.compile(r"[\(\[\{<（［｛【「『][^)\]\}>）］｝】」』]*[\)\]\}>）］｝】」』]")
_ALLOWED_TTS_PUNCTUATION = {"!", "?", ","}
_PEAK_CEILING = 0.95
_TARGET_RMS = 10 ** (-20 / 20)
_WAV_EPSILON = 1e-8
_TTS_WARMUP_TEXT = "안녕하세요"


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


def get_tts_executor() -> concurrent.futures.ThreadPoolExecutor:
    """항상 같은 1개 스레드를 재사용하는 executor 반환."""
    global _tts_executor
    with _tts_executor_lock:
        if _tts_executor is None:
            _tts_executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="tts-worker"
            )
    return _tts_executor


def unload_model() -> None:
    """TTS executor를 종료하고 VRAM에서 voxcpm2 모델을 해제."""
    import gc
    global _tts_executor, _tts_warmed_up

    # executor 종료 — wait=True로 스레드가 완전히 종료될 때까지 대기
    with _tts_executor_lock:
        if _tts_executor is not None:
            _tts_executor.shutdown(wait=True)
            _tts_executor = None
        _tts_warmed_up = False

    # model_loader 싱글톤(_model) 해제
    try:
        ml = sys.modules.get('model_loader')
        if ml is not None and getattr(ml, '_model', None) is not None:
            del ml._model
            ml._model = None
            print("[TTS] voxcpm2 model unloaded from VRAM")
    except Exception as e:
        print(f"[TTS] model unload: {e}")

    # CUDA 메모리 강제 반환 — del만으로는 allocator 캐시가 남음
    try:
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            print("[TTS] CUDA cache cleared")
    except Exception as e:
        print(f"[TTS] CUDA cleanup: {e}")


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
        except Exception as e:
            raise TTSError(f"voxcpm2 warmup failed: {e}") from e
        _tts_warmed_up = True
        print("[TTS] voxcpm2 warmup done")


def _generate_wav(text: str, emotion: str | None, ref_wav: Path):
    """Internal: run model.generate and return (wav_array, sample_rate)."""
    tts_text = _clean_tts_text(text)

    model = _get_model()
    _warm_up_model(model, ref_wav)
    try:
        wav = _run_model_generate(model, tts_text, ref_wav)
    except Exception as e:
        raise TTSError(f"voxcpm2 generation failed: {e}") from e

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

    wav, sr = _generate_wav(text, emotion, ref_wav)
    _write_wav(output_path, wav, sr)


def synthesize_narration_dialogue(
    narration: str,
    dialogue: str,
    narration_emotion: str | None,
    dialogue_emotion: str | None,
    output_path: Path,
    reference_wav: Path | None = None,
) -> None:
    """Synthesize narration + dialogue in one pass and save."""
    ref_wav = reference_wav or settings.tts_reference_wav
    if not ref_wav.exists():
        raise TTSError(f"TTS reference WAV not found: {ref_wav}")

    combined_text = f"{narration}, {dialogue}" if dialogue else narration
    wav, sr = _generate_wav(combined_text, emotion=None, ref_wav=ref_wav)
    _write_wav(output_path, wav, sr)
