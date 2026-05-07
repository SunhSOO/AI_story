"""STT service: delegates to whisper_client and normalizes field values."""
from app.clients.whisper_client import transcribe
from app.schemas.stt_schema import FieldType


def _parse_field(text: str, field_type: FieldType) -> str:
    return text.strip()


async def process_stt(
    audio_bytes: bytes,
    field_type: FieldType,
    language: str = "ko",
) -> tuple[str, str, float]:
    """Run Whisper and return (stt_text, parsed_value, confidence)."""
    import asyncio

    loop = asyncio.get_event_loop()
    stt_text, confidence = await loop.run_in_executor(None, transcribe, audio_bytes, language)
    parsed_value = _parse_field(stt_text, field_type)
    return stt_text, parsed_value, confidence
