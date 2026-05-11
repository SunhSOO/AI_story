"""Story generation service: prompt → GBNF-constrained LLM → validated StorySchema."""
import json
from pathlib import Path

from app.clients.llama_cpp_client import call_llama
from app.core.config import settings
from app.core.exceptions import LLMError, SchemaValidationError
from app.schemas.story_schema import StorySchema


def _load_prompt_template() -> str:
    tpl_path = Path(__file__).parent.parent / "prompts" / "story_prompt_template.md"
    return tpl_path.read_text(encoding="utf-8")


def _build_prompt(era: str, place: str, characters: str, topic: str) -> str:
    template = _load_prompt_template()
    return (
        template
        .replace("{era}", era)
        .replace("{place}", place)
        .replace("{characters}", characters)
        .replace("{topic}", topic)
    )


def generate_story(
    era: str,
    place: str,
    characters: str,
    topic: str,
    seed: int | None = None,
) -> StorySchema:
    """Run LLM and return a validated StorySchema.

    Retries up to settings.llm_max_retries times.

    Raises:
        LLMError: If all retries fail.
        SchemaValidationError: If validation repeatedly fails.
    """
    prompt = _build_prompt(era, place, characters, topic)
    current_prompt = prompt
    last_error: Exception | None = None

    for attempt in range(settings.llm_max_retries):
        print(f"\n=== LLM attempt {attempt + 1}/{settings.llm_max_retries} ===")
        try:
            json_str = call_llama(current_prompt, seed=seed)
            story_dict = json.loads(json_str)
            story = StorySchema.model_validate(story_dict)
            return story
        except json.JSONDecodeError as e:
            last_error = LLMError(f"JSON parse error: {e}")
        except Exception as e:
            if "SchemaValidation" in type(e).__name__ or "ValidationError" in type(e).__name__:
                last_error = SchemaValidationError(str(e))
            else:
                last_error = LLMError(str(e))

        print(f"[RETRY] Attempt {attempt + 1} failed: {last_error}")
        retry_hint = "REMINDER: Output ONLY the JSON object. scenes array must have exactly 4 items. dialogue_emotion must be one of: 기쁨, 슬픔, 무서움.\n"
        current_prompt = retry_hint + prompt

    raise LLMError(f"Story generation failed after {settings.llm_max_retries} retries: {last_error}")
