"""ComfyUI HTTP API client."""
import json
import re
import time
from pathlib import Path
from typing import Optional

import requests

from app.core.config import settings
from app.core.exceptions import ImageGenError


class ComfyUIClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.comfyui_url).rstrip("/")

    def is_running(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/system_stats", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def queue_prompt(self, workflow: dict) -> str:
        r = requests.post(f"{self.base_url}/prompt", json={"prompt": workflow}, timeout=30)
        r.raise_for_status()
        return r.json()["prompt_id"]

    def get_history(self, prompt_id: str) -> Optional[dict]:
        r = requests.get(f"{self.base_url}/history/{prompt_id}", timeout=10)
        r.raise_for_status()
        history = r.json()
        return history.get(prompt_id)

    def wait_for_completion(self, prompt_id: str, timeout: int | None = None) -> dict:
        effective_timeout = timeout or settings.image_gen_timeout
        deadline = time.time() + effective_timeout
        while time.time() < deadline:
            h = self.get_history(prompt_id)
            if h is not None:
                status = h.get("status", {})
                if status.get("completed") or status.get("status_str") == "error":
                    return h
            time.sleep(2)
        raise ImageGenError(f"ComfyUI prompt {prompt_id} timed out after {effective_timeout}s")

    def download_image(self, filename: str, subfolder: str = "", folder_type: str = "output") -> bytes:
        r = requests.get(
            f"{self.base_url}/view",
            params={"filename": filename, "subfolder": subfolder, "type": folder_type},
            timeout=60,
        )
        r.raise_for_status()
        return r.content

    def free_memory(self, unload_models: bool | None = None) -> bool:
        if unload_models is None:
            unload_models = settings.comfyui_unload_models_after_run
        try:
            r = requests.post(
                f"{self.base_url}/free",
                json={"unload_models": unload_models, "free_memory": True},
                timeout=30,
            )
            return r.status_code == 200
        except Exception:
            return False


def sanitize_prefix(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()) or "scene_img"


def _extract_execution_error(status: dict) -> Optional[dict]:
    for entry in reversed(status.get("messages", [])):
        if isinstance(entry, (list, tuple)) and len(entry) == 2:
            name, data = entry
            if name == "execution_error" and isinstance(data, dict):
                return data
    return None


def _extract_first_image(outputs: dict) -> Optional[dict]:
    for node_out in outputs.values():
        imgs = node_out.get("images")
        if imgs:
            return imgs[0]
    return None


def _find_latest_file(prefix: str, created_after: float) -> Optional[Path]:
    out_dir = settings.comfyui_output_dir
    if not out_dir.exists():
        return None
    candidates = [
        p for p in out_dir.glob(f"{prefix}*")
        if p.is_file()
        and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        and p.stat().st_mtime >= created_after - 1
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def build_api_workflow(workflow: dict, positive_prompt: str, seed: int, filename_prefix: str) -> dict:
    """Convert ComfyUI UI-format workflow to API format and patch prompts/seed."""
    workflow = json.loads(json.dumps(workflow))
    api = {}
    style = settings.comfyui_url  # unused – just loading settings to avoid circular import
    image_style = (
        "watercolor painting, children's book illustration, soft pastel colors, "
        "gentle brush strokes, warm lighting, "
    )
    neg = "low quality, blurry, bad anatomy, extra fingers, text, watermark, nsfw"

    for node in workflow.get("nodes", []):
        nid = str(node.get("id"))
        ntype = node.get("type")
        if not ntype:
            continue

        api_node: dict = {"class_type": ntype, "inputs": {}}
        widgets = node.get("widgets_values", [])

        if ntype == "CLIPTextEncode":
            title = node.get("title", "")
            if title == "PROMPT_POS" or nid == "5":
                api_node["inputs"]["text"] = image_style + positive_prompt
            elif title == "PROMPT_NEG" or nid == "6":
                api_node["inputs"]["text"] = neg
            else:
                api_node["inputs"]["text"] = widgets[0] if widgets else ""
            api_node["inputs"]["clip"] = ["1", 1]

        elif ntype == "KSampler":
            api_node["inputs"].update({
                "seed": seed,
                "control_after_generate": "fixed",
                "steps": 4,
                "cfg": widgets[3] if len(widgets) > 3 else 1,
                "sampler_name": widgets[4] if len(widgets) > 4 else "dpmpp_sde_gpu",
                "scheduler": widgets[5] if len(widgets) > 5 else "karras",
                "denoise": widgets[6] if len(widgets) > 6 else 1,
                "model": ["1", 0],
                "positive": ["5", 0],
                "negative": ["6", 0],
                "latent_image": ["9", 0],
            })

        elif ntype == "CheckpointLoaderSimple":
            api_node["inputs"]["ckpt_name"] = widgets[0] if widgets else "flux1-schnell-fp8.safetensors"

        elif ntype == "EmptyLatentImage":
            api_node["inputs"].update({
                "width": settings.image_width,
                "height": settings.image_height,
                "batch_size": widgets[2] if len(widgets) > 2 else 1,
            })

        elif ntype == "VAEDecode":
            api_node["inputs"].update({"samples": ["12", 0], "vae": ["1", 2]})

        elif ntype == "SaveImage":
            api_node["inputs"].update({"filename_prefix": filename_prefix, "images": ["4", 0]})

        api[nid] = api_node

    return api


def generate_single_image(
    prompt: str,
    seed: int,
    output_path: Path,
    workflow_path: Path,
    client: ComfyUIClient | None = None,
) -> str:
    """Generate one image via ComfyUI and save to output_path. Returns filename."""
    client = client or ComfyUIClient()
    if not client.is_running():
        raise ImageGenError("ComfyUI is not running")

    with open(workflow_path, encoding="utf-8") as f:
        template = json.load(f)

    started_at = time.time()
    prefix = sanitize_prefix(output_path.stem)
    workflow = build_api_workflow(template, prompt, seed, prefix)
    prompt_id = client.queue_prompt(workflow)
    history = client.wait_for_completion(prompt_id)

    status = history.get("status", {})
    if status.get("status_str") == "error":
        err = _extract_execution_error(status)
        msg = f"ComfyUI error at node {err.get('node_id')} ({err.get('node_type')}): {err.get('exception_message')}" if err else "ComfyUI execution error"
        raise ImageGenError(msg)

    img_info = _extract_first_image(history.get("outputs", {}))
    if img_info is None:
        fallback = _find_latest_file(prefix, started_at)
        if fallback is None:
            raise ImageGenError(f"ComfyUI returned no images for prompt_id={prompt_id}")
        image_data = fallback.read_bytes()
    else:
        image_data = client.download_image(img_info["filename"], img_info.get("subfolder", ""), img_info.get("type", "output"))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image_data)
    return output_path.name


def generate_image_bytes(
    prompt: str,
    seed: int,
    stem: str,
    workflow_path: Path,
    client: ComfyUIClient | None = None,
) -> bytes:
    """Generate one image via ComfyUI and return raw PNG bytes (without saving)."""
    client = client or ComfyUIClient()
    if not client.is_running():
        raise ImageGenError("ComfyUI is not running")

    with open(workflow_path, encoding="utf-8") as f:
        template = json.load(f)

    started_at = time.time()
    prefix = sanitize_prefix(stem)
    workflow = build_api_workflow(template, prompt, seed, prefix)
    prompt_id = client.queue_prompt(workflow)
    history = client.wait_for_completion(prompt_id)

    status = history.get("status", {})
    if status.get("status_str") == "error":
        err = _extract_execution_error(status)
        msg = f"ComfyUI error at node {err.get('node_id')} ({err.get('node_type')}): {err.get('exception_message')}" if err else "ComfyUI execution error"
        raise ImageGenError(msg)

    img_info = _extract_first_image(history.get("outputs", {}))
    if img_info is None:
        fallback = _find_latest_file(prefix, started_at)
        if fallback is None:
            raise ImageGenError(f"ComfyUI returned no images for prompt_id={prompt_id}")
        return fallback.read_bytes()

    return client.download_image(img_info["filename"], img_info.get("subfolder", ""), img_info.get("type", "output"))
