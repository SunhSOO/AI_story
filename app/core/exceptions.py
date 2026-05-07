"""Domain-specific exceptions."""


class StoryGenError(RuntimeError):
    """Base error for story generation pipeline."""


class LLMError(StoryGenError):
    """LLM call failed or produced invalid output."""


class SchemaValidationError(StoryGenError):
    """LLM output failed Pydantic schema validation."""


class ImageGenError(StoryGenError):
    """ComfyUI image generation failed."""


class TTSError(StoryGenError):
    """voxcpm2 TTS generation failed."""


class STTError(StoryGenError):
    """Whisper STT failed."""


class RunNotFoundError(StoryGenError):
    """Run ID not found."""
