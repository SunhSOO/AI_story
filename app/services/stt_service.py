"""STT service: delegates transcription to the worker and normalizes field values."""
from app.clients.worker_client import WorkerClient
from app.core.config import settings
from app.schemas.stt_schema import FieldType


def _parse_field(text: str, field_type: FieldType) -> str:
    return text.strip()


async def process_stt(
    audio_bytes: bytes,
    field_type: FieldType,
    language: str = "ko",
) -> tuple[str, str, float]:
    """Run Whisper on the worker and return (stt_text, parsed_value, confidence)."""
    worker = WorkerClient(settings.worker_url)
    stt_text, confidence = await worker.transcribe_stt(audio_bytes, language)
    parsed_value = _parse_field(stt_text, field_type)
    return stt_text, parsed_value, confidence
