"""Central configuration loaded from environment variables."""
import random
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _resolve_llama_cli() -> Path:
    candidates = [
        BASE_DIR / "llama.cpp" / "build-cuda-nmake" / "bin" / "llama-cli.exe",
        BASE_DIR / "llama.cpp" / "build" / "bin" / "Release" / "llama-cli.exe",
        BASE_DIR / "llama.cpp" / "build" / "bin" / "llama-cli.exe",
        BASE_DIR / "llama.cpp" / "build" / "bin" / "Debug" / "llama-cli.exe",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return candidates[0]


def _resolve_gguf_model() -> Path:
    preferred = BASE_DIR / "llm_model" / "Qwen3.5-9B-Q8_0.gguf"
    if preferred.is_file():
        return preferred
    model_dir = BASE_DIR / "llm_model"
    candidates = sorted(model_dir.glob("*.gguf"))
    if candidates:
        return candidates[0]
    return preferred


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    llama_cli: Path = _resolve_llama_cli()
    gguf_model: Path = _resolve_gguf_model()
    grammar_file: Path = BASE_DIR / "app" / "prompts" / "story_gbnf_spec.gbnf"
    llm_temp: float = 0.3
    llm_top_p: float = 0.9
    llm_repeat_penalty: float = 1.1
    llm_n_predict: int = 1200
    llm_ctx: int = 4096

    # ComfyUI
    comfyui_url: str = "http://127.0.0.1:8188"
    comfyui_output_dir: Path = BASE_DIR / "ComfyUI" / "output"
    workflow_path: Path = BASE_DIR / "make_panel.json"
    images_per_scene: int = 3
    image_gen_timeout: int = 300

    # voxcpm2 TTS
    voxcpm2_dir: Path = BASE_DIR / "voxcpm2TTS"
    tts_reference_wav: Path = BASE_DIR / "voxcpm2TTS" / "reference_speaker.wav"
    tts_cfg_value: float = 1.0
    tts_timesteps: int = 32

    # Whisper STT
    whisper_model: str = "medium"
    ffmpeg_path: str = r"C:\ffmpeg\bin\ffmpeg.exe"

    # Worker (5080) — LLM + designated images
    worker_url: str = "http://127.0.0.1:8001"

    # Server
    outputs_dir: Path = BASE_DIR / "outputs" / "runs"
    max_runs: int = 100

    # Story pipeline
    scene_count: int = 4
    llm_max_retries: int = 3


settings = Settings()
