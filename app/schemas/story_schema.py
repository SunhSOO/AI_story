"""Story-related Pydantic schemas for LLM output validation and API responses."""
import re

from pydantic import BaseModel, Field, field_validator

from app.core.constants import ALLOWED_EMOTIONS, IMAGES_PER_SCENE, SCENE_COUNT


_WHITESPACE_RE = re.compile(r"\s+")
_ORPHAN_ASCII_PUNCT_RE = re.compile(r"(^|\s)[,.!?;:]+(?=\s|$)")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.!?;:])")

_FOREIGN_TEXT_RANGES = (
    (0x3000, 0x303F),  # CJK symbols and punctuation
    (0x3040, 0x309F),  # Hiragana
    (0x30A0, 0x30FF),  # Katakana
    (0x3100, 0x312F),  # Bopomofo
    (0x31A0, 0x31BF),  # Bopomofo extended
    (0x31C0, 0x31EF),  # CJK strokes
    (0x31F0, 0x31FF),  # Katakana phonetic extensions
    (0x3400, 0x4DBF),  # CJK extension A
    (0x4E00, 0x9FFF),  # CJK unified ideographs
    (0xF900, 0xFAFF),  # CJK compatibility ideographs
    (0xFE30, 0xFE4F),  # CJK compatibility forms
    (0xFF01, 0xFF5E),  # Fullwidth ASCII variants
    (0xFF66, 0xFF9F),  # Halfwidth Katakana
    (0x20000, 0x2A6DF),  # CJK extension B
    (0x2A700, 0x2B73F),  # CJK extension C
    (0x2B740, 0x2B81F),  # CJK extension D
    (0x2B820, 0x2CEAF),  # CJK extension E
    (0x2CEB0, 0x2EBEF),  # CJK extension F
    (0x2F800, 0x2FA1F),  # CJK compatibility supplement
    (0x30000, 0x3134F),  # CJK extension G
    (0x31350, 0x323AF),  # CJK extension H
)


def _is_latin_letter(ch: str) -> bool:
    return ("A" <= ch <= "Z") or ("a" <= ch <= "z")


def _is_foreign_story_char(ch: str) -> bool:
    cp = ord(ch)
    return _is_latin_letter(ch) or any(start <= cp <= end for start, end in _FOREIGN_TEXT_RANGES)


def _clean_story_text(value: str) -> str:
    cleaned = "".join(ch for ch in value if not _is_foreign_story_char(ch))
    cleaned = _ORPHAN_ASCII_PUNCT_RE.sub(" ", cleaned)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned)
    cleaned = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", cleaned)
    return cleaned.strip()


class SceneSchema(BaseModel):
    scene_no: int = Field(..., ge=1, le=4)
    narration: str = Field(...)
    dialogue: str = Field(..., description="장면 내 캐릭터 발화 (한국어)")
    image_prompts: list[str] = Field(..., min_length=IMAGES_PER_SCENE, max_length=IMAGES_PER_SCENE)
    dialogue_emotion: str = Field(...)

    @field_validator("narration", "dialogue", mode="before")
    @classmethod
    def remove_foreign_text(cls, v: str) -> str:
        if not isinstance(v, str):
            return v
        return _clean_story_text(v)

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
