"""Run API request/response schemas."""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


class RunStage(str, Enum):
    LLM = "LLM"
    IMAGE = "IMAGE"
    TTS = "TTS"
    PARALLEL = "PARALLEL"


class CreateRunRequest(BaseModel):
    era_ko: str = Field(..., description="시대 (한국어)")
    place_ko: str = Field(..., description="장소 (한국어)")
    characters_ko: str = Field(..., description="등장인물 (한국어)")
    topic_ko: str = Field(..., description="주제 (한국어)")


class CreateRunResponse(BaseModel):
    run_id: str


class SceneImageInfo(BaseModel):
    scene_no: int
    image_urls: list[str] = Field(default_factory=list)


class SceneInfo(BaseModel):
    scene_no: int
    title: str = ""
    narration: str = ""
    dialogue: str = ""
    narration_emotion: str = ""
    dialogue_emotion: str = ""
    image_urls: list[str] = Field(default_factory=list)
    audio_url: str = ""


class RunStateResponse(BaseModel):
    run_id: str
    status: RunStatus
    stage: RunStage
    story_title: str = ""
    cover_image_url: str = ""
    cover_audio_url: str = ""
    scenes: list[SceneInfo] = Field(default_factory=list)
    error: Optional[str] = None
