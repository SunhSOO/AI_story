"""
Run state management and SSE event handling
"""
import asyncio
import json
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from models import Status, Stage, PageInfo, RunStateResponse


class RunState:
    """State for a single run"""
    
    def __init__(self, run_id: str, era: str, place: str, characters: str, topic: str, tts_enabled: bool):
        self.run_id = run_id
        self.era = era
        self.place = place
        self.characters = characters
        self.topic = topic
        self.tts_enabled = tts_enabled
        
        self.status = Status.QUEUED
        self.stage = Stage.LLM
        self.ready_max_page = -1
        self.ready_max_audio_page = -1
        self.error: Optional[str] = None
        self.created_at = datetime.now()
        
        # Initialize pages array with 5 empty pages
        self.pages = [
            PageInfo(page=i, title="", summary="", image_url="", audio_url="")
            for i in range(5)
        ]
    
    def to_response(self) -> RunStateResponse:
        """Convert to API response model"""
        return RunStateResponse(
            status=self.status,
            stage=self.stage,
            ready_max_page=self.ready_max_page,
            ready_max_audio_page=self.ready_max_audio_page,
            pages=self.pages,
            error=self.error
        )
    
    def set_page_image(self, page: int, filename: str):
        """Set image URL for a page"""
        if 0 <= page < 5:
            self.pages[page].image_url = f"/api/runs/{self.run_id}/images/{filename}"
            self.ready_max_page = max(self.ready_max_page, page)
    
    def set_page_audio(self, page: int, filename: str):
        """Set audio URL for a page"""
        if 0 <= page < 5:
            self.pages[page].audio_url = f"/api/runs/{self.run_id}/audio/{filename}"
            self.ready_max_audio_page = max(self.ready_max_audio_page, page)
    
    def set_page_content(self, page: int, title: str = "", summary: str = ""):
        """Set text content for a page"""
        if 0 <= page < 5:
            if title:
                self.pages[page].title = title
            if summary:
                self.pages[page].summary = summary


class RunManager:
    """Manages all runs and their states"""
    
    def __init__(self, outputs_dir: Path, max_outputs: int = 100):
        self.outputs_dir = outputs_dir
        self.max_outputs = max_outputs
        self.runs: dict[str, RunState] = {}
        self.event_queues: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        
        # Create outputs directory
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
    
    def create_run(self, era: str, place: str, characters: str, topic: str, tts_enabled: bool = True) -> str:
        """Create a new run and return its ID"""
        # Generate timestamp-based ID: YYYYMMDD_HHMMSS_short_uuid
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_id = uuid4().hex[:6]  # 6 characters for uniqueness
        run_id = f"{timestamp}_{short_id}"
        run_state = RunState(run_id, era, place, characters, topic, tts_enabled)
        self.runs[run_id] = run_state
        
        # Create output directory for this run
        run_dir = self.outputs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # Clean up old outputs if needed
        self._cleanup_old_outputs()
        
        return run_id
    
    def get_run(self, run_id: str) -> Optional[RunState]:
        """Get run state by ID"""
        return self.runs.get(run_id)
    
    def get_run_dir(self, run_id: str) -> Path:
        """Get output directory for a run"""
        return self.outputs_dir / run_id
    
    async def emit_event(self, run_id: str, event_data: dict):
        """Emit an SSE event for a run"""
        if run_id in self.event_queues:
            await self.event_queues[run_id].put(event_data)
    
    async def get_events(self, run_id: str):
        """Generator for SSE events"""
        queue = self.event_queues[run_id]
        
        # Send initial state
        run_state = self.get_run(run_id)
        if run_state:
            yield {
                "status": run_state.status.value,
                "stage": run_state.stage.value,
                "ready_max_page": run_state.ready_max_page,
                "ready_max_audio_page": run_state.ready_max_audio_page
            }
        
        # Stream updates
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield event
                
                # Stop streaming if run is done or failed
                if event.get("status") in [Status.DONE.value, Status.FAILED.value]:
                    break
            except asyncio.TimeoutError:
                # Send keepalive
                yield {"keepalive": True}
    
    def _cleanup_old_outputs(self):
        """Delete oldest outputs if exceeding max_outputs"""
        # Get all run directories with their creation times
        run_dirs = []
        for item in self.outputs_dir.iterdir():
            if item.is_dir():
                run_dirs.append((item, item.stat().st_ctime))
        
        # Sort by creation time (oldest first)
        run_dirs.sort(key=lambda x: x[1])
        
        # Delete oldest if exceeding limit
        while len(run_dirs) > self.max_outputs:
            oldest_dir, _ = run_dirs.pop(0)
            try:
                shutil.rmtree(oldest_dir)
                # Also remove from in-memory cache if present
                run_id = oldest_dir.name
                if run_id in self.runs:
                    del self.runs[run_id]
                if run_id in self.event_queues:
                    del self.event_queues[run_id]
            except Exception as e:
                print(f"Warning: Failed to delete old output {oldest_dir}: {e}")


# Global run manager instance
run_manager = RunManager(outputs_dir=Path(__file__).parent / "outputs")
