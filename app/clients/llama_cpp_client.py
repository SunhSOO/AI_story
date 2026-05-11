"""llama.cpp CLI client: runs llama-cli subprocess with GBNF grammar."""
import subprocess
import sys
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import LLMError


def _build_cmd(prompt_file: Path, seed: int | None = None) -> list[str]:
    cmd = [
        str(settings.llama_cli),
        "-m", str(settings.gguf_model),
        "--grammar-file", str(settings.grammar_file),
        "-f", str(prompt_file),
        "--temp", str(settings.llm_temp),
        "--top-p", str(settings.llm_top_p),
        "--repeat-penalty", str(settings.llm_repeat_penalty),
        "-n", str(settings.llm_n_predict),
        "-ngl", "99",
        "-c", str(settings.llm_ctx),
    ]
    if seed is not None:
        cmd.extend(["--seed", str(seed)])
    return cmd


def _extract_json(raw: str) -> str:
    start = raw.find("{")
    if start == -1:
        raise LLMError("No JSON object found in LLM output")

    depth = 0
    in_str = False
    esc = False
    for i, ch in enumerate(raw[start:], start=start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return raw[start : i + 1]

    raise LLMError("Incomplete JSON in LLM output")


def call_llama(prompt: str, tmp_prompt_path: Path | None = None, seed: int | None = None) -> str:
    """Run llama.cpp CLI and return the raw JSON string from stdout.

    Args:
        prompt: Full prompt text.
        tmp_prompt_path: Optional override for the temp prompt file path.

    Returns:
        Extracted JSON string.

    Raises:
        LLMError: On subprocess failure or missing JSON.
    """
    prompt_file = tmp_prompt_path or (settings.gguf_model.parent / "_llm_prompt_tmp.txt")
    try:
        prompt_file.write_text(prompt, encoding="utf-8")
    except OSError as e:
        raise LLMError(f"Failed to write prompt file: {e}") from e

    cmd = _build_cmd(prompt_file, seed)

    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except FileNotFoundError as e:
        raise LLMError(f"llama-cli not found at {settings.llama_cli}: {e}") from e

    assert process.stdout is not None
    assert process.stdin is not None

    chunks: list[str] = []
    depth = 0
    in_str = False
    esc = False
    json_done = False
    json_started = False

    while True:
        ch = process.stdout.read(1)
        if ch == "" and process.poll() is not None:
            break
        if not ch:
            continue

        sys.stdout.write(ch)
        sys.stdout.flush()
        chunks.append(ch)

        if json_done:
            continue

        if not json_started:
            if ch == "{":
                json_started = True
                depth = 1
        else:
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        json_done = True
                        try:
                            process.stdin.write("\n/exit\n")
                            process.stdin.flush()
                        except Exception:
                            pass

    if process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
                process.wait(timeout=5)
            except Exception:
                pass

    raw = "".join(chunks)
    return _extract_json(raw)
