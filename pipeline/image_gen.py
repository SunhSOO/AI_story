"""
ComfyUI integration for image generation
"""
import json
import random
import time
from pathlib import Path
from typing import Optional
import requests


COMFYUI_URL = "http://127.0.0.1:8188"


class ComfyUIClient:
    """Client for ComfyUI API"""
    
    def __init__(self, base_url: str = COMFYUI_URL):
        self.base_url = base_url
    
    def is_running(self) -> bool:
        """Check if ComfyUI is running"""
        try:
            response = requests.get(f"{self.base_url}/system_stats", timeout=2)
            return response.status_code == 200
        except Exception:
            return False
    
    def queue_prompt(self, workflow: dict) -> str:
        """Queue a prompt workflow
        
        Args:
            workflow: Workflow JSON
        
        Returns:
            Prompt ID
        """
        response = requests.post(
            f"{self.base_url}/prompt",
            json={"prompt": workflow}
        )
        response.raise_for_status()
        result = response.json()
        return result["prompt_id"]
    
    def get_history(self, prompt_id: str) -> Optional[dict]:
        """Get execution history for a prompt
        
        Args:
            prompt_id: Prompt ID
        
        Returns:
            History dict if complete, None if still running
        """
        response = requests.get(f"{self.base_url}/history/{prompt_id}")
        response.raise_for_status()
        history = response.json()
        
        if prompt_id in history:
            return history[prompt_id]
        return None
    
    def wait_for_completion(self, prompt_id: str, timeout: int = 300) -> dict:
        """Wait for prompt to complete
        
        Args:
            prompt_id: Prompt ID
            timeout: Max wait time in seconds
        
        Returns:
            History dict
        
        Raises:
            TimeoutError: If timeout exceeded
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            history = self.get_history(prompt_id)
            if history is not None:
                status = history.get("status", {})
                if status.get("completed", False):
                    return history
            time.sleep(2)
        
        raise TimeoutError(f"Prompt {prompt_id} did not complete within {timeout}s")
    
    def download_image(self, filename: str, subfolder: str = "", folder_type: str = "output") -> bytes:
        """Download generated image
        
        Args:
            filename: Image filename
            subfolder: Subfolder path
            folder_type: Folder type (output/temp/input)
        
        Returns:
            Image bytes
        """
        params = {
            "filename": filename,
            "subfolder": subfolder,
            "type": folder_type
        }
        response = requests.get(f"{self.base_url}/view", params=params)
        response.raise_for_status()
        return response.content


def load_workflow_template(template_path: Path) -> dict:
    """Load workflow JSON template"""
    with open(template_path, "r", encoding="utf-8") as f:
        return json.load(f)


def modify_workflow_for_panel(
    workflow: dict,
    positive_prompt: str,
    seed: int,
    prepend_style: str = "watercolor painting, children's book illustration, "
) -> dict:
    """Modify workflow for a specific panel
    
    Args:
        workflow: Base workflow dict
        positive_prompt: Positive prompt text
        seed: Random seed
        prepend_style: Style to prepend to positive prompt
    
    Returns:
        Modified workflow (API format)
    """
    # Deep copy to avoid modifying original
    workflow = json.loads(json.dumps(workflow))
    
    # ComfyUI API expects workflow in different format than the exported JSON
    # We need to convert from UI format to API format
    # API format: nodes are a dict with node IDs as keys, not an array
    
    api_workflow = {}
    
    # Convert nodes array to API format (dict with node IDs)
    for node in workflow.get("nodes", []):
        node_id = str(node.get("id"))
        node_type = node.get("type")
        
        if not node_type:
            continue
            
        # Build API node structure
        api_node = {
            "class_type": node_type,
            "inputs": {}
        }
        
        # Handle different node types
        if node_type == "CLIPTextEncode":
            # This is a text prompt node
            title = node.get("title", "")
            widgets = node.get("widgets_values", [""])
            
            if title == "PROMPT_POS" or node_id == "5":
                # Positive prompt - prepend style
                full_prompt = prepend_style + positive_prompt
                api_node["inputs"]["text"] = full_prompt
            else:
                # Negative prompt or other
                api_node["inputs"]["text"] = widgets[0] if widgets else ""
            
            # CLIP input connection
            api_node["inputs"]["clip"] = ["1", 1]
            
        elif node_type == "KSampler":
            # Set seed for this node
            widgets = node.get("widgets_values", [])
            api_node["inputs"]["seed"] = seed
            api_node["inputs"]["control_after_generate"] = "fixed"
            api_node["inputs"]["steps"] = widgets[2] if len(widgets) > 2 else 5
            api_node["inputs"]["cfg"] = widgets[3] if len(widgets) > 3 else 1
            api_node["inputs"]["sampler_name"] = widgets[4] if len(widgets) > 4 else "dpmpp_sde_gpu"
            api_node["inputs"]["scheduler"] = widgets[5] if len(widgets) > 5 else "karras"
            api_node["inputs"]["denoise"] = widgets[6] if len(widgets) > 6 else 1
            
            # Connections
            api_node["inputs"]["model"] = ["1", 0]
            api_node["inputs"]["positive"] = ["5", 0]
            api_node["inputs"]["negative"] = ["6", 0]
            api_node["inputs"]["latent_image"] = ["9", 0]
            
        elif node_type == "CheckpointLoaderSimple":
            widgets = node.get("widgets_values", ["flux1-schnell-fp8.safetensors"])
            api_node["inputs"]["ckpt_name"] = widgets[0]
            
        elif node_type == "EmptyLatentImage":
            widgets = node.get("widgets_values", [1024, 1024, 1])
            api_node["inputs"]["width"] = widgets[0]
            api_node["inputs"]["height"] = widgets[1]
            api_node["inputs"]["batch_size"] = widgets[2]
            
        elif node_type == "VAEDecode":
            api_node["inputs"]["samples"] = ["12", 0]
            api_node["inputs"]["vae"] = ["1", 2]
            
        elif node_type == "SaveImage":
            widgets = node.get("widgets_values", ["ComfyUI"])
            api_node["inputs"]["filename_prefix"] = widgets[0]
            api_node["inputs"]["images"] = ["4", 0]
        
        api_workflow[node_id] = api_node
    
    return api_workflow


def generate_panel_image(
    panel_description: str,
    seed: int,
    output_path: Path,
    workflow_path: Path,
    client: Optional[ComfyUIClient] = None
) -> str:
    """Generate image for a panel using ComfyUI
    
    Args:
        panel_description: Description/prompt for the panel
        seed: Random seed
        output_path: Where to save the image
        workflow_path: Path to workflow template JSON
        client: ComfyUI client (creates new if None)
    
    Returns:
        Output filename
    """
    if client is None:
        client = ComfyUIClient()
    
    # Check if ComfyUI is running
    if not client.is_running():
        raise RuntimeError("ComfyUI is not running. Please start ComfyUI first.")
    
    # Load and modify workflow
    workflow = load_workflow_template(workflow_path)
    workflow = modify_workflow_for_panel(workflow, panel_description, seed)
    
    # Queue prompt
    prompt_id = client.queue_prompt(workflow)
    
    # Wait for completion
    history = client.wait_for_completion(prompt_id, timeout=300)
    
    # Extract output image filename
    outputs = history.get("outputs", {})
    for node_id, node_output in outputs.items():
        if "images" in node_output:
            images = node_output["images"]
            if images:
                # Download first image
                image_info = images[0]
                filename = image_info["filename"]
                subfolder = image_info.get("subfolder", "")
                
                image_data = client.download_image(filename, subfolder)
                
                # Save to output path
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(image_data)
                
                return output_path.name
    
    raise RuntimeError("No image generated by ComfyUI")


def generate_story_images(
    cover_title: str,
    panels: list[str],
    output_dir: Path,
    workflow_path: Path
) -> dict[str, str]:
    """Generate all images for a story (cover + 4 panels)
    
    Args:
        cover_title: Cover page title
        panels: List of 4 panel descriptions
        output_dir: Output directory
        workflow_path: Path to workflow template
    
    Returns:
        Dict mapping page number to filename: {0: "cover.png", 1: "panel_1.png", ...}
    """
    client = ComfyUIClient()
    
    # Generate cover with random seed
    base_seed = random.randint(1000000, 9999999)
    
    filenames = {}
    
    # Generate cover (page 0)
    cover_path = output_dir / "cover.png"
    generate_panel_image(cover_title, base_seed, cover_path, workflow_path, client)
    filenames[0] = "cover.png"
    
    # Generate panels 1-4 using same seed
    for i, panel_desc in enumerate(panels, start=1):
        panel_path = output_dir / f"panel_{i}.png"
        generate_panel_image(panel_desc, base_seed, panel_path, workflow_path, client)
        filenames[i] = f"panel_{i}.png"
    
    return filenames
