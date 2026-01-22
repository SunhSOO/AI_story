"""
TTS generation wrapper using existing run_tts.py logic
"""
import sys
from pathlib import Path
from types import SimpleNamespace


def generate_tts(text: str, output_path: Path, voice: str = "M2", lang: str = "ko", speed: float = 1.05):
    """Generate TTS audio using Supertonic
    
    Args:
        text: Text to synthesize
        output_path: Output WAV file path
        voice: Voice name (M1-M5, F1-F5)
        lang: Language code
        speed: Speech speed multiplier
    """
    # Import from run_tts module
    base_dir = Path(__file__).parent.parent
    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))
    
    from run_tts import supertonic_root, default_voice_style_path, default_onnx_dir
    
    # Add supertonic py directory to path
    py_dir = supertonic_root() / "py"
    if str(py_dir) not in sys.path:
        sys.path.insert(0, str(py_dir))
    
    try:
        import soundfile as sf
        from helper import load_text_to_speech, load_voice_style, timer
    except ImportError as exc:
        raise RuntimeError("Missing ONNX dependencies for TTS") from exc
    
    onnx_dir = default_onnx_dir()
    voice_style_path = default_voice_style_path(voice)
    
    if not onnx_dir.exists():
        raise FileNotFoundError(f"ONNX directory not found: {onnx_dir}")
    if not voice_style_path.exists():
        raise FileNotFoundError(f"Voice style not found: {voice_style_path}")
    
    # Load TTS model
    text_to_speech = load_text_to_speech(str(onnx_dir), use_gpu=False)
    style = load_voice_style([str(voice_style_path)], verbose=False)
    
    # Generate speech
    wav, duration = text_to_speech(text, lang, style, total_step=10, speed=speed)
    
    # Save to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    trim_len = int(text_to_speech.sample_rate * duration[0].item())
    sf.write(str(output_path), wav[0, :trim_len], text_to_speech.sample_rate)


def generate_page_audio(text: str, page_num: int, output_dir: Path, voice: str = "M2", lang: str = "ko"):
    """Generate audio for a single page
    
    Args:
        text: Text content for the page
        page_num: Page number (0-4)
        output_dir: Output directory for audio files
        voice: Voice name
        lang: Language code
    
    Returns:
        Path to generated audio file
    """
    filename = f"page_{page_num}.wav"
    output_path = output_dir / filename
    
    generate_tts(text, output_path, voice=voice, lang=lang)
    
    return filename
