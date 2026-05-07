"""Worker server (5080): exposes LLM generation and ComfyUI image generation via HTTP API."""
import asyncio
from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel

app = FastAPI(title="Story Worker", version="1.0.0")


class LLMRequest(BaseModel):
    era_ko: str
    place_ko: str
    characters_ko: str
    topic_ko: str


class ImageRequest(BaseModel):
    prompt: str
    seed: int
    stem: str


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/llm/generate")
async def llm_generate(req: LLMRequest):
    loop = asyncio.get_event_loop()
    from app.services.story_service import generate_story
    story = await loop.run_in_executor(
        None, generate_story, req.era_ko, req.place_ko, req.characters_ko, req.topic_ko
    )
    return story.model_dump()


@app.post("/image/generate")
async def image_generate(req: ImageRequest):
    loop = asyncio.get_event_loop()
    img_bytes = await loop.run_in_executor(None, _generate_image_bytes, req.prompt, req.seed, req.stem)
    return Response(content=img_bytes, media_type="image/png")


def _generate_image_bytes(prompt: str, seed: int, stem: str) -> bytes:
    from app.clients.comfyui_client import ComfyUIClient, generate_image_bytes
    from app.core.config import settings
    client = ComfyUIClient()
    return generate_image_bytes(
        prompt=prompt,
        seed=seed,
        stem=stem,
        workflow_path=settings.workflow_path,
        client=client,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.workers.worker_server:app", host="0.0.0.0", port=8001, reload=False)
