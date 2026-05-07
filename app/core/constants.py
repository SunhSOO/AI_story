"""Project-wide constants."""

ALLOWED_EMOTIONS = frozenset(
    {"happy", "sad", "curious", "surprised", "tense", "calm", "warm", "magical"}
)

EMOTION_STYLE_MAP = {
    "happy": "joyful, bright, warm, smiling voice, upbeat",
    "sad": "sorrowful, melancholy, tearful, heavy voice",
    "curious": "inquisitive, wondering, playful, light voice",
    "surprised": "astonished, wide-eyed, breathless",
    "tense": "intense, urgent, slightly trembling",
    "calm": "slow, calm, peaceful, gentle, relaxed, steady",
    "warm": "gentle, caring, tender, soft voice",
    "magical": "dreamy, mystical, ethereal, enchanting",
}

IMAGE_STYLE_PREFIX = (
    "watercolor painting, children's book illustration, soft pastel colors, "
    "gentle brush strokes, warm lighting, "
)

SCENE_COUNT = 4
IMAGES_PER_SCENE = 3
