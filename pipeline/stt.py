"""
Speech-to-Text implementation using Whisper
"""
import tempfile
from pathlib import Path
from typing import Tuple
import whisper


class STTEngine:
    """STT engine using OpenAI Whisper"""
    
    def __init__(self, model_name: str = "medium"):
        """Initialize Whisper model
        
        Args:
            model_name: Whisper model size (tiny, base, small, medium, large)
        """
        self.model = whisper.load_model(model_name)
    
    def transcribe(self, audio_path: Path, language: str = "ko") -> Tuple[str, float]:
        """Transcribe audio file
        
        Args:
            audio_path: Path to audio file
            language: Language code (ko, en, etc.)
        
        Returns:
            Tuple of (transcribed_text, confidence_score)
        """
        import numpy as np
        try:
            import soundfile as sf
        except ImportError:
            raise RuntimeError("soundfile not installed. Install with: pip install soundfile")
        
        # Load audio using soundfile instead of ffmpeg
        try:
            audio, sample_rate = sf.read(str(audio_path), dtype='float32')
            
            # Convert to mono if stereo
            if len(audio.shape) > 1:
                audio = audio.mean(axis=1)
            
            # Resample to 16kHz if needed (Whisper requires 16kHz)
            if sample_rate != 16000:
                # Simple resampling (for better quality, use librosa)
                from scipy import signal
                audio = signal.resample(audio, int(len(audio) * 16000 / sample_rate))
        except Exception as e:
            raise RuntimeError(f"Failed to load audio file: {e}")
        
        result = self.model.transcribe(
            audio,
            language=language,
            fp16=False  # CPU compatibility
        )
        
        text = result["text"].strip()
        
        # Calculate confidence from segment probabilities
        segments = result.get("segments", [])
        if segments:
            avg_confidence = sum(seg.get("no_speech_prob", 0.5) for seg in segments) / len(segments)
            # Invert no_speech_prob to get confidence
            confidence = 1.0 - avg_confidence
        else:
            confidence = 0.5  # Default if no segments
        
        return text, max(0.0, min(1.0, confidence))


class FieldParser:
    """Parse and normalize field values"""
    
    @staticmethod
    def parse_era(text: str) -> str:
        """Parse era field"""
        # Simple normalization: strip and return
        return text.strip()
    
    @staticmethod
    def parse_place(text: str) -> str:
        """Parse place field"""
        return text.strip()
    
    @staticmethod
    def parse_characters(text: str) -> str:
        """Parse characters field"""
        return text.strip()
    
    @staticmethod
    def parse_topic(text: str) -> str:
        """Parse topic field"""
        return text.strip()


# Global STT engine instance (lazy loaded)
_stt_engine: STTEngine | None = None


def get_stt_engine() -> STTEngine:
    """Get or create STT engine singleton"""
    global _stt_engine
    if _stt_engine is None:
        _stt_engine = STTEngine(model_name="medium")
    return _stt_engine


async def process_field_stt(
    audio_data: bytes,
    field_type: str,
    language: str = "ko"
) -> Tuple[str, str, float]:
    """Process field STT request
    
    Args:
        audio_data: Audio file bytes
        field_type: Field type (era/place/characters/topic)
        language: Language code
    
    Returns:
        Tuple of (stt_text, parsed_value, confidence)
    """
    # Save audio to temp file first
    with tempfile.NamedTemporaryFile(suffix=".tmp", delete=False) as tmp:
        tmp.write(audio_data)
        tmp_path = Path(tmp.name)
    
    wav_path = None
    try:
        # Convert to WAV using pydub (supports webm, mp4, etc.)
        try:
            from pydub import AudioSegment
            
            # Load audio (pydub auto-detects format)
            audio = AudioSegment.from_file(str(tmp_path))
            
            # Convert to mono and set to 16kHz (Whisper requirements)
            audio = audio.set_channels(1).set_frame_rate(16000)
            
            # Export as WAV
            wav_path = tmp_path.with_suffix('.wav')
            audio.export(str(wav_path), format='wav')
            
        except Exception as e:
            raise RuntimeError(f"Failed to convert audio format: {e}")
        
        # Transcribe using Whisper
        engine = get_stt_engine()
        
        # Load WAV with soundfile
        import soundfile as sf
        audio_array, sample_rate = sf.read(str(wav_path), dtype='float32')
        
        # Transcribe
        result = engine.model.transcribe(
            audio_array,
            language=language.split("-")[0],
            fp16=False
        )
        
        stt_text = result["text"].strip()
        
        # Calculate confidence
        segments = result.get("segments", [])
        if segments:
            avg_confidence = sum(seg.get("no_speech_prob", 0.5) for seg in segments) / len(segments)
            confidence = 1.0 - avg_confidence
        else:
            confidence = 0.5
        
        confidence = max(0.0, min(1.0, confidence))
        
        # Parse based on field type
        parser_method = getattr(FieldParser, f"parse_{field_type}", FieldParser.parse_topic)
        parsed_value = parser_method(stt_text)
        
        return stt_text, parsed_value, confidence
        
    finally:
        # Clean up temp files
        try:
            tmp_path.unlink()
        except Exception:
            pass
        
        if wav_path and wav_path.exists():
            try:
                wav_path.unlink()
            except Exception:
                pass
