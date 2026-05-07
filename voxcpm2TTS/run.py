"""
test.wav 목소리를 참조하여 텍스트 + 감정으로 음성을 생성합니다.
생성된 파일은 outputs/ 폴더에 저장됩니다.
"""
import os
import soundfile as sf
from voxcpm import VoxCPM

REFERENCE = "reference_speaker.wav"
OUTPUT_DIR = "outputs"
MODEL_ID = "openbmb/VoxCPM2"

EMOTIONS = {
    "1": ("기쁨",   "joyful, bright, warm, smiling voice, upbeat"),
    "2": ("슬픔",   "slow, sorrowful, melancholy, tearful, heavy voice"),
    "3": ("분노",   "intense, forceful, stern, angry, raised voice"),
    "4": ("신남",   "energetic, enthusiastic, excited, fast-paced, lively"),
    "5": ("차분",   "slow, calm, peaceful, gentle, relaxed, steady"),
    "6": ("두려움", "trembling, hesitant, nervous, quiet, shaky voice"),
    "7": ("놀람",   "sharp, surprised, astonished, wide-eyed voice"),
    "8": ("속삭임", "whispering, very soft, hushed, intimate voice"),
    "9": ("자신감", "confident, clear, strong, assertive voice"),
    "10":("그리움", "nostalgic, longing, wistful, emotional voice"),
}


def select_emotion() -> tuple[str, str]:
    print("\n── 감정 선택 ──────────────────────")
    for key, (name, _) in EMOTIONS.items():
        print(f"  {key:>2}. {name}")
    print("────────────────────────────────────")

    while True:
        choice = input("번호 입력 (기본값 없음, 번호 선택 필수): ").strip()
        if choice in EMOTIONS:
            name, style = EMOTIONS[choice]
            print(f"선택: {name}")
            return name, style
        print("올바른 번호를 입력하세요.")


def main():
    print("=" * 40)
    print("  VoxCPM2 감정 TTS (test.wav 참조)")
    print("=" * 40)

    # 참조 파일 확인
    if not os.path.exists(REFERENCE):
        print(f"오류: 참조 파일({REFERENCE})이 없습니다.")
        print("test.wav를 먼저 reference_speaker.wav로 변환하세요.")
        return

    # 텍스트 입력
    text = input("\n읽을 텍스트 입력: ").strip()
    if not text:
        print("텍스트를 입력하세요.")
        return

    # 감정 선택
    emotion_name, emotion_style = select_emotion()

    # 출력 파일명
    default_filename = f"output_{emotion_name}.wav"
    filename = input(f"\n저장 파일명 (엔터 = {default_filename}): ").strip()
    if not filename:
        filename = default_filename
    if not filename.endswith(".wav"):
        filename += ".wav"

    # 모델 로드 & 생성
    print(f"\n모델 로딩 중: {MODEL_ID}")
    model = VoxCPM.from_pretrained(MODEL_ID, load_denoiser=False)

    styled_text = f"({emotion_style}){text}"
    print(f"\n생성 중... [{emotion_name}] {text}")

    wav = model.generate(
        text=styled_text,
        reference_wav_path=REFERENCE,
        cfg_value=2.0,
        inference_timesteps=10,
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, filename)
    sf.write(output_path, wav, model.tts_model.sample_rate)

    print(f"\n완료! 저장 위치: {output_path}")


if __name__ == "__main__":
    main()
