"""Async HTTP client for the 5080 worker server."""
import base64
import json
import time
import aiohttp

from app.core.config import settings
from app.schemas.story_schema import StorySchema

_LLM_TIMEOUT = aiohttp.ClientTimeout(total=900)
_IMG_TIMEOUT = aiohttp.ClientTimeout(total=settings.image_gen_timeout + 120, sock_connect=30)
_IMG_BATCH_TIMEOUT_PER_ITEM = settings.image_gen_timeout + 120
_TTS_TIMEOUT = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=720)
_TTS_BATCH_TIMEOUT_PER_ITEM = 180
_STT_TIMEOUT = aiohttp.ClientTimeout(total=300, sock_connect=30)
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
        started_at = time.time()
        try:
            print(f"[WORKER IMAGE HTTP] request stem={stem} prompt_len={len(prompt)}")
            async with aiohttp.ClientSession(timeout=_IMG_TIMEOUT) as session:
                async with session.post(
                    f"{self.base_url}/image/generate",
                    json={"prompt": prompt, "seed": seed, "stem": stem},
                ) as resp:
                    if resp.status >= 400:
                        body = await resp.text()
                        raise RuntimeError(f"Worker image HTTP {resp.status} stem={stem}: {body[:500]}")
                    data = await resp.read()
                    print(
                        f"[WORKER IMAGE HTTP] response stem={stem} "
                        f"bytes={len(data)} elapsed={time.time() - started_at:.1f}s"
                    )
                    return data
        except Exception as exc:
            raise RuntimeError(
                f"Worker image request failed stem={stem}: {type(exc).__name__}: {exc!r}"
            ) from exc

    async def generate_image_batch(self, items: list[dict]) -> dict[str, bytes]:
        timeout = aiohttp.ClientTimeout(
            total=_IMG_BATCH_TIMEOUT_PER_ITEM * max(1, len(items)),
            sock_connect=30,
        )
        started_at = time.time()
        try:
            stems = [str(item.get("stem", "")) for item in items]
            print(f"[WORKER IMAGE BATCH HTTP] request count={len(items)} stems={stems}")
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.base_url}/image/batch",
                    json={"images": items},
                ) as resp:
                    if resp.status >= 400:
                        body = await resp.text()
                        raise RuntimeError(f"Worker image batch HTTP {resp.status}: {body[:500]}")
                    data = await resp.json()

            result: dict[str, bytes] = {}
            for item in data.get("images", []):
                stem = str(item["stem"])
                result[stem] = base64.b64decode(item["image_base64"])

            missing = [stem for stem in stems if stem not in result]
            if missing:
                raise RuntimeError(f"Worker image batch missing results: {missing}")

            print(
                f"[WORKER IMAGE BATCH HTTP] response count={len(result)} "
                f"total_bytes={sum(len(v) for v in result.values())} "
                f"elapsed={time.time() - started_at:.1f}s"
            )
            return result
        except Exception as exc:
            raise RuntimeError(
                f"Worker image batch request failed: {type(exc).__name__}: {exc!r}"
            ) from exc

    async def stream_image_batch(self, items: list[dict]):
        timeout = aiohttp.ClientTimeout(
            total=_IMG_BATCH_TIMEOUT_PER_ITEM * max(1, len(items)),
            sock_connect=30,
            sock_read=_IMG_BATCH_TIMEOUT_PER_ITEM,
        )
        stems = [str(item.get("stem", "")) for item in items]
        started_at = time.time()
        try:
            print(f"[WORKER IMAGE STREAM HTTP] request count={len(items)} stems={stems}")
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.base_url}/image/batch-stream",
                    json={"images": items},
                ) as resp:
                    if resp.status >= 400:
                        body = await resp.text()
                        raise RuntimeError(f"Worker image stream HTTP {resp.status}: {body[:500]}")

                    received = 0
                    while True:
                        raw_line = await resp.content.readline()
                        if not raw_line:
                            break
                        data = json.loads(raw_line.decode("utf-8"))
                        if data.get("ping"):
                            print(f"[WORKER IMAGE STREAM HTTP] ping stem={data.get('stem')}")
                            continue
                        if data.get("error"):
                            raise RuntimeError(
                                f"Worker image stream failed stem={data.get('stem')}: {data['error']}"
                            )
                        stem = str(data["stem"])
                        img_bytes = await resp.content.readexactly(int(data["bytes"]))
                        await resp.content.readexactly(1)
                        received += 1
                        print(
                            f"[WORKER IMAGE STREAM HTTP] item stem={stem} "
                            f"bytes={len(img_bytes)} received={received}/{len(items)} "
                            f"elapsed={time.time() - started_at:.1f}s"
                        )
                        yield stem, img_bytes

            print(
                f"[WORKER IMAGE STREAM HTTP] complete count={received} "
                f"elapsed={time.time() - started_at:.1f}s"
            )
            if received != len(items):
                raise RuntimeError(
                    f"Worker image stream ended early: received={received}, expected={len(items)}"
                )
        except Exception as exc:
            raise RuntimeError(
                f"Worker image stream request failed: {type(exc).__name__}: {exc!r}"
            ) from exc

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
    ) -> dict[str, bytes]:
        """배치 TTS 요청: narration/dialogue 분할 생성.

        Args:
            items: list of {"scene_no", "narration", "dialogue", "narration_emotion", "dialogue_emotion"}

        Returns:
            {"scene_no_0": narration_wav_bytes, "scene_no_1": dialogue_wav_bytes, ...}
            키 형식: "{scene_no}_0" = narration, "{scene_no}_1" = dialogue
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
                    # base64 디코딩 — 키: "scene_no_0", "scene_no_1"
                    result: dict[str, bytes] = {}
                    for key, b64_wav in data.items():
                        result[key] = base64.b64decode(b64_wav)
                    print(
                        f"[MASTER TTS BATCH] response keys={list(result.keys())} "
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

    async def transcribe_stt(self, audio_bytes: bytes, language: str) -> tuple[str, float]:
        try:
            form = aiohttp.FormData()
            form.add_field(
                "audio_file",
                audio_bytes,
                filename="recording.webm",
                content_type="application/octet-stream",
            )
            form.add_field("language", language)

            print(f"[MASTER STT HTTP] request bytes={len(audio_bytes)} language={language}")
            async with aiohttp.ClientSession(timeout=_STT_TIMEOUT) as session:
                async with session.post(f"{self.base_url}/stt/transcribe", data=form) as resp:
                    if resp.status >= 400:
                        body = await resp.text()
                        raise RuntimeError(f"Worker STT HTTP {resp.status}: {body[:500]}")
                    data = await resp.json()
                    text = str(data.get("stt_text", ""))
                    confidence = float(data.get("confidence", 0.0))
                    print(f"[MASTER STT HTTP] response chars={len(text)} confidence={confidence:.2f}")
                    return text, confidence
        except Exception as exc:
            raise RuntimeError(f"Worker STT request failed: {type(exc).__name__}: {exc!r}") from exc

    async def free_comfyui(self, unload_models: bool = False) -> None:
        try:
            async with aiohttp.ClientSession(timeout=_CLEANUP_TIMEOUT) as session:
                async with session.post(
                    f"{self.base_url}/comfyui/free",
                    json={"unload_models": unload_models},
                ) as resp:
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

    async def cleanup(self, unload_comfyui_models: bool = False) -> None:
        try:
            async with aiohttp.ClientSession(timeout=_CLEANUP_TIMEOUT) as session:
                async with session.post(
                    f"{self.base_url}/cleanup",
                    json={"unload_comfyui_models": unload_comfyui_models},
                ) as resp:
                    resp.raise_for_status()
        except Exception as e:
            print(f"[WORKER CLEANUP] {e}")
