"""Run API request/response schemas."""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

from app.core.constants import IMAGES_PER_SCENE


class RunStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


class RunStage(str, Enum):
    LLM = "LLM"
    IMAGE = "IMAGE"
    TTS = "TTS"


class CreateRunRequest(BaseModel):
    era_ko: str = Field(..., description="시대 (한국어)")
    place_ko: str = Field(..., description="장소 (한국어)")
    characters_ko: str = Field(..., description="등장인물 (한국어)")
    topic_ko: str = Field(..., description="주제 (한국어)")


class CreateRunResponse(BaseModel):
    run_id: str


class ScenarioItem(BaseModel):
    index: int
    msg: str = ""
    audio_url: str = ""
    image_url: str = ""
    delay: int = 0


class SceneScenarioInfo(BaseModel):
    scene_no: int
    status: str = "Pending"
    scenarios: list[ScenarioItem] = Field(default_factory=list)
    error: Optional[str] = None


class SceneInfo(BaseModel):
    scene_no: int
    narration: str = ""
    dialogue: str = ""
    dialogue_emotion: str = ""
    image_urls: list[str] = Field(default_factory=list)
    audio_url: str = ""
    dialogue_audio_url: str = ""
    image_delay: int = 1
    audio_delay: int = 0
    dialogue_audio_delay: int = 0

    def to_scenario_info(self) -> SceneScenarioInfo:
        has_audio = bool(self.audio_url) or bool(self.dialogue_audio_url)
        has_all_images = len(self.image_urls) >= IMAGES_PER_SCENE

        if has_audio and has_all_images:
            scene_status = "End"
        elif has_audio or self.image_urls:
            scene_status = "Running"
        else:
            scene_status = "Pending"

        img_urls = self.image_urls[:IMAGES_PER_SCENE]
        while len(img_urls) < IMAGES_PER_SCENE:
            img_urls.append("")

        d = self.image_delay
        scenarios = [
            ScenarioItem(index=0, msg="", audio_url="", image_url=img_urls[0], delay=d),
            ScenarioItem(index=1, msg=self.narration, audio_url=self.audio_url, image_url="", delay=self.audio_delay),
            ScenarioItem(index=2, msg="", audio_url="", image_url=img_urls[1], delay=d),
            ScenarioItem(index=3, msg=self.dialogue, audio_url=self.dialogue_audio_url, image_url="", delay=self.dialogue_audio_delay),
        ]

        return SceneScenarioInfo(
            scene_no=self.scene_no,
            status=scene_status,
            scenarios=scenarios,
        )


class RunStateResponse(BaseModel):
    run_id: str
    status: RunStatus
    stage: RunStage
    story_title: str = ""
    cover: Optional[SceneScenarioInfo] = None
    scenes: list[SceneScenarioInfo] = Field(default_factory=list)
    error: Optional[str] = None
    restart_required: bool = False
