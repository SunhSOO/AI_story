"""스트리밍 TTS: 긴 텍스트를 실시간으로 청크 단위 생성합니다."""
import os
import numpy as np
import soundfile as sf
from model_loader import get_model
from config import OUTPUT_DIR


def generate_streaming(
    text: str,
    output_filename: str = "streaming.wav",
    on_chunk=None,
) -> str:
    """
    스트리밍 방식으로 음성을 생성합니다.

    Args:
        text: 변환할 텍스트
        output_filename: 저장할 파일명
        on_chunk: 청크마다 호출되는 콜백 함수 (optional). 인자로 chunk(np.ndarray)를 받습니다.

    Returns:
        저장된 파일 경로
    """
    model = get_model()
    chunks = []

    print("스트리밍 생성 시작...")
    for i, chunk in enumerate(model.generate_streaming(text=text)):
        chunks.append(chunk)
        print(f"  청크 {i + 1} 수신 ({len(chunk)} 샘플)")
        if on_chunk:
            on_chunk(chunk)

    wav = np.concatenate(chunks)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    sf.write(output_path, wav, model.tts_model.sample_rate)
    print(f"저장 완료: {output_path} (총 {len(chunks)}개 청크)")
    return output_path


if __name__ == "__main__":
    generate_streaming(
        text=(
            "스트리밍 TTS 테스트입니다. "
            "VoxCPM2는 긴 텍스트도 실시간으로 청크 단위로 생성할 수 있습니다. "
            "이 방식은 빠른 응답이 필요한 서비스에 적합합니다."
        ),
        output_filename="streaming_test.wav",
    )
