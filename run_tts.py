import argparse
import re
import sys
from pathlib import Path
from types import SimpleNamespace

AVAILABLE_LANGS = ["en", "ko", "es", "pt", "fr"]
DEFAULT_VOICES = ["M1", "M2", "M3", "M4", "M5", "F1", "F2", "F3", "F4", "F5"]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run TTS from the repo root using ONNX or PyPI backend"
    )
    parser.add_argument(
        "--backend",
        choices=["onnx", "pypi"],
        default="onnx",
        help="Backend to use (default: onnx)",
    )
    parser.add_argument(
        "--lang",
        type=str,
        default="ko",
        choices=AVAILABLE_LANGS,
        help="Language code (default: ko)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.05,
        help="Speech speed (default: 1.05, higher = faster)",
    )
    parser.add_argument(
        "--total-step",
        type=int,
        default=5,
        help="Number of denoising steps (default: 5)",
    )
    parser.add_argument(
        "--text",
        type=str,
        default=(
            "This morning, I took a walk in the park, and the sound of the birds "
            "and the breeze was so pleasant that I stopped for a long time just to listen."
        ),
        help="Text to synthesize",
    )
    parser.add_argument(
        "--voice",
        type=str,
        default="M1",
        help="Voice style name (default: M1)",
    )
    parser.add_argument(
        "--voice-style",
        type=str,
        default=None,
        help="Path to voice style JSON (overrides --voice for ONNX/PyPI)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output WAV path (default: auto from text/voice)",
    )
    parser.add_argument(
        "--save-dir",
        type=str,
        default="results",
        help="Output directory when --output is not set",
    )
    parser.add_argument(
        "--onnx-dir",
        type=str,
        default=None,
        help="Path to ONNX model directory (default: supertonic/assets/onnx)",
    )
    parser.add_argument(
        "--use-gpu", action="store_true", help="Use GPU for ONNX inference"
    )
    return parser.parse_args()


def wrap_text_with_lang(text: str, lang: str) -> str:
    return f"<{lang}>{text}</{lang}>"


def repo_root() -> Path:
    return Path(__file__).resolve().parent


def supertonic_root() -> Path:
    base = repo_root()
    if (base / "assets" / "onnx").exists() and (base / "py").exists():
        return base
    if (base / "supertonic" / "assets" / "onnx").exists():
        return base / "supertonic"
    return base / "supertonic"


def default_onnx_dir() -> Path:
    return supertonic_root() / "assets" / "onnx"


def default_voice_style_path(voice_name: str) -> Path:
    return supertonic_root() / "assets" / "voice_styles" / f"{voice_name}.json"


def sanitize_filename(text: str, max_len: int = 20) -> str:
    prefix = text[:max_len]
    return re.sub(r"[^\w]", "_", prefix, flags=re.UNICODE)


def resolve_voice_label(args) -> str:
    if args.voice_style:
        return Path(args.voice_style).stem
    return args.voice


def build_output_path(args, voice_label: str) -> Path:
    if args.output:
        return Path(args.output)
    base = sanitize_filename(args.text, max_len=20)
    if voice_label:
        base = f"{base}_{voice_label}"
    return Path(args.save_dir) / f"{base}.wav"


def list_voice_names() -> list[str]:
    voice_dir = supertonic_root() / "assets" / "voice_styles"
    if voice_dir.exists():
        names = [p.stem for p in voice_dir.glob("*.json")]
        preferred = [v for v in DEFAULT_VOICES if v in names]
        remaining = sorted(v for v in names if v not in preferred)
        return preferred + remaining
    return DEFAULT_VOICES[:]


