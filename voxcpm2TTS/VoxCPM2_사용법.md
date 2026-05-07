# VoxCPM2 사용 가이드

> **VoxCPM2** — 2B 파라미터, 30개 언어 지원, 48kHz 고음질 출력의 오픈소스 TTS 모델  
> 라이선스: Apache-2.0 (상업적 사용 가능)

---

## 시스템 요구사항

| 항목 | 최소 요구사항 |
|------|--------------|
| Python | 3.10 이상 |
| PyTorch | 2.5.0 이상 |
| CUDA | 12.0 이상 |
| VRAM | 약 8GB |

---

## 설치

```bash
pip install voxcpm
```

---

## 기본 사용법

### 1. 기본 TTS (텍스트 → 음성)

```python
from voxcpm import VoxCPM
import soundfile as sf

# 모델 로드
model = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)

# 음성 생성
wav = model.generate(
    text="안녕하세요. VoxCPM2 한국어 TTS 테스트입니다.",
    cfg_value=2.0,
    inference_timesteps=10,
)

# 파일 저장
sf.write("output.wav", wav, model.tts_model.sample_rate)
```

---

### 2. 보이스 디자인 (설명으로 목소리 생성)

괄호 안에 목소리 특성을 설명하면 해당 스타일의 목소리를 생성합니다.

```python
wav = model.generate(
    text="(A young woman, gentle and sweet voice)안녕하세요, VoxCPM2입니다!",
    cfg_value=2.0,
    inference_timesteps=10,
)
sf.write("voice_design.wav", wav, model.tts_model.sample_rate)
```

**스타일 예시:**
- `(A young woman, gentle and sweet voice)` — 부드럽고 달콤한 여성 목소리
- `(deep, authoritative male voice)` — 깊고 권위있는 남성 목소리
- `(cheerful, energetic)` — 활기차고 명랑한 목소리

---

### 3. 목소리 클로닝 (참조 음성으로 복제)

#### 기본 클로닝

```python
wav = model.generate(
    text="이 목소리는 VoxCPM2로 클로닝된 목소리입니다.",
    reference_wav_path="speaker.wav",  # 참조할 목소리 파일
)
sf.write("cloned.wav", wav, model.tts_model.sample_rate)
```

#### 스타일 제어와 함께 클로닝

```python
wav = model.generate(
    text="(slightly faster, cheerful tone)스타일 제어와 함께 클로닝된 목소리입니다.",
    reference_wav_path="speaker.wav",
    cfg_value=2.0,
    inference_timesteps=10,
)
sf.write("cloned_styled.wav", wav, model.tts_model.sample_rate)
```

---

### 4. 울티메이트 클로닝 (최고 품질 복제)

참조 오디오의 텍스트 대본도 함께 제공하여 가장 높은 품질로 클로닝합니다.

```python
wav = model.generate(
    text="울티메이트 클로닝 방식으로 생성된 고품질 음성입니다.",
    prompt_wav_path="speaker_reference.wav",    # 참조 오디오
    prompt_text="참조 오디오의 정확한 텍스트 내용을 여기에 입력하세요.",  # 참조 오디오 대본
    reference_wav_path="speaker_reference.wav",
)
sf.write("ultimate_cloned.wav", wav, model.tts_model.sample_rate)
```

---

### 5. 스트리밍 생성

긴 텍스트를 실시간으로 청크 단위로 생성합니다.

```python
import numpy as np
from voxcpm import VoxCPM
import soundfile as sf

model = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)

chunks = []
for chunk in model.generate_streaming(text="스트리밍 방식으로 음성을 생성합니다. VoxCPM2는 실시간 스트리밍도 지원합니다."):
    chunks.append(chunk)

wav = np.concatenate(chunks)
sf.write("streaming.wav", wav, model.tts_model.sample_rate)
```

---

## 주요 파라미터 설명

| 파라미터 | 설명 | 기본값 |
|---------|------|--------|
| `text` | 생성할 텍스트 (괄호로 스타일 지정 가능) | 필수 |
| `cfg_value` | Classifier-Free Guidance 강도 (높을수록 지시 충실도 ↑) | 2.0 |
| `inference_timesteps` | 추론 스텝 수 (높을수록 품질 ↑, 속도 ↓) | 10 |
| `reference_wav_path` | 목소리 클로닝용 참조 WAV 파일 경로 | None |
| `prompt_wav_path` | 울티메이트 클로닝용 참조 오디오 | None |
| `prompt_text` | 참조 오디오의 텍스트 대본 | None |

---

## 지원 언어 (30개)

한국어, 중국어, 영어, 일본어, 아랍어, 프랑스어, 독일어, 스페인어, 포르투갈어, 러시아어, 이탈리아어, 네덜란드어, 폴란드어, 터키어, 힌디어, 인도네시아어, 말레이어, 태국어, 베트남어, 스웨덴어, 덴마크어, 핀란드어, 노르웨이어, 그리스어, 히브리어, 스와힐리어, 타갈로그어, 버마어, 크메르어, 라오어 + 9개 중국 방언

---

## 파인튜닝

5~10분 분량의 오디오로도 파인튜닝 가능합니다.

### LoRA 파인튜닝 (권장)

```bash
python scripts/train_voxcpm_finetune.py \
    --config_path conf/voxcpm_v2/voxcpm_finetune_lora.yaml
```

---

## 모델 스펙

| 항목 | 내용 |
|------|------|
| 아키텍처 | Tokenizer-free Diffusion Autoregressive |
| 파라미터 수 | 2B |
| 백본 | MiniCPM-4 기반 |
| 오디오 VAE | AudioVAE V2 (16kHz 입력 → 48kHz 출력) |
| 최대 시퀀스 길이 | 8192 토큰 |
| 데이터 타입 | bfloat16 |
| RTF (RTX 4090) | ~0.30 (표준) / ~0.13 (가속) |

---

## 주의사항 및 제한사항

- 보이스 디자인 / 스타일 제어는 원하는 결과를 위해 1~3번 재생성이 필요할 수 있습니다.
- 언어별 성능은 학습 데이터 양에 따라 다를 수 있습니다.
- 매우 길거나 감정 표현이 강한 입력에서 간헐적으로 불안정할 수 있습니다.
- **엄격히 금지**: 사칭, 사기, 허위 정보 생성 등 악의적 목적 사용

---

## 관련 링크

- [Hugging Face 모델 페이지](https://huggingface.co/openbmb/VoxCPM2)
- [Hugging Face 데모](https://huggingface.co/spaces/OpenBMB/VoxCPM-Demo)
- [GitHub 레포지토리](https://github.com/OpenBMB/VoxCPM)
