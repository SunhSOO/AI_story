"""TTS generation service using voxcpm2."""
from pathlib import Path

from app.clients.voxcpm2_client import synthesize, synthesize_narration_dialogue
from app.core.exceptions import TTSError
from app.schemas.story_schema import SceneSchema


def _scene_audio_path(run_dir: Path, scene_no: int) -> Path:
    return run_dir / "audio" / f"scene_{scene_no:02d}.wav"


def generate_cover_audio(title: str, run_dir: Path) -> str:
    """Synthesize cover audio (title) and save to run_dir/audio/cover.wav."""
    output_path = run_dir / "audio" / "cover.wav"
    synthesize(text=title, emotion=None, output_path=output_path)
    print(f"[TTS] cover → {output_path.name}")
    return output_path.name


def generate_scene_audio(scene: SceneSchema, run_dir: Path) -> str:
    """Synthesize audio for a single scene and save to run_dir/audio/.

    Returns filename relative to run_dir/audio/.
    """
    output_path = _scene_audio_path(run_dir, scene.scene_no)

    if scene.dialogue:
        synthesize_narration_dialogue(
            narration=scene.narration,
            dialogue=scene.dialogue,
            narration_emotion=None,
            dialogue_emotion=None,
            output_path=output_path,
        )
    else:
        synthesize(text=scene.narration, emotion=None, output_path=output_path)

    print(f"[TTS] scene {scene.scene_no} → {output_path.name}")
    return output_path.name


def generate_all_audio(scenes: list[SceneSchema], run_dir: Path) -> dict[int, str]:
    """Generate audio for all scenes.

    Returns:
        {scene_no: filename} mapping.
    """
    result: dict[int, str] = {}
    for scene in scenes:
        try:
            filename = generate_scene_audio(scene, run_dir)
            result[scene.scene_no] = filename
        except Exception as e:
            raise TTSError(f"TTS failed for scene {scene.scene_no}: {e}") from e
    return result