def prompt_non_empty(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("빈 값은 입력할 수 없습니다. 다시 입력해주세요.")


def prompt_choice(prompt: str, choices: list[str], default: str) -> str:
    choice_str = "/".join(choices)
    while True:
        value = input(f"{prompt} ({choice_str}, 기본: {default}): ").strip().lower()
        if not value:
            return default
        if value in choices:
            return value
        print("지원하지 않는 값입니다. 다시 입력해주세요.")


def prompt_float(prompt: str, default: float, min_value: float | None = None) -> float:
    while True:
        value = input(f"{prompt} (기본: {default}): ").strip()
        if not value:
            return default
        try:
            parsed = float(value)
        except ValueError:
            print("숫자를 입력해주세요.")
            continue
        if min_value is not None and parsed < min_value:
            print(f"{min_value} 이상으로 입력해주세요.")
            continue
        return parsed


def prompt_int(prompt: str, default: int, min_value: int | None = None) -> int:
    while True:
        value = input(f"{prompt} (기본: {default}): ").strip()
        if not value:
            return default
        try:
            parsed = int(value)
        except ValueError:
            print("정수를 입력해주세요.")
            continue
        if min_value is not None and parsed < min_value:
            print(f"{min_value} 이상으로 입력해주세요.")
            continue
        return parsed


def prompt_voice() -> str:
    voices = list_voice_names()
    print("\n보이스 선택 (숫자 → 스타일)")
    for idx, voice in enumerate(voices, start=1):
        print(f"  {idx}: {voice}")
    while True:
        value = input(f"보이스 번호 입력 (1~{len(voices)}): ").strip()
        try:
            index = int(value)
        except ValueError:
            print("숫자를 입력해주세요.")
            continue
        if 1 <= index <= len(voices):
            return voices[index - 1]
        print("범위를 벗어났습니다. 다시 입력해주세요.")


def prompt_interactive_args() -> SimpleNamespace:
    voice = prompt_voice()
    text = prompt_non_empty("\nTTS 텍스트 입력: ")
    lang = prompt_choice("언어 입력", AVAILABLE_LANGS, default="ko")
    speed = prompt_float("속도 입력", default=1.05, min_value=0.1)
    total_step = prompt_int("스텝수 입력", default=5, min_value=1)
    return SimpleNamespace(
        backend="onnx",
        lang=lang,
        speed=speed,
        total_step=total_step,
        text=text,
        voice=voice,
        voice_style=None,
        output=None,
        save_dir="results",
        onnx_dir=None,
        use_gpu=False,
    )


def run_onnx(args) -> None:
    py_dir = supertonic_root() / "py"
    if str(py_dir) not in sys.path:
        sys.path.insert(0, str(py_dir))

    try:
        import soundfile as sf
        from helper import load_text_to_speech, load_voice_style, timer
    except ImportError as exc:
        raise SystemExit(
            "Missing ONNX dependencies. Install requirements in supertonic/py."
        ) from exc

    onnx_dir = Path(args.onnx_dir) if args.onnx_dir else default_onnx_dir()
    voice_style_path = (
        Path(args.voice_style)
        if args.voice_style
        else default_voice_style_path(args.voice)
    )

    if not onnx_dir.exists():
        raise SystemExit(f"ONNX directory not found: {onnx_dir}")
    if not voice_style_path.exists():
        raise SystemExit(f"Voice style not found: {voice_style_path}")

    text_to_speech = load_text_to_speech(str(onnx_dir), args.use_gpu)
    style = load_voice_style([str(voice_style_path)], verbose=True)

    with timer("Generating speech from text"):
        wav, duration = text_to_speech(
            args.text, args.lang, style, args.total_step, args.speed
        )

    voice_label = resolve_voice_label(args)
    output_path = build_output_path(args, voice_label)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    trim_len = int(text_to_speech.sample_rate * duration[0].item())
    sf.write(str(output_path), wav[0, :trim_len], text_to_speech.sample_rate)
    print(f"\nSaved: {output_path.resolve()}")


def run_pypi(args) -> None:
    try:
        from supertonic import TTS
    except ImportError as exc:
        raise SystemExit(
            "supertonic package not installed. Install with: pip install supertonic"
        ) from exc

    tts = TTS(auto_download=True)
    if args.voice_style:
        voice_style_path = Path(args.voice_style)
        if not voice_style_path.exists():
            raise SystemExit(f"Voice style not found: {voice_style_path}")
        style = tts.get_voice_style_from_path(str(voice_style_path))
    else:
        style = tts.get_voice_style(voice_name=args.voice)

    text = wrap_text_with_lang(args.text, args.lang)
    wav, duration = tts.synthesize(
        text,
        voice_style=style,
        total_steps=args.total_step,
        speed=args.speed,
    )

    voice_label = resolve_voice_label(args)
    output_path = build_output_path(args, voice_label)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tts.save_audio(wav, str(output_path))
    print(f"\nSaved: {output_path.resolve()} ({duration[0]:.2f}s)")


def main() -> None:
    if len(sys.argv) == 1:
        args = prompt_interactive_args()
    else:
        args = parse_args()
    if args.backend == "onnx":
        run_onnx(args)
    else:
        run_pypi(args)


if __name__ == "__main__":
    main()
