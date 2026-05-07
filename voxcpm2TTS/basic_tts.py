"""기본 TTS: 텍스트를 음성으로 변환합니다."""
import os
import soundfile as sf
from model_loader import get_model
from config import DEFAULT_CFG_VALUE, DEFAULT_TIMESTEPS, OUTPUT_DIR


def text_to_speech(
    text: str,
    output_filename: str = "output.wav",
    cfg_value: float = DEFAULT_CFG_VALUE,
    inference_timesteps: int = DEFAULT_TIMESTEPS,
) -> str:
    """
    텍스트를 음성으로 변환하여 WAV 파일로 저장합니다.

    Args:
        text: 변환할 텍스트
        output_filename: 저장할 파일명 (outputs/ 디렉토리 기준)
        cfg_value: Classifier-Free Guidance 강도
        inference_timesteps: 추론 스텝 수

    Returns:
        저장된 파일 경로
    """
    model = get_model()
    wav = model.generate(
        text=text,
        cfg_value=cfg_value,
        inference_timesteps=inference_timesteps,
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    sf.write(output_path, wav, model.tts_model.sample_rate)
    print(f"저장 완료: {output_path}")
    return output_path


if __name__ == "__main__":
    text_to_speech(
        text="(엄마 고래, 차분한 톤)무서워하지 않아도 돼.",
        output_filename="엄마고래.wav",
    )
