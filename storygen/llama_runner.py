import subprocess
import sys
from pathlib import Path
from typing import Optional

from .config import (
    GEN_ARGS, GRAMMAR_FILE, LLAMA_CLI, GGUF_MODEL, PROMPT_PATH, USE_GRAMMAR,
    USE_SERVER_MODE, LLAMA_SERVER_URL
)


def _build_command(prompt_path: Path) -> list[str]:
    cmd = [
        str(LLAMA_CLI),
        "-m",
        str(GGUF_MODEL),
        "-f",
        str(prompt_path),
        "--temp",
        str(GEN_ARGS["temp"]),
        "--top-p",
        str(GEN_ARGS["top_p"]),
        "--repeat-penalty",
        str(GEN_ARGS["repeat_penalty"]),
        "-n",
        str(GEN_ARGS["n_predict"]),
    ]

    if USE_GRAMMAR:
        cmd.insert(3, "--grammar-file")
        cmd.insert(4, str(GRAMMAR_FILE))

    return cmd


def run_llama_stream(prompt: str, prompt_path: Optional[Path] = None) -> str:
    """Run LLM generation using server or CLI mode
    
    Tries server mode first, falls back to CLI if server is unavailable
    """
    # Try server mode first if enabled
    if USE_SERVER_MODE:
        try:
            from .llama_server_client import call_llama_server
            
            output = call_llama_server(
                prompt=prompt,
                server_url=LLAMA_SERVER_URL,
                temperature=GEN_ARGS["temp"],
                top_p=GEN_ARGS["top_p"],
                n_predict=GEN_ARGS["n_predict"]
            )
            
            return output
            
        except Exception as e:
            import sys
            print(f"Warning: Server mode failed ({e}), falling back to CLI mode", file=sys.stderr)
            # Fall through to CLI mode
    
    # CLI mode (original implementation)
    return _run_llama_cli(prompt, prompt_path)


def _run_llama_cli(prompt: str, prompt_path: Optional[Path] = None) -> str:
    prompt_file = prompt_path or PROMPT_PATH
    prompt_file.write_text(prompt, encoding="utf-8")

    cmd = _build_command(prompt_file)
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

    assert process.stdout is not None
    assert process.stdin is not None

    full_output = []

    start = -1
    depth = 0
    in_str = False
    esc = False
    json_done = False

    while True:
        ch = process.stdout.read(1)
        if ch == "" and process.poll() is not None:
            break
        if not ch:
            continue

        sys.stdout.write(ch)
        sys.stdout.flush()
        full_output.append(ch)

        if not json_done:
            if start == -1:
                if ch == "{":
                    start = len(full_output) - 1
                    depth = 1
                    in_str = False
                    esc = False
                continue

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

    out = "".join(full_output)

    if process.poll() is None:
        try:
            process.terminate()
        except Exception:
            pass

    return out
