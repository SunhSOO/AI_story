from pathlib import Path

# Base directory of the project.
BASE_DIR = Path(__file__).resolve().parent.parent

def _resolve_llama_cli() -> Path:
    candidates = [
        BASE_DIR / "llama.cpp" / "build" / "bin" / "Release" / "llama-cli.exe",
        BASE_DIR / "llama.cpp" / "build" / "bin" / "llama-cli.exe",
        BASE_DIR / "llama.cpp" / "build" / "bin" / "Debug" / "llama-cli.exe",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def _resolve_model() -> Path:
    preferred = BASE_DIR / "llm_model" / "Qwen3-14B-Q8_0.gguf"
    if preferred.is_file():
        return preferred

    model_dir = BASE_DIR / "llm_model"
    candidates = sorted(model_dir.glob("*.gguf"))
    if candidates:
        return candidates[0]

    return preferred


# Paths to llama.cpp binary, model, and grammar.
LLAMA_CLI = _resolve_llama_cli()
MODEL_GGUF = _resolve_model()
GRAMMAR = BASE_DIR / "story_spec.gbnf"

# Generation settings passed through to llama.cpp.
USE_GRAMMAR = True
GEN_ARGS = {
    "temp": 0.2,
    "top_p": 0.9,
    "repeat_penalty": 1.1,
    "n_predict": 500,
}

# Shared file locations.
PROMPT_PATH = BASE_DIR / "_prompt_utf8.txt"
RAW_OUTPUT_PATH = BASE_DIR / "raw_output.txt"
SPEC_OUTPUT_PATH = BASE_DIR / "story_output.json"

# Default seed value used by the story generator.
DEFAULT_BASE_SEED = 31007
