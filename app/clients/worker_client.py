"""Async HTTP client for the 5080 worker server."""
import aiohttp

from app.schemas.story_schema import StorySchema

_LLM_TIMEOUT = aiohttp.ClientTimeout(total=900)
_IMG_TIMEOUT = aiohttp.ClientTimeout(total=300)
_TTS_TIMEOUT = aiohttp.ClientTimeout(total=120)
_CLEANUP_TIMEOUT = aiohttp.ClientTimeout(total=30)


class WorkerClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def generate_story(
        self, era_ko: str, place_ko: str, characters_ko: str, topic_ko: str
    ) -> StorySchema:
        async with aiohttp.ClientSession(timeout=_LLM_TIMEOUT) as session:
            async with session.post(
                f"{self.base_url}/llm/generate",
                json={
                    "era_ko": era_ko,
                    "place_ko": place_ko,
                    "characters_ko": characters_ko,
                    "topic_ko": topic_ko,
                },
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return StorySchema(**data)

    async def generate_image(self, prompt: str, seed: int, stem: str) -> bytes:
        async with aiohttp.ClientSession(timeout=_IMG_TIMEOUT) as session:
            async with session.post(
                f"{self.base_url}/image/generate",
                json={"prompt": prompt, "seed": seed, "stem": stem},
            ) as resp:
                resp.raise_for_status()
                return await resp.read()

    async def generate_tts(
        self,
        scene_no: int,
        narration: str,
        dialogue: str,
        narration_emotion: str,
        dialogue_emotion: str,
    ) -> bytes:
        async with aiohttp.ClientSession(timeout=_TTS_TIMEOUT) as session:
            async with session.post(
                f"{self.base_url}/tts/generate",
                json={
                    "scene_no": scene_no,
                    "narration": narration,
                    "dialogue": dialogue,
                    "narration_emotion": narration_emotion,
                    "dialogue_emotion": dialogue_emotion,
                },
            ) as resp:
                resp.raise_for_status()
                return await resp.read()

    async def cleanup(self) -> None:
        try:
            async with aiohttp.ClientSession(timeout=_CLEANUP_TIMEOUT) as session:
                async with session.post(f"{self.base_url}/cleanup") as resp:
                    resp.raise_for_status()
        except Exception as e:
            print(f"[WORKER CLEANUP] {e}")
