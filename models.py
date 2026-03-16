"""
Pydantic models for API contracts following External API Specification v2.1
"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


SUPPORTED_TTS_LANGS = {"en", "ko", "es", "pt", "fr"}
VOICE_NAME_PATTERN = r"^(?:M|F)[1-5]$"


def _normalize_voice_name(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("voice must be a string")

    normalized = value.strip().upper()
    if not normalized:
        raise ValueError("voice must not be empty")

    return normalized


class FieldType(str, Enum):
    """Field types for STT requests"""
    ERA = "era"
    PLACE = "place"
    CHARACTERS = "characters"
    TOPIC = "topic"


class Status(str, Enum):
    """Run status values"""
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


class Stage(str, Enum):
    """Pipeline stages"""
    LLM = "LLM"
    COVER = "COVER"
    PANEL_1 = "PANEL_1"
    PANEL_2 = "PANEL_2"
    PANEL_3 = "PANEL_3"
    PANEL_4 = "PANEL_4"
    TTS = "TTS"


class FieldSTTResponse(BaseModel):
    """Response from field STT endpoint"""
    stt_text: str = Field(..., description="Raw transcription text")
    parsed_value: str = Field(..., description="Normalized/parsed value")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0-1")


class DialogueLine(BaseModel):
    """Structured dialogue information for a story page"""
    character: str = Field(..., description="Speaking character name")
    text: str = Field(..., description="Dialogue text in Korean")
    voice: str = Field(default="", description="Resolved TTS voice for this dialogue line")


class TTSConfig(BaseModel):
    """Voice configuration used when generating page audio"""
    narrator_voice: str = Field(
        default="F2",
        pattern=VOICE_NAME_PATTERN,
        description="Voice used for narration segments"
    )
    dialogue_voice: str = Field(
        default="F5",
        pattern=VOICE_NAME_PATTERN,
        description="Default voice used for dialogue segments"
    )
    character_voices: dict[str, str] = Field(
        default_factory=dict,
        description="Optional per-character voice overrides"
    )
    lang: str = Field(default="ko", description="TTS language code")
    speed: float = Field(default=1.05, gt=0.0, le=2.0, description="Speech speed multiplier")
    segment_pause_ms: int = Field(
        default=250,
        ge=0,
        le=5000,
        description="Pause inserted between narration/dialogue segments in milliseconds"
    )

    @field_validator("narrator_voice", "dialogue_voice", mode="before")
    @classmethod
    def normalize_voice_fields(cls, value: str) -> str:
        return _normalize_voice_name(value)

    @field_validator("lang")
    @classmethod
    def validate_lang(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_TTS_LANGS:
            raise ValueError(f"lang must be one of: {sorted(SUPPORTED_TTS_LANGS)}")
        return normalized

    @field_validator("character_voices")
    @classmethod
    def validate_character_voices(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for character, voice in (value or {}).items():
            if not isinstance(character, str) or not character.strip():
                raise ValueError("character_voices keys must be non-empty strings")
            normalized[character.strip()] = _normalize_voice_name(voice)
        return normalized


class CreateRunRequest(BaseModel):
    """Request to create a new run"""
    era_ko: str = Field(..., description="Era in Korean")
    place_ko: str = Field(..., description="Place in Korean")
    characters_ko: str = Field(..., description="Characters in Korean")
    topic_ko: str = Field(..., description="Topic in Korean")
    tts_enabled: bool = Field(default=True, description="Enable TTS generation")
    tts_config: TTSConfig = Field(
        default_factory=TTSConfig,
        description="Optional voice configuration for narration and dialogue"
    )


class CreateRunResponse(BaseModel):
    """Response from run creation"""
    run_id: str = Field(..., description="Unique run identifier")


class PageInfo(BaseModel):
    """Information about a single page"""
    page: int = Field(..., ge=0, le=4, description="Page number 0-4")
    title: str = Field(default="", description="Title for cover page")
    summary: str = Field(
        default="",
        description="Page body text. Dialogue lines are appended here when present."
    )
    dialogues: list[DialogueLine] = Field(
        default_factory=list,
        description="Structured dialogue lines for the page"
    )
    image_url: str = Field(default="", description="URL to download image")
    audio_url: str = Field(default="", description="URL to download audio")


class RunStateResponse(BaseModel):
    """Response from run state query"""
    status: Status = Field(..., description="Current run status")
    stage: Stage = Field(..., description="Current pipeline stage")
    ready_max_page: int = Field(..., ge=-1, le=4, description="Max ready page index (-1 means none)")
    ready_max_audio_page: int = Field(..., ge=-1, le=4, description="Max ready audio page index (-1 means none)")
    pages: list[PageInfo] = Field(..., description="Page information array (always 5 elements)")
    error: Optional[str] = Field(default=None, description="Error message if failed")
