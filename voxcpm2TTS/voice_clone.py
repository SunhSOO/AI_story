"""목소리 클로닝: 참조 음성 파일을 기반으로 목소리를 복제합니다."""
import os
import soundfile as sf
from model_loader import get_model
from config import DEFAULT_CFG_VALUE, DEFAULT_TIMESTEPS, OUTPUT_DIR


def clone_basic(
    text: str,
    reference_wav_path: str,
    output_filename: str = "cloned.wav",
) -> str:
    """
    기본 목소리 클로닝.

    Args:
        text: 생성할 텍스트
        reference_wav_path: 참조 목소리 WAV 파일 경로
        output_filename: 저장할 파일명

    Returns:
        저장된 파일 경로
    """
    if not os.path.exists(reference_wav_path):
        raise FileNotFoundError(f"참조 파일을 찾을 수 없습니다: {reference_wav_path}")

    model = get_model()
    wav = model.generate(
        text=text,
        reference_wav_path=reference_wav_path,
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    sf.write(output_path, wav, model.tts_model.sample_rate)
    print(f"저장 완료: {output_path}")
    return output_path


def clone_with_style(
    text: str,
    reference_wav_path: str,
    style_description: str,
    output_filename: str = "cloned_styled.wav",
    cfg_value: float = DEFAULT_CFG_VALUE,
    inference_timesteps: int = DEFAULT_TIMESTEPS,
) -> str:
    """
    스타일 제어와 함께 목소리 클로닝.

    Args:
        text: 생성할 텍스트
        reference_wav_path: 참조 목소리 WAV 파일 경로
        style_description: 스타일 설명 (예: "slightly faster, cheerful tone")
        output_filename: 저장할 파일명
        cfg_value: Guidance 강도
        inference_timesteps: 추론 스텝 수

    Returns:
        저장된 파일 경로
    """
    if not os.path.exists(reference_wav_path):
        raise FileNotFoundError(f"참조 파일을 찾을 수 없습니다: {reference_wav_path}")

    styled_text = f"({style_description}){text}"
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
    print(f"저장 완료: {output_path}")
    return output_path


def clone_ultimate(
    text: str,
    reference_wav_path: str,
    prompt_text: str,
    output_filename: str = "ultimate_cloned.wav",
) -> str:
    """
    울티메이트 클로닝: 참조 오디오 + 대본으로 최고 품질 복제.

    Args:
        text: 생성할 텍스트
        reference_wav_path: 참조 목소리 WAV 파일 경로
        prompt_text: 참조 오디오의 정확한 텍스트 대본
        output_filename: 저장할 파일명

    Returns:
        저장된 파일 경로
    """
    if not os.path.exists(reference_wav_path):
        raise FileNotFoundError(f"참조 파일을 찾을 수 없습니다: {reference_wav_path}")

    model = get_model()
    wav = model.generate(
        text=text,
        prompt_wav_path=reference_wav_path,
        prompt_text=prompt_text,
        reference_wav_path=reference_wav_path,
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    sf.write(output_path, wav, model.tts_model.sample_rate)
    print(f"저장 완료: {output_path}")
    return output_path


if __name__ == "__main__":
    REF = "C:\Users\sunhy\Desktop\voxcpm2TTS\test.wav"  # 참조 파일 경로를 여기에 지정하세요

    # 기본 클로닝
    clone_basic(
        text="기본 클로닝 테스트입니다.",
        reference_wav_path=REF,
        output_filename="clone_basic.wav",
    )

    # 스타일 클로닝
    clone_with_style(
        text="스타일 제어 클로닝 테스트입니다.",
        reference_wav_path=REF,
        style_description="slightly faster, cheerful tone",
        output_filename="clone_styled.wav",
    )

    # 울티메이트 클로닝
    clone_ultimate(
        text="울티메이트 클로닝 테스트입니다.",
        reference_wav_path=REF,
        prompt_text="참조 오디오에서 말하는 내용을 여기에 입력하세요.",
        output_filename="clone_ultimate.wav",
    )
