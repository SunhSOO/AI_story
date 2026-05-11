"""File storage helpers for run outputs."""
import json
import re
import shutil
import wave
from pathlib import Path

from app.core.config import settings
from app.schemas.run_schema import RunStage, RunStateResponse, RunStatus, SceneInfo
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


def load_run_response(run_id: str) -> RunStateResponse | None:
    """Rebuild a run response from files after the in-memory registry is lost."""
    run_dir = get_run_dir(run_id)
    if not run_dir.exists():
        return None

    story_path = run_dir / "story.json"
    story_data: dict = {}
    if story_path.exists():
        try:
            story_data = json.loads(story_path.read_text(encoding="utf-8"))
        except Exception:
            story_data = {}

    story_title = str(story_data.get("title") or "")
    scene_infos = _load_scene_infos(run_id, run_dir, story_data)
    cover_image_url = _asset_url(run_id, "images", "cover.png") if (run_dir / "images" / "cover.png").exists() else ""
    cover_audio_url = _asset_url(run_id, "audio", "cover.wav") if (run_dir / "audio" / "cover.wav").exists() else ""

    complete = bool(
        story_title
        and cover_image_url
        and cover_audio_url
        and len(scene_infos) >= settings.scene_count
        and all(
            s.narration
            and s.audio_url
            and len(s.image_urls) >= settings.images_per_scene
            for s in scene_infos[: settings.scene_count]
        )
    )

    return RunStateResponse(
        run_id=run_id,
        status=RunStatus.DONE if complete else RunStatus.FAILED,
        stage=RunStage.IMAGE if cover_image_url or any(s.image_urls for s in scene_infos) else RunStage.LLM,
        story_title=story_title,
        cover_image_url=cover_image_url,
        cover_audio_url=cover_audio_url,
        scenes=[s.to_scenario_info() for s in scene_infos],
        error=None if complete else "서버가 재시작되어 파일에서 가능한 결과만 복구했습니다.",
    )


def _load_scene_infos(run_id: str, run_dir: Path, story_data: dict) -> list[SceneInfo]:
    story_scenes = {
        int(scene.get("scene_no")): scene
        for scene in story_data.get("scenes", [])
        if str(scene.get("scene_no", "")).isdigit()
    }

    scenes: list[SceneInfo] = []
    for scene_no in range(1, settings.scene_count + 1):
        raw = story_scenes.get(scene_no, {})
        scenes.append(
            SceneInfo(
                scene_no=scene_no,
                narration=str(raw.get("narration") or ""),
                dialogue=str(raw.get("dialogue") or ""),
                narration_emotion=str(raw.get("narration_emotion") or ""),
                dialogue_emotion=str(raw.get("dialogue_emotion") or ""),
                image_urls=_scene_image_urls(run_id, run_dir, scene_no),
                audio_url=_scene_audio_url(run_id, run_dir, scene_no),
                image_delay=_scene_image_delay(run_dir, scene_no),
            )
        )
    return scenes


def _scene_image_urls(run_id: str, run_dir: Path, scene_no: int) -> list[str]:
    images_dir = run_dir / "images"
    if not images_dir.exists():
        return []

    pattern = f"scene_{scene_no:02d}_img_*.png"
    files = sorted(images_dir.glob(pattern), key=lambda path: _image_index(path.name))
    return [_asset_url(run_id, "images", path.name) for path in files]


def _scene_audio_url(run_id: str, run_dir: Path, scene_no: int) -> str:
    filename = f"scene_{scene_no:02d}.wav"
    return _asset_url(run_id, "audio", filename) if (run_dir / "audio" / filename).exists() else ""


def _scene_image_delay(run_dir: Path, scene_no: int) -> int:
    """WAV 재생시간 / 3 반올림. 파일 없거나 읽기 실패 시 1."""
    path = run_dir / "audio" / f"scene_{scene_no:02d}.wav"
    if not path.exists():
        return 1
    try:
        with wave.open(str(path), "rb") as f:
            duration = f.getnframes() / f.getframerate()
        return max(1, round(duration / 3))
    except Exception:
        return 1


def _image_index(filename: str) -> int:
    match = re.search(r"_img_(\d+)\.png$", filename)
    return int(match.group(1)) if match else 0


def _asset_url(run_id: str, kind: str, filename: str) -> str:
    return f"/api/runs/{run_id}/{kind}/{filename}"


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
