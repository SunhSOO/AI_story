"""보이스 디자인: 텍스트 설명으로 새로운 목소리를 생성합니다."""
import os
import soundfile as sf
from model_loader import get_model
from config import DEFAULT_CFG_VALUE, DEFAULT_TIMESTEPS, OUTPUT_DIR

STYLE_PRESETS = {
    "young_woman_sweet": "A young woman, gentle and sweet voice",
    "deep_male": "deep, authoritative male voice",
    "cheerful": "cheerful, energetic",
    "calm_male": "calm and steady male voice",
    "elderly_woman": "elderly woman, warm and kind voice",
}


def generate_with_style(
    text: str,
    style_description: str,
    output_filename: str = "voice_design.wav",
    cfg_value: float = DEFAULT_CFG_VALUE,
    inference_timesteps: int = DEFAULT_TIMESTEPS,
) -> str:
    """
    목소리 스타일 설명과 함께 음성을 생성합니다.

    Args:
        text: 읽을 텍스트
        style_description: 목소리 스타일 설명 (영어 권장)
        output_filename: 저장할 파일명
        cfg_value: Guidance 강도
        inference_timesteps: 추론 스텝 수

    Returns:
        저장된 파일 경로
    """
    styled_text = f"({style_description}){text}"
    model = get_model()
    wav = model.generate(
        text=styled_text,
        cfg_value=cfg_value,
        inference_timesteps=inference_timesteps,
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    sf.write(output_path, wav, model.tts_model.sample_rate)
    print(f"저장 완료: {output_path}")
    return output_path


def generate_with_preset(
    text: str,
    preset: str,
    output_filename: str = "preset_voice.wav",
) -> str:
    """
    프리셋 이름으로 목소리 스타일을 선택하여 음성을 생성합니다.

    Args:
        text: 읽을 텍스트
        preset: STYLE_PRESETS의 키 이름
        output_filename: 저장할 파일명

    Returns:
        저장된 파일 경로
    """
    if preset not in STYLE_PRESETS:
        raise ValueError(f"알 수 없는 프리셋: '{preset}'. 사용 가능: {list(STYLE_PRESETS.keys())}")
    return generate_with_style(text, STYLE_PRESETS[preset], output_filename)


if __name__ == "__main__":
    # 직접 스타일 설명 사용
    generate_with_style(
        text="안녕하세요, 보이스 디자인 테스트입니다.",
        style_description="A young woman, gentle and sweet voice",
        output_filename="voice_design_test.wav",
    )

    # 프리셋 사용
    generate_with_preset(
        text="프리셋 목소리 테스트입니다.",
        preset="deep_male",
        output_filename="preset_deep_male.wav",
    )
