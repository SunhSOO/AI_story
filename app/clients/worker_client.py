"""Async HTTP client for the 5080 worker server."""
import base64
import aiohttp

from app.schemas.story_schema import StorySchema

_LLM_TIMEOUT = aiohttp.ClientTimeout(total=900)
_IMG_TIMEOUT = aiohttp.ClientTimeout(total=300)
_TTS_TIMEOUT = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=720)
_TTS_BATCH_TIMEOUT_PER_ITEM = 180
_CLEANUP_TIMEOUT = aiohttp.ClientTimeout(total=300)


class WorkerClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def generate_story(
        self,
        era_ko: str,
        place_ko: str,
        characters_ko: str,
        topic_ko: str,
        seed: int | None = None,
    ) -> StorySchema:
        async with aiohttp.ClientSession(timeout=_LLM_TIMEOUT) as session:
            async with session.post(
                f"{self.base_url}/llm/generate",
                json={
                    "era_ko": era_ko,
                    "place_ko": place_ko,
                    "characters_ko": characters_ko,
                    "topic_ko": topic_ko,
                    "seed": seed,
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
        try:
            print(f"[MASTER TTS HTTP] request scene={scene_no}")
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
                    if resp.status >= 400:
                        body = await resp.text()
                        raise RuntimeError(
                            f"Worker TTS HTTP {resp.status} scene={scene_no}: {body[:500]}"
                        )
                    data = await resp.read()
                    print(f"[MASTER TTS HTTP] response scene={scene_no} bytes={len(data)}")
                    return data
        except Exception as exc:
            raise RuntimeError(
                f"Worker TTS request failed scene={scene_no}: {type(exc).__name__}: {exc!r}"
            ) from exc

    async def generate_tts_batch(
        self,
        items: list[dict],
    ) -> dict[int, bytes]:
        """배치 TTS 요청: 여러 scene의 TTS를 1회 요청으로 생성하고 자동 VRAM 해제.

        Args:
            items: list of {"scene_no", "narration", "dialogue", "narration_emotion", "dialogue_emotion"}

        Returns:
            {scene_no: wav_bytes} dict
        """
        total_timeout = aiohttp.ClientTimeout(
            total=_TTS_BATCH_TIMEOUT_PER_ITEM * len(items) + 120,  # +120s for unload
            sock_connect=30,
        )
        try:
            print(f"[MASTER TTS BATCH] request items={len(items)}")
            async with aiohttp.ClientSession(timeout=total_timeout) as session:
                async with session.post(
                    f"{self.base_url}/tts/batch",
                    json={"items": items},
                ) as resp:
                    if resp.status >= 400:
                        body = await resp.text()
                        raise RuntimeError(
                            f"Worker TTS batch HTTP {resp.status}: {body[:500]}"
                        )
                    data = await resp.json()
                    # base64 디코딩
                    result: dict[int, bytes] = {}
                    for scene_no_str, b64_wav in data.items():
                        result[int(scene_no_str)] = base64.b64decode(b64_wav)
                    print(
                        f"[MASTER TTS BATCH] response scenes={list(result.keys())} "
                        f"total_bytes={sum(len(v) for v in result.values())}"
                    )
                    return result
        except Exception as exc:
            raise RuntimeError(
                f"Worker TTS batch request failed: {type(exc).__name__}: {exc!r}"
            ) from exc

    async def generate_cover_tts(self, title: str) -> bytes:
        return await self.generate_tts(
            scene_no=0,
            narration=title,
            dialogue="",
            narration_emotion="",
            dialogue_emotion="",
        )

    async def free_comfyui(self) -> None:
        try:
            async with aiohttp.ClientSession(timeout=_CLEANUP_TIMEOUT) as session:
                async with session.post(f"{self.base_url}/comfyui/free") as resp:
                    resp.raise_for_status()
        except Exception as e:
            print(f"[WORKER COMFYUI FREE] {e}")

    async def unload_tts(self) -> None:
        async with aiohttp.ClientSession(timeout=_CLEANUP_TIMEOUT) as session:
            async with session.post(f"{self.base_url}/tts/unload") as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    raise RuntimeError(f"Worker TTS unload HTTP {resp.status}: {body[:500]}")
                print("[WORKER TTS UNLOAD] ok")

    async def cleanup(self) -> None:
        try:
            async with aiohttp.ClientSession(timeout=_CLEANUP_TIMEOUT) as session:
                async with session.post(f"{self.base_url}/cleanup") as resp:
                    resp.raise_for_status()
        except Exception as e:
            print(f"[WORKER CLEANUP] {e}")
