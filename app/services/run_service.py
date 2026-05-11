"""Run state management: in-memory store of RunState objects."""
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from app.schemas.run_schema import CreateRunRequest, RunStage, RunStateResponse, RunStatus, SceneInfo
from app.services import storage_service


class RunState:
    def __init__(self, run_id: str, request: CreateRunRequest):
        self.run_id = run_id
        self.request = request
        self.status = RunStatus.QUEUED
        self.stage = RunStage.LLM
        self.story_title: str = ""
        self.cover_image_url: str = ""
        self.cover_audio_url: str = ""
        self.scenes: list[SceneInfo] = []
        self.error: Optional[str] = None
        self.created_at = datetime.now()

    def to_response(self) -> RunStateResponse:
        return RunStateResponse(
            run_id=self.run_id,
            status=self.status,
            stage=self.stage,
            story_title=self.story_title,
            cover_image_url=self.cover_image_url,
            cover_audio_url=self.cover_audio_url,
            scenes=[s.to_scenario_info() for s in self.scenes],
            error=self.error,
        )

    def set_story_title(self, title: str) -> None:
        self.story_title = title

    def set_cover_image(self, filename: str) -> None:
        self.cover_image_url = f"/api/runs/{self.run_id}/images/{filename}"

    def set_cover_audio(self, filename: str) -> None:
        self.cover_audio_url = f"/api/runs/{self.run_id}/audio/{filename}"

    def init_scenes(self, scene_count: int) -> None:
        self.scenes = [SceneInfo(scene_no=i) for i in range(1, scene_count + 1)]

    def update_scene_meta(self, scene_no: int, narration: str, dialogue: str, dialogue_emotion: str) -> None:
        for s in self.scenes:
            if s.scene_no == scene_no:
                s.narration = narration
                s.dialogue = dialogue
                s.dialogue_emotion = dialogue_emotion
                return

    def add_scene_image(self, scene_no: int, filename: str) -> None:
        for s in self.scenes:
            if s.scene_no == scene_no:
                url = f"/api/runs/{self.run_id}/images/{filename}"
                if url not in s.image_urls:
                    s.image_urls.append(url)
                return

    def set_scene_audio(self, scene_no: int, filename: str, image_delay: int = 1) -> None:
        for s in self.scenes:
            if s.scene_no == scene_no:
                s.audio_url = f"/api/runs/{self.run_id}/audio/{filename}"
                s.image_delay = image_delay
                return


class RunRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, RunState] = {}

    def create(self, request: CreateRunRequest) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"{ts}_{uuid4().hex[:6]}"
        state = RunState(run_id, request)
        self._runs[run_id] = state

        storage_service.create_run_dirs(run_id)
        storage_service.cleanup_old_runs()
        return run_id

    def get(self, run_id: str) -> Optional[RunState]:
        return self._runs.get(run_id)

    def get_run_dir(self, run_id: str) -> Path:
        return storage_service.get_run_dir(run_id)


run_registry = RunRegistry()
