"""
FastAPI server for storybook generation
External API Specification v2.0 compliant
"""
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from models import (
    FieldType,
    FieldSTTResponse,
    CreateRunRequest,
    CreateRunResponse,
    RunStateResponse
)
from run_manager import run_manager
from pipeline.stt import process_field_stt
from pipeline.story_pipeline import run_story_pipeline


# Create FastAPI app
app = FastAPI(
    title="Storybook Generation API",
    description="External API v2.0 for generating children's storybooks",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "version": "2.0.0"}


@app.post("/api/stt/field", response_model=FieldSTTResponse)
async def field_stt(
    audio_file: UploadFile = File(...),
    field_type: str = Form(...),
    language: str = Form(default="ko-KR")
):
    """
    Field-level STT endpoint
    
    Accepts audio file and converts to text with field-specific parsing
    """
    # Validate field type
    try:
        field_type_enum = FieldType(field_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid field_type. Must be one of: {[ft.value for ft in FieldType]}"
        )
    
    # Read audio file
    audio_data = await audio_file.read()
    
    if not audio_data:
        raise HTTPException(status_code=400, detail="Empty audio file")
    
    # Process STT
    try:
        stt_text, parsed_value, confidence = await process_field_stt(
            audio_data,
            field_type_enum.value,
            language
        )
        
        return FieldSTTResponse(
            stt_text=stt_text,
            parsed_value=parsed_value,
            confidence=confidence
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STT processing failed: {str(e)}")


@app.post("/api/runs", response_model=CreateRunResponse, status_code=201)
async def create_run(request: CreateRunRequest, background_tasks: BackgroundTasks):
    """
    Create a new story generation run
    
    Returns run_id immediately and starts background processing
    """
    # Create run
    run_id = run_manager.create_run(
        era=request.era_ko,
        place=request.place_ko,
        characters=request.characters_ko,
        topic=request.topic_ko,
        tts_enabled=request.tts_enabled
    )
    
    # Start background pipeline
    background_tasks.add_task(run_story_pipeline, run_id, run_manager)
    
    return CreateRunResponse(run_id=run_id)


@app.get("/api/runs/{run_id}", response_model=RunStateResponse)
async def get_run_state(run_id: str):
    """
    Query run state
    
    Returns current status, stage, and ready indicators
    """
    run_state = run_manager.get_run(run_id)
    
    if not run_state:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    
    return run_state.to_response()


@app.get("/api/runs/{run_id}/events")
async def get_run_events(run_id: str):
    """
    SSE event stream for run progress
    
    Streams status/stage/ready updates as they occur
    """
    run_state = run_manager.get_run(run_id)
    
    if not run_state:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    
    async def event_generator():
        """Generate SSE events"""
        async for event_data in run_manager.get_events(run_id):
            # Skip keepalive events in data
            if event_data.get("keepalive"):
                yield {"event": "keepalive", "data": ""}
            else:
                # Send event with JSON data
                import json
                yield {"event": "update", "data": json.dumps(event_data)}
    
    return EventSourceResponse(event_generator())


@app.get("/api/runs/{run_id}/images/{filename}")
async def get_image(run_id: str, filename: str):
    """
    Download generated image
    
    Returns PNG image file
    """
    run_state = run_manager.get_run(run_id)
    
    if not run_state:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    
    # Validate filename to prevent directory traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    image_path = run_manager.get_run_dir(run_id) / filename
    
    if not image_path.exists():
        raise HTTPException(status_code=404, detail=f"Image {filename} not found")
    
    return FileResponse(
        path=str(image_path),
        media_type="image/png",
        filename=filename
    )


@app.get("/api/runs/{run_id}/audio/{filename}")
async def get_audio(run_id: str, filename: str):
    """
    Download generated audio
    
    Returns WAV audio file
    """
    run_state = run_manager.get_run(run_id)
    
    if not run_state:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    
    # Validate filename to prevent directory traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    audio_path = run_manager.get_run_dir(run_id) / filename
    
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail=f"Audio {filename} not found")
    
    return FileResponse(
        path=str(audio_path),
        media_type="audio/wav",
        filename=filename
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
