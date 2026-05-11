"""Project-wide constants."""

ALLOWED_EMOTIONS = frozenset({"기쁨", "슬픔", "무서움"})

EMOTION_STYLE_MAP = {
    "기쁨": "joyful bright tone",
    "슬픔": "sad emotional voice",
    "무서움": "fearful trembling voice",
}

IMAGE_STYLE_PREFIX = (
    "watercolor painting, children's book illustration, soft pastel colors, "
    "gentle brush strokes, warm lighting, "
)

SCENE_COUNT = 4
IMAGES_PER_SCENE = 3
