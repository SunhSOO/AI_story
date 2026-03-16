"""
TTS generation wrapper using existing run_tts.py logic
"""
from dataclasses import dataclass
import sys
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class SpeechSegment:
    text: str
    voice: str


def _load_tts_runtime():
    """Load Supertonic ONNX runtime helpers."""
    base_dir = Path(__file__).parent.parent

    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))

    from run_tts import default_onnx_dir, default_voice_style_path, supertonic_root

    py_dir = supertonic_root() / "py"
    if str(py_dir) not in sys.path:
        sys.path.insert(0, str(py_dir))

    try:
        import numpy as np
        import soundfile as sf
        from helper import load_text_to_speech, load_voice_style
    except ImportError as exc:
        raise RuntimeError("Missing ONNX dependencies for TTS") from exc

    onnx_dir = default_onnx_dir()
    if not onnx_dir.exists():
        raise FileNotFoundError(f"ONNX directory not found: {onnx_dir}")

    text_to_speech = load_text_to_speech(str(onnx_dir), use_gpu=False)
    return {
        "default_voice_style_path": default_voice_style_path,
        "load_voice_style": load_voice_style,
        "numpy": np,
        "soundfile": sf,
        "text_to_speech": text_to_speech,
    }


def _load_voice_styles(voice_names: Iterable[str], runtime: dict) -> dict[str, object]:
    styles: dict[str, object] = {}
    default_voice_style_path = runtime["default_voice_style_path"]
    load_voice_style = runtime["load_voice_style"]

    for voice_name in sorted({voice.strip().upper() for voice in voice_names if voice.strip()}):
        voice_style_path = default_voice_style_path(voice_name)
        if not voice_style_path.exists():
            raise FileNotFoundError(f"Voice style not found: {voice_style_path}")
        styles[voice_name] = load_voice_style([str(voice_style_path)], verbose=False)

    return styles


def generate_tts_segments(
    segments: Iterable[SpeechSegment],
    output_path: Path,
    lang: str = "ko",
    speed: float = 1.05,
    pause_ms: int = 250,
):
    """Generate TTS audio by stitching together multiple voice segments."""
    prepared_segments = [
        SpeechSegment(text=segment.text.strip(), voice=segment.voice.strip().upper())
        for segment in segments
        if segment.text.strip()
    ]
    if not prepared_segments:
        raise ValueError("No non-empty TTS segments to synthesize")

    runtime = _load_tts_runtime()
    np = runtime["numpy"]
    sf = runtime["soundfile"]
    text_to_speech = runtime["text_to_speech"]
    styles = _load_voice_styles((segment.voice for segment in prepared_segments), runtime)

    audio_chunks = []
    sample_rate = text_to_speech.sample_rate
    pause_chunk = None
    if pause_ms > 0:
        pause_chunk = np.zeros(int(sample_rate * (pause_ms / 1000.0)), dtype=np.float32)

    for index, segment in enumerate(prepared_segments):
        wav, duration = text_to_speech(
            segment.text,
            lang,
            styles[segment.voice],
            total_step=10,
            speed=speed,
        )
        trim_len = int(sample_rate * duration[0].item())
        audio_chunks.append(np.asarray(wav[0, :trim_len], dtype=np.float32))

        if pause_chunk is not None and index < len(prepared_segments) - 1:
            audio_chunks.append(pause_chunk.copy())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_path), np.concatenate(audio_chunks), sample_rate)


def generate_tts(text: str, output_path: Path, voice: str = "F2", lang: str = "ko", speed: float = 1.05):
    """Generate TTS audio using Supertonic
    
    Args:
        text: Text to synthesize
        output_path: Output WAV file path
        voice: Voice name (M1-M5, F1-F5)
        lang: Language code
        speed: Speech speed multiplier
    """
    generate_tts_segments(
        [SpeechSegment(text=text, voice=voice)],
        output_path,
        lang=lang,
        speed=speed,
        pause_ms=0,
    )


def _coerce_tts_config(tts_config: dict | None) -> dict:
    config = dict(tts_config or {})
    character_voices = {
        str(character).strip(): str(voice).strip().upper()
        for character, voice in dict(config.get("character_voices") or {}).items()
        if str(character).strip() and str(voice).strip()
    }
    return {
        "narrator_voice": str(config.get("narrator_voice", "F2")).strip().upper() or "F2",
        "dialogue_voice": str(config.get("dialogue_voice", "F5")).strip().upper() or "F5",
        "character_voices": character_voices,
        "lang": str(config.get("lang", "ko")).strip().lower() or "ko",
        "speed": float(config.get("speed", 1.05)),
        "segment_pause_ms": int(config.get("segment_pause_ms", 250)),
    }


def generate_page_audio(
    text: str,
    dialogues: list[dict] | None,
    page_num: int,
    output_dir: Path,
    tts_config: dict | None = None,
):
    """Generate audio for a single page
    
    Args:
        text: Narration text content for the page
        dialogues: Structured dialogue lines for the page
        page_num: Page number (0-4)
        output_dir: Output directory for audio files
        tts_config: Voice configuration
    
    Returns:
        Path to generated audio file
    """
    config = _coerce_tts_config(tts_config)
    segments: list[SpeechSegment] = []

    if text.strip():
        segments.append(SpeechSegment(text=text.strip(), voice=config["narrator_voice"]))

    for dialogue in dialogues or []:
        dialogue_text = str(dialogue.get("text", "")).strip()
        character = str(dialogue.get("character", "")).strip()
        if not dialogue_text:
            continue

        resolved_voice = (
            str(dialogue.get("voice", "")).strip().upper()
            or config["character_voices"].get(character)
            or config["dialogue_voice"]
        )
        segments.append(SpeechSegment(text=dialogue_text, voice=resolved_voice))

    filename = f"page_{page_num}.wav"
    output_path = output_dir / filename

    generate_tts_segments(
        segments,
        output_path,
        lang=config["lang"],
        speed=config["speed"],
        pause_ms=config["segment_pause_ms"],
    )

    return filename

