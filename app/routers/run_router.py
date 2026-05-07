"""Run router: POST /api/runs, GET /api/runs/{run_id}, SSE, images, audio, story."""
import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from app.jobs.job_manager import job_manager
from app.jobs.story_job import run_pipeline
from app.schemas.run_schema import CreateRunRequest, CreateRunResponse, RunStateResponse
from app.services.run_service import run_registry
from app.services import storage_service

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("", response_model=CreateRunResponse, status_code=201)
async def create_run(request: CreateRunRequest, background_tasks: BackgroundTasks):
    run_id = run_registry.create(request)

    async def _pipeline_wrapper():
        try:
            await run_pipeline(run_id, run_registry)
        finally:
            await job_manager.release(run_id)

    background_tasks.add_task(_pipeline_wrapper)
    return CreateRunResponse(run_id=run_id)


@router.get("/{run_id}", response_model=RunStateResponse)
async def get_run(run_id: str):
    state = run_registry.get(run_id)
    if not state:
        raise HTTPException(404, f"Run {run_id} not found")
    return state.to_response()


@router.get("/{run_id}/events")
async def run_events(run_id: str):
    state = run_registry.get(run_id)
    if not state:
        raise HTTPException(404, f"Run {run_id} not found")

    from app.services.event_service import event_bus

    async def generator():
        async for event in event_bus.stream(run_id):
            if event.get("keepalive"):
                yield {"event": "keepalive", "data": ""}
            else:
                yield {"event": "update", "data": json.dumps(event)}

    return EventSourceResponse(generator())


@router.get("/{run_id}/story")
async def get_story(run_id: str):
    state = run_registry.get(run_id)
    if not state:
        raise HTTPException(404, f"Run {run_id} not found")
    story_path = storage_service.get_run_dir(run_id) / "story.json"
    if not story_path.exists():
        raise HTTPException(404, "Story not yet generated")
    return FileResponse(story_path, media_type="application/json")


@router.get("/{run_id}/images/{filename}")
async def get_image(run_id: str, filename: str):
    _validate_filename(filename)
    path = storage_service.get_run_dir(run_id) / "images" / filename
    if not path.exists():
        raise HTTPException(404, f"Image {filename} not found")
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{run_id}/audio/{filename}")
async def get_audio(run_id: str, filename: str):
    _validate_filename(filename)
    path = storage_service.get_run_dir(run_id) / "audio" / filename
    if not path.exists():
        raise HTTPException(404, f"Audio {filename} not found")
    return FileResponse(
        path,
        media_type="audio/wav",
        headers={"Cache-Control": "no-store"},
    )


def _validate_filename(filename: str) -> None:
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(400, "Invalid filename")
