"""Project-wide constants."""

ALLOWED_EMOTIONS = frozenset(
    {
        "행복",
        "슬픔",
        "화남",
        "밝음",
        "긴장",
        "무서움",
    }
)

EMOTION_STYLE_MAP = {
    "행복": "cheerful tone",
    "슬픔": "sad emotional voice",
    "화남": "angry aggressive tone",
    "밝음": "bright energetic tone",
    "긴장": "nervous hesitant voice",
    "무서움": "fearful trembling voice",
}

IMAGE_STYLE_PREFIX = (
    "watercolor painting, children's book illustration, soft pastel colors, "
    "gentle brush strokes, warm lighting, "
)

SCENE_COUNT = 4
IMAGES_PER_SCENE = 3
