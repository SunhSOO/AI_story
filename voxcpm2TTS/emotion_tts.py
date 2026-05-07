"""감정 표현 TTS: 복제된 목소리로 다양한 감정을 담아 음성을 생성합니다."""
import os
import soundfile as sf
from model_loader import get_model
from config import DEFAULT_CFG_VALUE, DEFAULT_TIMESTEPS, OUTPUT_DIR

# 기본 참조 파일 (test.wav에서 추출한 화자)
DEFAULT_REFERENCE = "reference_speaker.wav"

# 감정별 스타일 프롬프트
EMOTION_PRESETS = {
    "기쁨":    "joyful, bright, warm, smiling voice, upbeat",
    "슬픔":    "sorrowful, melancholy, tearful, heavy voice",
    "분노":    "intense, forceful, stern, angry, raised voice",
    "신남":    "energetic, enthusiastic, excited, fast-paced, lively",
    "차분":    "slow, calm, peaceful, gentle, relaxed, steady",
    "두려움":  "trembling, hesitant, nervous, quiet, shaky voice",
    "놀람":    "astonished",
    "속삭임":  "whispering, very soft, hushed,",
    "자신감":  "confident, clear, strong, assertive voice",
    "그리움":  "nostalgic, longing, wistful, emotional voice",
}


def generate_emotion(
    text: str,
    emotion: str,
    reference_wav_path: str = DEFAULT_REFERENCE,
    output_filename: str = None,
    cfg_value: float = DEFAULT_CFG_VALUE,
    inference_timesteps: int = DEFAULT_TIMESTEPS,
) -> str:
    """
    복제된 목소리로 감정이 담긴 음성을 생성합니다.

    Args:
        text: 읽을 텍스트
        emotion: 감정 이름 (EMOTION_PRESETS 키 또는 자유 영어 설명)
        reference_wav_path: 참조 목소리 WAV 파일 경로
        output_filename: 저장 파일명 (None이면 자동 생성)
        cfg_value: Guidance 강도
        inference_timesteps: 추론 스텝 수

    Returns:
        저장된 파일 경로
    """
    if not os.path.exists(reference_wav_path):
        raise FileNotFoundError(f"참조 파일을 찾을 수 없습니다: {reference_wav_path}")

    # 프리셋 감정이면 영어 프롬프트로 변환, 아니면 그대로 사용
    style = EMOTION_PRESETS.get(emotion, emotion)
    styled_text = f"({style}){text}"

    if output_filename is None:
        safe_emotion = emotion.replace(" ", "_")
        output_filename = f"emotion_{safe_emotion}.wav"

    model = get_model()
    wav = model.generate(
        text=styled_text,
        reference_wav_path=reference_wav_path,
        cfg_value=cfg_value,
        inference_timesteps=inference_timesteps,
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    sf.write(output_path, wav, model.tts_model.sample_rate)
    print(f"[{emotion}] 저장 완료: {output_path}")
    return output_path


def batch_emotions(
    text: str,
    emotions: list = None,
    reference_wav_path: str = DEFAULT_REFERENCE,
    cfg_value: float = DEFAULT_CFG_VALUE,
    inference_timesteps: int = DEFAULT_TIMESTEPS,
) -> dict:
    """
    동일한 텍스트를 여러 감정으로 한꺼번에 생성합니다.

    Args:
        text: 읽을 텍스트
        emotions: 생성할 감정 목록 (None이면 전체 프리셋)
        reference_wav_path: 참조 목소리 WAV 파일 경로
        cfg_value: Guidance 강도
        inference_timesteps: 추론 스텝 수

    Returns:
        {감정: 저장 경로} 딕셔너리
    """
    if emotions is None:
        emotions = list(EMOTION_PRESETS.keys())

    results = {}
    print(f"총 {len(emotions)}개 감정으로 배치 생성 시작")
    print(f"텍스트: {text}\n")

    for emotion in emotions:
        try:
            path = generate_emotion(
                text=text,
                emotion=emotion,
                reference_wav_path=reference_wav_path,
                cfg_value=cfg_value,
                inference_timesteps=inference_timesteps,
            )
            results[emotion] = path
        except Exception as e:
            print(f"[{emotion}] 오류 발생: {e}")
            results[emotion] = None

    print(f"\n배치 생성 완료: {len(results)}개")
    return results


def list_emotions():
    """사용 가능한 감정 프리셋 목록을 출력합니다."""
    print("사용 가능한 감정 프리셋:")
    for i, (emotion, style) in enumerate(EMOTION_PRESETS.items(), 1):
        print(f"  {i:2}. {emotion:6} → {style}")


if __name__ == "__main__":
    list_emotions()
    print()

    # 단일 감정 생성
    generate_emotion(
        text="오늘 정말 좋은 하루였어요. 모든 일이 잘 풀렸어요!",
        emotion="기쁨",
        output_filename="emotion_happy.wav",
    )

    # 여러 감정 비교 생성
    batch_emotions(
        text="안녕하세요, 반갑습니다.",
        emotions=["기쁨", "슬픔", "분노", "차분"],
    )
