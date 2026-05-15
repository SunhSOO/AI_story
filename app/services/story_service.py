"""Story generation service: prompt → GBNF-constrained LLM → validated StorySchema."""
import json
import random
from pathlib import Path

from pydantic import ValidationError

from app.clients.llama_cpp_client import call_llama
from app.core.exceptions import LLMError, SchemaValidationError
from app.schemas.story_schema import StorySchema


def _load_prompt_template() -> str:
    tpl_path = Path(__file__).parent.parent / "prompts" / "story_prompt_template.md"
    return tpl_path.read_text(encoding="utf-8")


_PLOT_SHAPES = [
    "작은 약속을 지키는 이야기",
    "잃어버린 물건의 비밀을 찾는 이야기",
    "서로 다른 생각을 조율하는 이야기",
    "새로운 규칙을 배우는 이야기",
    "위험해 보였던 것이 사실은 도움이 되는 이야기",
    "낯선 장소에서 숨은 단서를 발견하는 이야기",
    "작은 실수가 뜻밖의 해결책이 되는 이야기",
    "주인공의 특별한 재능이 드러나는 이야기",
]

_CONFLICTS = [
    "오해",
    "시간 부족",
    "사라진 단서",
    "예상 밖 날씨",
    "서로 다른 목표",
    "고장 난 도구",
    "작은 두려움",
    "잘못 전달된 메시지",
]

_RESOLUTIONS = [
    "관찰과 추리",
    "용기 있는 질문",
    "작은 도움의 연쇄",
    "새로운 사용법 발견",
    "솔직한 사과",
    "차분한 계획",
    "함께 만든 신호",
    "주인공만의 상상력",
]

_BANNED_STORY_PHRASES = (
    "새로운 친구를 만나고 싶",
    "길을 잃은 것 같",
    "포기하지 말자",
    "한 번만 더 해볼게",
    "함께라면 무엇이든",
    "함께라면 뭐든",
    "함께라면 해낼 수",
)


def _build_variation(seed: int | None) -> str:
    rng = random.Random(seed)
    return (
        f"plot={rng.choice(_PLOT_SHAPES)}, "
        f"conflict={rng.choice(_CONFLICTS)}, "
        f"resolution={rng.choice(_RESOLUTIONS)}"
    )


def _ensure_not_boilerplate(story: StorySchema) -> None:
    text = " ".join(
        [story.title]
        + [scene.narration for scene in story.scenes]
        + [scene.dialogue for scene in story.scenes]
    )
    for phrase in _BANNED_STORY_PHRASES:
        if phrase in text:
            raise SchemaValidationError(f"boilerplate story phrase detected: {phrase}")


def _build_prompt(era: str, place: str, characters: str, topic: str, seed: int | None) -> str:
    template = _load_prompt_template()
    return (
        template
        .replace("{era}", era)
        .replace("{place}", place)
        .replace("{characters}", characters)
        .replace("{topic}", topic)
        .replace("{variation}", _build_variation(seed))
    )


def generate_story(
    era: str,
    place: str,
    characters: str,
    topic: str,
    seed: int | None = None,
) -> StorySchema:
    """Run LLM once and return a validated StorySchema.

    A failed LLM output is surfaced immediately so the pipeline can clean up
    VRAM and require a fresh request instead of retrying with the same inputs.

    Raises:
        LLMError: If generation or JSON parsing fails.
        SchemaValidationError: If schema validation fails.
    """
    prompt = _build_prompt(era, place, characters, topic, seed)
    print("\n=== LLM attempt 1/1 ===")

    json_str = call_llama(prompt, seed=seed)
    try:
        story_dict = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise LLMError(f"JSON parse error: {e}") from e

    try:
        story = StorySchema.model_validate(story_dict)
        _ensure_not_boilerplate(story)
    except SchemaValidationError:
        raise
    except ValidationError as e:
        raise SchemaValidationError(str(e)) from e

    return story
