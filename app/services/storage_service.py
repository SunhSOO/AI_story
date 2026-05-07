"""File storage helpers for run outputs."""
import json
import shutil
from pathlib import Path

from app.core.config import settings
from app.schemas.story_schema import StorySchema


def get_run_dir(run_id: str) -> Path:
    return settings.outputs_dir / run_id


def create_run_dirs(run_id: str) -> Path:
    run_dir = get_run_dir(run_id)
    (run_dir / "images").mkdir(parents=True, exist_ok=True)
    (run_dir / "audio").mkdir(parents=True, exist_ok=True)
    return run_dir


def save_story(run_id: str, story: StorySchema) -> None:
    run_dir = get_run_dir(run_id)
    path = run_dir / "story.json"
    path.write_text(story.model_dump_json(indent=2), encoding="utf-8")


def append_event(run_id: str, event: dict) -> None:
    run_dir = get_run_dir(run_id)
    path = run_dir / "events.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def cleanup_old_runs(max_runs: int | None = None) -> None:
    limit = max_runs or settings.max_runs
    base = settings.outputs_dir
    if not base.exists():
        return
    dirs = [(d, d.stat().st_ctime) for d in base.iterdir() if d.is_dir()]
    dirs.sort(key=lambda x: x[1])
    while len(dirs) > limit:
        oldest, _ = dirs.pop(0)
        try:
            shutil.rmtree(oldest)
        except Exception:
            pass
