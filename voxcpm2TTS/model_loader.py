from voxcpm import VoxCPM
from config import MODEL_ID

_model = None


def get_model(load_denoiser: bool = False) -> VoxCPM:
    """모델을 싱글톤으로 로드합니다."""
    global _model
    if _model is None:
        print(f"모델 로딩 중: {MODEL_ID}")
        _model = VoxCPM.from_pretrained(MODEL_ID, load_denoiser=load_denoiser)
        print("모델 로딩 완료")
    return _model
