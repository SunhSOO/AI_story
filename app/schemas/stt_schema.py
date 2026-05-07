"""STT API request/response schemas."""
from enum import Enum
from pydantic import BaseModel, Field


class FieldType(str, Enum):
    ERA = "era"
    PLACE = "place"
    CHARACTERS = "characters"
    TOPIC = "topic"


class FieldSTTResponse(BaseModel):
    stt_text: str = Field(..., description="Whisper 원문 인식 결과")
    parsed_value: str = Field(..., description="정규화된 값")
    confidence: float = Field(..., ge=0.0, le=1.0)
