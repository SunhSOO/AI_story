"""
Speech-to-Text implementation using Whisper
"""
import tempfile
from pathlib import Path
from typing import Tuple
import whisper


class STTEngine:
    """STT engine using OpenAI Whisper"""
    
    def __init__(self, model_name: str = "base"):
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
        result = self.model.transcribe(
            str(audio_path),
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
        _stt_engine = STTEngine(model_name="base")
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
    # Save audio to temp file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_data)
        tmp_path = Path(tmp.name)
    
    try:
        # Transcribe
        engine = get_stt_engine()
        stt_text, confidence = engine.transcribe(tmp_path, language=language.split("-")[0])
        
        # Parse based on field type
        parser_method = getattr(FieldParser, f"parse_{field_type}", FieldParser.parse_topic)
        parsed_value = parser_method(stt_text)
        
        return stt_text, parsed_value, confidence
    finally:
        # Clean up temp file
        try:
            tmp_path.unlink()
        except Exception:
            pass
