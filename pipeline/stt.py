"""
Speech-to-Text implementation using Whisper
"""
import os
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
            fp16=True  # GPU acceleration
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


def clear_stt_memory():
    """Clear STT model from GPU memory"""
    import gc
    import torch
    
    # Clear CUDA cache
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
    
    # Force garbage collection
    gc.collect()


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
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_data)
        tmp_path = Path(tmp.name)
    
    try:
        # Try to use soundfile + ffmpeg directly for conversion
        # If webm, we need to convert it first
        import subprocess
        import soundfile as sf
        
        # Create a temporary WAV file
        wav_path = tmp_path.with_suffix('.wav')
        
        # Use ffmpeg directly to convert to WAV
        ffmpeg_path = r"C:\ffmpeg\bin\ffmpeg.exe"
        if os.path.exists(ffmpeg_path):
            # Use ffmpeg to convert any audio format to WAV
            cmd = [
                ffmpeg_path,
                '-i', str(tmp_path),
                '-ar', '16000',  # 16kHz sample rate
                '-ac', '1',       # mono
                '-y',             # overwrite output
                str(wav_path)
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg conversion failed: {result.stderr.decode()}")
        else:
            # Fallback: try to read directly with soundfile
            try:
                audio_array, sample_rate = sf.read(str(tmp_path), dtype='float32')
                # Convert to mono if stereo
                if len(audio_array.shape) > 1:
                    audio_array = audio_array.mean(axis=1)
                # Resample to 16kHz if needed
                if sample_rate != 16000:
                    from scipy import signal
                    audio_array = signal.resample(audio_array, int(len(audio_array) * 16000 / sample_rate))
                # Write to WAV
                sf.write(str(wav_path), audio_array, 16000)
            except Exception as e:
                raise RuntimeError(f"Failed to convert audio (no ffmpeg): {e}")
        
        # Load Whisper model (on-demand, will be freed after use)
        import torch
        import gc
        import soundfile as sf
        
        # Load WAV with soundfile
        audio_array, sample_rate = sf.read(str(wav_path), dtype='float32')
        
        # Load model just before use
        model = whisper.load_model("medium")
        
        # Transcribe
        result = model.transcribe(
            audio_array,
            language=language.split("-")[0],
            fp16=True  # GPU acceleration
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
        
        # !!! CRITICAL: Free GPU memory immediately after use !!!
        del model
        del result
        del audio_array
        
        # Clear GPU cache
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        
        # Force garbage collection
        gc.collect()
        
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
