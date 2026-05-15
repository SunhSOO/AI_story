"""Whisper STT client: converts audio bytes → text."""
import gc
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import STTError


def _convert_to_wav(src: Path, dst: Path) -> None:
    ffmpeg = settings.ffmpeg_path if os.path.exists(settings.ffmpeg_path) else shutil.which("ffmpeg")
    if ffmpeg:
        result = subprocess.run(
            [ffmpeg, "-i", str(src), "-ar", "16000", "-ac", "1", "-y", str(dst)],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise STTError(f"ffmpeg conversion failed: {result.stderr.decode(errors='replace')}")
        return

    try:
        import soundfile as sf
        from scipy import signal

        audio, sr = sf.read(str(src), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != 16000:
            audio = signal.resample(audio, int(len(audio) * 16000 / sr))
        sf.write(str(dst), audio, 16000)
    except Exception as e:
        raise STTError(f"Audio conversion failed (no ffmpeg): {e}") from e


def transcribe(audio_bytes: bytes, language: str = "ko") -> tuple[str, float]:
    """Run Whisper on raw audio bytes.

    Returns:
        (text, confidence) tuple.
    """
    try:
        import whisper
        import soundfile as sf
    except ImportError as e:
        raise STTError(f"Missing dependency: {e}") from e

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = Path(tmp.name)

    wav_path = tmp_path.with_suffix(".wav")
    try:
        _convert_to_wav(tmp_path, wav_path)

        audio_array, _ = sf.read(str(wav_path), dtype="float32")

        model = whisper.load_model(settings.whisper_model, device="cpu")
        result = model.transcribe(audio_array, language=language.split("-")[0], fp16=False)

        text = result["text"].strip()
        segments = result.get("segments", [])
        if segments:
            avg_no_speech = sum(s.get("no_speech_prob", 0.5) for s in segments) / len(segments)
            confidence = max(0.0, min(1.0, 1.0 - avg_no_speech))
        else:
            confidence = 0.5

        del model, result, audio_array
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

        return text, confidence

    finally:
        for p in (tmp_path, wav_path):
            try:
                p.unlink()
            except Exception:
                pass
