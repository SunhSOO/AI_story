"""Story-related Pydantic schemas for LLM output validation and API responses."""
from pydantic import BaseModel, Field, field_validator

from app.core.constants import ALLOWED_EMOTIONS, SCENE_COUNT


class SceneSchema(BaseModel):
    scene_no: int = Field(..., ge=1, le=4)
    narration: str = Field(..., min_length=1)
    dialogue: str = Field(..., min_length=1, description="장면 내 캐릭터 발화 (한국어)")
    image_prompts: list[str] = Field(..., min_length=3, max_length=3)
    dialogue_emotion: str = Field(...)

    @field_validator("dialogue_emotion")
    @classmethod
    def validate_emotion(cls, v: str) -> str:
        if v not in ALLOWED_EMOTIONS:
            raise ValueError(f"emotion must be one of {sorted(ALLOWED_EMOTIONS)}, got '{v}'")
        return v

    @field_validator("image_prompts")
    @classmethod
    def no_chinese(cls, v: list[str]) -> list[str]:
        for prompt in v:
            if not prompt.strip():
                raise ValueError("image_prompts entries must not be empty")
            for ch in prompt:
                cp = ord(ch)
                if 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF:
                    raise ValueError("image_prompts must not contain Chinese characters")
        return v


class StorySchema(BaseModel):
    title: str = Field(..., min_length=1)
    cover_prompt: str = Field(..., min_length=1, description="표지 이미지 생성용 영어 프롬프트")
    scenes: list[SceneSchema] = Field(..., min_length=SCENE_COUNT, max_length=SCENE_COUNT)

    @field_validator("scenes")
    @classmethod
    def validate_scene_order(cls, scenes: list[SceneSchema]) -> list[SceneSchema]:
        for i, scene in enumerate(scenes, start=1):
            if scene.scene_no != i:
                raise ValueError(f"scenes[{i-1}].scene_no must be {i}, got {scene.scene_no}")
        return scenes
