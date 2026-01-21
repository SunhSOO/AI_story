"""
Pydantic models for API contracts following External API Specification v2.0
"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


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


class CreateRunRequest(BaseModel):
    """Request to create a new run"""
    era_ko: str = Field(..., description="Era in Korean")
    place_ko: str = Field(..., description="Place in Korean")
    characters_ko: str = Field(..., description="Characters in Korean")
    topic_ko: str = Field(..., description="Topic in Korean")
    tts_enabled: bool = Field(default=True, description="Enable TTS generation")


class CreateRunResponse(BaseModel):
    """Response from run creation"""
    run_id: str = Field(..., description="Unique run identifier")


class PageInfo(BaseModel):
    """Information about a single page"""
    page: int = Field(..., ge=0, le=4, description="Page number 0-4")
    title: str = Field(default="", description="Title for cover page")
    summary: str = Field(default="", description="Summary for panel pages")
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
