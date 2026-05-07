"""VoxCPM2 TTS — 통합 실행 진입점."""
import argparse
from basic_tts import text_to_speech
from voice_design import generate_with_style, generate_with_preset, STYLE_PRESETS
from voice_clone import clone_basic, clone_with_style, clone_ultimate
from streaming_tts import generate_streaming
from emotion_tts import generate_emotion, batch_emotions, list_emotions, EMOTION_PRESETS, DEFAULT_REFERENCE


def parse_args():
    parser = argparse.ArgumentParser(description="VoxCPM2 TTS")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    # 기본 TTS
    basic = subparsers.add_parser("basic", help="기본 TTS")
    basic.add_argument("--text", required=True)
    basic.add_argument("--output", default="output.wav")
    basic.add_argument("--cfg", type=float, default=2.0)
    basic.add_argument("--steps", type=int, default=10)

    # 보이스 디자인
    design = subparsers.add_parser("design", help="보이스 디자인")
    design.add_argument("--text", required=True)
    design_group = design.add_mutually_exclusive_group(required=True)
    design_group.add_argument("--style", help="목소리 스타일 설명 (자유 입력)")
    design_group.add_argument("--preset", choices=list(STYLE_PRESETS.keys()), help="프리셋 선택")
    design.add_argument("--output", default="voice_design.wav")

    # 목소리 클로닝
    clone = subparsers.add_parser("clone", help="목소리 클로닝")
    clone.add_argument("--text", required=True)
    clone.add_argument("--ref", required=True, help="참조 WAV 파일 경로")
    clone.add_argument("--style", default=None, help="스타일 설명 (선택)")
    clone.add_argument("--prompt-text", default=None, help="울티메이트 클로닝용 참조 오디오 대본")
    clone.add_argument("--output", default="cloned.wav")

    # 스트리밍
    stream = subparsers.add_parser("stream", help="스트리밍 TTS")
    stream.add_argument("--text", required=True)
    stream.add_argument("--output", default="streaming.wav")

    # 감정 TTS
    emotion = subparsers.add_parser("emotion", help="감정 표현 TTS (목소리 복제 기반)")
    emotion.add_argument("--text", default=None, help="읽을 텍스트 (--batch 없이 필수)")
    emotion.add_argument("--emotion", default=None, help=f"감정 이름. 사용 가능: {list(EMOTION_PRESETS.keys())}")
    emotion.add_argument("--ref", default=DEFAULT_REFERENCE, help=f"참조 WAV 파일 (기본: {DEFAULT_REFERENCE})")
    emotion.add_argument("--output", default=None, help="저장 파일명 (기본: emotion_감정명.wav)")
    emotion.add_argument("--cfg", type=float, default=2.0)
    emotion.add_argument("--steps", type=int, default=10)
    emotion.add_argument("--batch", action="store_true", help="모든 감정으로 한꺼번에 생성")
    emotion.add_argument("--list", action="store_true", help="사용 가능한 감정 목록 출력")

    return parser.parse_args()


def main():
    args = parse_args()

    if args.mode == "basic":
        text_to_speech(args.text, args.output, args.cfg, args.steps)

    elif args.mode == "design":
        if args.preset:
            generate_with_preset(args.text, args.preset, args.output)
        else:
            generate_with_style(args.text, args.style, args.output)

    elif args.mode == "clone":
        if args.prompt_text:
            clone_ultimate(args.text, args.ref, args.prompt_text, args.output)
        elif args.style:
            clone_with_style(args.text, args.ref, args.style, args.output)
        else:
            clone_basic(args.text, args.ref, args.output)

    elif args.mode == "stream":
        generate_streaming(args.text, args.output)

    elif args.mode == "emotion":
        if args.list:
            list_emotions()
        elif args.batch:
            if not args.text:
                print("오류: --batch 사용 시 --text 가 필요합니다.")
            else:
                batch_emotions(args.text, reference_wav_path=args.ref, cfg_value=args.cfg, inference_timesteps=args.steps)
        else:
            if not args.text or not args.emotion:
                print("오류: --text 와 --emotion 을 모두 지정하세요. (또는 --list / --batch 사용)")
            else:
                generate_emotion(args.text, args.emotion, args.ref, args.output, args.cfg, args.steps)


if __name__ == "__main__":
    main()
