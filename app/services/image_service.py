"""Image generation service: cover(1) + 3 images per scene = 13 total."""
import random
from pathlib import Path

from app.clients.comfyui_client import ComfyUIClient, generate_single_image, generate_image_bytes
from app.core.config import settings
from app.core.exceptions import ImageGenError
from app.schemas.story_schema import SceneSchema


def _cover_image_path(run_dir: Path) -> Path:
    return run_dir / "images" / "cover.png"


def _scene_image_path(run_dir: Path, scene_no: int, img_idx: int) -> Path:
    """Return path: images/scene_01_img_01.png"""
    return run_dir / "images" / f"scene_{scene_no:02d}_img_{img_idx:02d}.png"


def generate_cover_image(
    cover_prompt: str,
    run_dir: Path,
    base_seed: int,
    workflow_path: Path | None = None,
    client: ComfyUIClient | None = None,
) -> str:
    """Generate 1 cover image. Returns filename."""
    wf_path = workflow_path or settings.workflow_path
    client = client or ComfyUIClient()
    output_path = _cover_image_path(run_dir)
    filename = generate_single_image(
        prompt=cover_prompt,
        seed=base_seed,
        output_path=output_path,
        workflow_path=wf_path,
        client=client,
    )
    print(f"[IMAGE] cover → {filename}")
    return filename


def generate_scene_images(
    scene: SceneSchema,
    run_dir: Path,
    base_seed: int,
    workflow_path: Path | None = None,
    client: ComfyUIClient | None = None,
) -> list[str]:
    """Generate IMAGES_PER_SCENE images for a single scene.

    Returns:
        List of saved filenames (relative to run_dir/images/).
    """
    wf_path = workflow_path or settings.workflow_path
    client = client or ComfyUIClient()
    filenames: list[str] = []

    for idx in range(1, settings.images_per_scene + 1):
        output_path = _scene_image_path(run_dir, scene.scene_no, idx)
        seed = base_seed + (scene.scene_no * 10) + idx
        prompt = scene.image_prompts[idx - 1]
        filename = generate_single_image(
            prompt=prompt,
            seed=seed,
            output_path=output_path,
            workflow_path=wf_path,
            client=client,
        )
        filenames.append(filename)
        print(f"[IMAGE] scene {scene.scene_no} img {idx} → {filename}")

    return filenames


def generate_scene_image_at(
    scene: SceneSchema,
    run_dir: Path,
    base_seed: int,
    img_idx: int,
    workflow_path: Path | None = None,
    client: ComfyUIClient | None = None,
) -> str:
    """Generate a single image at img_idx (1-based) for a scene. Returns filename."""
    wf_path = workflow_path or settings.workflow_path
    client = client or ComfyUIClient()
    output_path = _scene_image_path(run_dir, scene.scene_no, img_idx)
    seed = base_seed + (scene.scene_no * 10) + img_idx
    prompt = scene.image_prompts[img_idx - 1]
    filename = generate_single_image(
        prompt=prompt,
        seed=seed,
        output_path=output_path,
        workflow_path=wf_path,
        client=client,
    )
    print(f"[IMAGE] scene {scene.scene_no} img {img_idx} → {filename}")
    return filename


def generate_all_images(
    scenes: list[SceneSchema],
    run_dir: Path,
    workflow_path: Path | None = None,
) -> dict[int, list[str]]:
    """Generate 3 images for each of the 4 scenes.

    Returns:
        {scene_no: [filename, ...]} mapping.
    """
    client = ComfyUIClient()
    if not client.is_running():
        raise ImageGenError("ComfyUI is not running")

    base_seed = random.randint(0, 9_999_999)
    result: dict[int, list[str]] = {}

    for scene in scenes:
        filenames = generate_scene_images(scene, run_dir, base_seed, workflow_path, client)
        result[scene.scene_no] = filenames

    return result
