# VoxCPM2 TTS

VoxCPM2 기반의 텍스트 음성 변환 프로젝트입니다.  
2B 파라미터, 30개 언어 지원, 48kHz 고음질 출력의 오픈소스 TTS 모델을 쉽게 사용할 수 있도록 기능별 모듈로 구성했습니다.

---

## 요구사항

| 항목 | 버전 |
|------|------|
| Python | 3.10 이상 |
| PyTorch | 2.5.0 이상 |
| CUDA | 12.0 이상 |
| VRAM | 약 8GB |

---

## 설치

```bash
pip install -r requirements.txt
```

`requirements.txt` 내용:
```
voxcpm
soundfile
numpy
torch>=2.5.0
moviepy
```

---

## 프로젝트 구조

```
voxcpm2TTS/
├── config.py               # 공통 설정값
├── model_loader.py         # 모델 싱글톤 로더
├── basic_tts.py            # 기본 TTS
├── voice_design.py         # 보이스 디자인 + 프리셋
├── voice_clone.py          # 목소리 클로닝 (기본 / 스타일 / 울티메이트)
├── streaming_tts.py        # 스트리밍 생성
├── emotion_tts.py          # 감정 표현 TTS (복제 목소리 기반)
├── main.py                 # CLI 통합 진입점
├── reference_speaker.wav   # 복제용 참조 화자 (test.wav에서 추출)
└── outputs/                # 생성된 음성 파일 저장 위치 (자동 생성)
```

---

## 모듈별 상세 설명

### `config.py` — 공통 설정

모든 모듈에서 공유하는 기본 설정값을 관리합니다.

```python
MODEL_ID = "openbmb/VoxCPM2"   # Hugging Face 모델 ID
DEFAULT_CFG_VALUE = 2.0         # Classifier-Free Guidance 기본값
DEFAULT_TIMESTEPS = 10          # 추론 스텝 수 기본값
OUTPUT_DIR = "outputs"          # 출력 파일 저장 디렉토리
```

**설정 변경 방법:**  
`config.py`의 값을 직접 수정하면 모든 모듈에 일괄 적용됩니다.  
예를 들어 `DEFAULT_TIMESTEPS = 30`으로 높이면 품질이 올라가지만 속도가 느려집니다.

---

### `model_loader.py` — 모델 로더

VoxCPM2 모델을 싱글톤 패턴으로 로드합니다.  
모델은 처음 호출 시 한 번만 로드되며, 이후 호출에서는 캐싱된 인스턴스를 반환합니다.

#### 함수

```python
get_model(load_denoiser: bool = False) -> VoxCPM
```

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `load_denoiser` | bool | 노이즈 제거기 함께 로드 여부. 기본값 `False` |

**직접 사용 예:**
```python
from model_loader import get_model

model = get_model()
# 이후 model.generate(...) 직접 호출 가능
```

> 첫 실행 시 Hugging Face에서 모델 가중치를 다운로드하므로 시간이 걸릴 수 있습니다.

---

### `basic_tts.py` — 기본 TTS

텍스트를 음성으로 변환하는 가장 기본적인 기능입니다.  
생성된 WAV 파일은 `outputs/` 폴더에 저장됩니다.

#### 함수

```python
text_to_speech(
    text: str,
    output_filename: str = "output.wav",
    cfg_value: float = 2.0,
    inference_timesteps: int = 10,
) -> str
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `text` | str | 필수 | 변환할 텍스트 |
| `output_filename` | str | `"output.wav"` | 저장 파일명 (`outputs/` 기준) |
| `cfg_value` | float | `2.0` | Guidance 강도. 높을수록 지시에 충실 |
| `inference_timesteps` | int | `10` | 추론 스텝 수. 높을수록 품질↑ 속도↓ |

**반환값:** 저장된 파일의 전체 경로 (`str`)

#### 코드 예시

```python
from basic_tts import text_to_speech

# 기본 사용
path = text_to_speech(
    text="안녕하세요. VoxCPM2 기본 TTS 테스트입니다.",
    output_filename="basic_output.wav",
)
print(path)  # outputs/basic_output.wav

# 품질 높여서 생성 (느려짐)
text_to_speech(
    text="고품질로 생성합니다.",
    output_filename="high_quality.wav",
    cfg_value=3.0,
    inference_timesteps=30,
)
```

#### 직접 실행

```bash
python basic_tts.py
```

---

### `voice_design.py` — 보이스 디자인

텍스트 설명으로 원하는 스타일의 목소리를 새롭게 생성합니다.  
괄호 안의 스타일 설명이 텍스트 앞에 자동으로 붙어 모델에 전달됩니다.  
예: `"(gentle and sweet voice)안녕하세요"`

#### 함수 1: `generate_with_style`

자유롭게 스타일을 직접 입력합니다.

```python
generate_with_style(
    text: str,
    style_description: str,
    output_filename: str = "voice_design.wav",
    cfg_value: float = 2.0,
    inference_timesteps: int = 10,
) -> str
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `text` | str | 필수 | 읽을 텍스트 |
| `style_description` | str | 필수 | 목소리 스타일 설명 (영어 권장) |
| `output_filename` | str | `"voice_design.wav"` | 저장 파일명 |
| `cfg_value` | float | `2.0` | Guidance 강도 |
| `inference_timesteps` | int | `10` | 추론 스텝 수 |

#### 함수 2: `generate_with_preset`

미리 정의된 프리셋 이름으로 빠르게 선택합니다.

```python
generate_with_preset(
    text: str,
    preset: str,
    output_filename: str = "preset_voice.wav",
) -> str
```

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `text` | str | 읽을 텍스트 |
| `preset` | str | 아래 프리셋 키 중 하나 |
| `output_filename` | str | 저장 파일명 |

#### 내장 프리셋 목록 (`STYLE_PRESETS`)

| 프리셋 키 | 설명 |
|-----------|------|
| `young_woman_sweet` | 부드럽고 달콤한 젊은 여성 목소리 |
| `deep_male` | 깊고 권위 있는 남성 목소리 |
| `cheerful` | 활기차고 명랑한 목소리 |
| `calm_male` | 차분하고 안정적인 남성 목소리 |
| `elderly_woman` | 따뜻하고 친절한 노년 여성 목소리 |

#### 코드 예시

```python
from voice_design import generate_with_style, generate_with_preset

# 자유 스타일 입력
generate_with_style(
    text="안녕하세요, 보이스 디자인 테스트입니다.",
    style_description="A young woman, gentle and sweet voice",
    output_filename="my_voice.wav",
)

# 프리셋 사용
generate_with_preset(
    text="프리셋 목소리 테스트입니다.",
    preset="deep_male",
    output_filename="deep_male_test.wav",
)
```

> 원하는 결과가 나오지 않으면 1~3번 재생성해 보세요. 스타일 설명은 영어로 입력할 때 가장 안정적입니다.

#### 직접 실행

```bash
python voice_design.py
```

---

### `voice_clone.py` — 목소리 클로닝

실제 사람의 WAV 파일을 참조하여 해당 목소리로 텍스트를 읽어줍니다.  
3단계 방식 중 선택할 수 있으며, 위로 갈수록 간단하고 아래로 갈수록 품질이 높습니다.

> 참조 WAV 파일이 없으면 `FileNotFoundError`가 발생합니다.

---

#### 함수 1: `clone_basic` — 기본 클로닝

가장 간단한 클로닝입니다. 참조 파일의 목소리 톤을 복제합니다.

```python
clone_basic(
    text: str,
    reference_wav_path: str,
    output_filename: str = "cloned.wav",
) -> str
```

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `text` | str | 생성할 텍스트 |
| `reference_wav_path` | str | 참조 목소리 WAV 파일 경로 |
| `output_filename` | str | 저장 파일명 |

```python
from voice_clone import clone_basic

clone_basic(
    text="이 목소리는 참조 파일을 기반으로 생성되었습니다.",
    reference_wav_path="speaker.wav",
    output_filename="clone_basic.wav",
)
```

---

#### 함수 2: `clone_with_style` — 스타일 제어 클로닝

참조 목소리를 복제하면서 추가로 스타일(속도, 톤 등)을 조절합니다.

```python
clone_with_style(
    text: str,
    reference_wav_path: str,
    style_description: str,
    output_filename: str = "cloned_styled.wav",
    cfg_value: float = 2.0,
    inference_timesteps: int = 10,
) -> str
```

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `text` | str | 생성할 텍스트 |
| `reference_wav_path` | str | 참조 목소리 WAV 파일 경로 |
| `style_description` | str | 스타일 조절 설명 (영어 권장) |
| `output_filename` | str | 저장 파일명 |
| `cfg_value` | float | Guidance 강도 |
| `inference_timesteps` | int | 추론 스텝 수 |

```python
from voice_clone import clone_with_style

clone_with_style(
    text="조금 빠르고 명랑하게 말합니다.",
    reference_wav_path="speaker.wav",
    style_description="slightly faster, cheerful tone",
    output_filename="clone_styled.wav",
)
```

**스타일 설명 예시:**
- `"slightly faster, cheerful tone"` — 약간 빠르고 명랑하게
- `"slow and calm"` — 느리고 차분하게
- `"whispering"` — 속삭이는 톤
- `"energetic and loud"` — 활기차고 크게

---

#### 함수 3: `clone_ultimate` — 울티메이트 클로닝

참조 오디오의 텍스트 대본까지 함께 제공하여 가장 높은 품질로 복제합니다.

```python
clone_ultimate(
    text: str,
    reference_wav_path: str,
    prompt_text: str,
    output_filename: str = "ultimate_cloned.wav",
) -> str
```

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `text` | str | 생성할 텍스트 |
| `reference_wav_path` | str | 참조 목소리 WAV 파일 경로 |
| `prompt_text` | str | 참조 오디오에서 말하는 내용의 정확한 대본 |
| `output_filename` | str | 저장 파일명 |

```python
from voice_clone import clone_ultimate

clone_ultimate(
    text="울티메이트 방식으로 복제된 목소리입니다.",
    reference_wav_path="speaker.wav",
    prompt_text="참조 오디오에서 이 사람이 실제로 말하는 내용입니다.",
    output_filename="clone_ultimate.wav",
)
```

> `prompt_text`는 참조 오디오의 내용과 최대한 정확히 일치할수록 품질이 좋아집니다.

#### 직접 실행

`voice_clone.py` 하단의 `REF = "speaker.wav"` 경로를 실제 참조 파일로 수정한 뒤:

```bash
python voice_clone.py
```

---

### `streaming_tts.py` — 스트리밍 TTS

텍스트를 청크 단위로 나눠 순차적으로 생성합니다.  
긴 텍스트나 실시간 응답이 필요한 서비스에 적합합니다.  
모든 청크가 완료되면 하나의 WAV 파일로 합쳐서 저장합니다.

#### 함수

```python
generate_streaming(
    text: str,
    output_filename: str = "streaming.wav",
    on_chunk=None,
) -> str
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `text` | str | 필수 | 변환할 텍스트 |
| `output_filename` | str | `"streaming.wav"` | 저장 파일명 |
| `on_chunk` | callable | `None` | 청크마다 호출되는 콜백 함수. `np.ndarray`를 인자로 받음 |

**반환값:** 저장된 파일 경로 (`str`)

#### 코드 예시

```python
from streaming_tts import generate_streaming

# 기본 사용
generate_streaming(
    text="스트리밍 방식으로 생성합니다. 긴 텍스트도 끊김 없이 처리됩니다.",
    output_filename="stream_output.wav",
)

# 청크 콜백 활용 (예: 실시간 재생 처리)
def play_chunk(chunk):
    # 실시간으로 오디오 스트림에 청크를 전송하는 로직
    print(f"  → 재생 중: {len(chunk)} 샘플")

generate_streaming(
    text="콜백으로 각 청크를 실시간 처리합니다.",
    output_filename="stream_callback.wav",
    on_chunk=play_chunk,
)
```

#### 직접 실행

```bash
python streaming_tts.py
```

---

### `main.py` — CLI 통합 진입점

모든 기능을 커맨드라인에서 바로 사용할 수 있는 통합 인터페이스입니다.

#### 모드별 사용법

**기본 TTS (`basic`)**

```bash
python main.py basic --text "텍스트를 입력하세요" [--output 파일명.wav] [--cfg 2.0] [--steps 10]
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--text` | 필수 | 변환할 텍스트 |
| `--output` | `output.wav` | 저장 파일명 |
| `--cfg` | `2.0` | Guidance 강도 |
| `--steps` | `10` | 추론 스텝 수 |

```bash
python main.py basic --text "안녕하세요" --output hello.wav --steps 20
```

---

**보이스 디자인 (`design`)**

`--style` 또는 `--preset` 중 하나를 반드시 지정해야 합니다.

```bash
# 자유 스타일 입력
python main.py design --text "안녕하세요" --style "deep, calm male voice" --output styled.wav

# 프리셋 사용
python main.py design --text "안녕하세요" --preset young_woman_sweet --output preset.wav
```

사용 가능한 프리셋: `young_woman_sweet`, `deep_male`, `cheerful`, `calm_male`, `elderly_woman`

---

**목소리 클로닝 (`clone`)**

`--prompt-text` 유무와 `--style` 유무에 따라 자동으로 클로닝 방식이 선택됩니다.

```bash
# 기본 클로닝
python main.py clone --text "생성할 텍스트" --ref speaker.wav --output cloned.wav

# 스타일 제어 클로닝
python main.py clone --text "생성할 텍스트" --ref speaker.wav --style "slow and calm" --output styled_clone.wav

# 울티메이트 클로닝 (최고 품질)
python main.py clone --text "생성할 텍스트" --ref speaker.wav --prompt-text "참조 오디오 대본" --output ultimate.wav
```

| 옵션 | 필수 여부 | 설명 |
|------|-----------|------|
| `--text` | 필수 | 생성할 텍스트 |
| `--ref` | 필수 | 참조 WAV 파일 경로 |
| `--style` | 선택 | 스타일 설명 (지정 시 스타일 클로닝) |
| `--prompt-text` | 선택 | 참조 오디오 대본 (지정 시 울티메이트 클로닝) |
| `--output` | 선택 | 저장 파일명 (기본: `cloned.wav`) |

---

**스트리밍 (`stream`)**

```bash
python main.py stream --text "긴 텍스트를 입력하면 청크 단위로 생성됩니다." --output stream.wav
```

---

## 출력 파일

모든 음성 파일은 `outputs/` 폴더에 저장됩니다.  
폴더가 없으면 자동으로 생성됩니다.

```
outputs/
├── basic_output.wav
├── voice_design.wav
├── cloned.wav
├── streaming.wav
└── ...
```

---

## 파라미터 튜닝 가이드

| 목표 | 권장 설정 |
|------|-----------|
| 빠른 테스트 | `cfg_value=1.5`, `inference_timesteps=5` |
| 기본 품질 (기본값) | `cfg_value=2.0`, `inference_timesteps=10` |
| 높은 품질 | `cfg_value=2.5`, `inference_timesteps=20~30` |
| 최고 품질 | `cfg_value=3.0`, `inference_timesteps=50` |

---

---

### `emotion_tts.py` — 감정 표현 TTS

`reference_speaker.wav`(test.wav에서 추출한 화자)의 목소리를 복제하면서 원하는 감정을 담아 음성을 생성합니다.

#### 내장 감정 프리셋 (`EMOTION_PRESETS`)

| 감정 키 | 스타일 설명 |
|--------|------------|
| `기쁨` | joyful, bright, warm, smiling voice, upbeat |
| `슬픔` | slow, sorrowful, melancholy, tearful, heavy voice |
| `분노` | intense, forceful, stern, angry, raised voice |
| `신남` | energetic, enthusiastic, excited, fast-paced, lively |
| `차분` | slow, calm, peaceful, gentle, relaxed, steady |
| `두려움` | trembling, hesitant, nervous, quiet, shaky voice |
| `놀람` | sharp, surprised, astonished, wide-eyed voice |
| `속삭임` | whispering, very soft, hushed, intimate voice |
| `자신감` | confident, clear, strong, assertive voice |
| `그리움` | nostalgic, longing, wistful, emotional voice |

#### 함수 1: `generate_emotion` — 단일 감정 생성

```python
generate_emotion(
    text: str,
    emotion: str,
    reference_wav_path: str = "reference_speaker.wav",
    output_filename: str = None,
    cfg_value: float = 2.0,
    inference_timesteps: int = 10,
) -> str
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `text` | str | 필수 | 읽을 텍스트 |
| `emotion` | str | 필수 | 감정 이름(프리셋 키) 또는 자유 영어 설명 |
| `reference_wav_path` | str | `"reference_speaker.wav"` | 참조 화자 WAV 경로 |
| `output_filename` | str | `None` (자동) | 저장 파일명 |
| `cfg_value` | float | `2.0` | Guidance 강도 |
| `inference_timesteps` | int | `10` | 추론 스텝 수 |

```python
from emotion_tts import generate_emotion

# 프리셋 감정 사용
generate_emotion(
    text="오늘 정말 좋은 하루였어요!",
    emotion="기쁨",
    output_filename="happy_test.wav",
)

# 자유 감정 설명 사용 (영어)
generate_emotion(
    text="그때가 정말 그리워요.",
    emotion="nostalgic, slow, emotional, gentle voice",
    output_filename="custom_emotion.wav",
)
```

#### 함수 2: `batch_emotions` — 여러 감정 한꺼번에 생성

동일한 텍스트를 지정한 모든 감정으로 한번에 생성합니다. 감정 비교에 유용합니다.

```python
batch_emotions(
    text: str,
    emotions: list = None,       # None이면 전체 프리셋 10개
    reference_wav_path: str = "reference_speaker.wav",
    cfg_value: float = 2.0,
    inference_timesteps: int = 10,
) -> dict  # {감정: 저장경로}
```

```python
from emotion_tts import batch_emotions

# 일부 감정만 선택
results = batch_emotions(
    text="안녕하세요, 반갑습니다.",
    emotions=["기쁨", "슬픔", "분노", "차분"],
)
for emotion, path in results.items():
    print(f"{emotion}: {path}")

# 전체 감정 생성 (emotions=None)
batch_emotions(text="테스트 문장입니다.")
```

#### 함수 3: `list_emotions` — 감정 목록 출력

```python
from emotion_tts import list_emotions
list_emotions()
```

#### 직접 실행

```bash
python emotion_tts.py
```

#### CLI (`main.py`) 사용법

```bash
# 감정 목록 확인
python main.py emotion --list

# 단일 감정 생성
python main.py emotion --text "오늘 정말 행복해요!" --emotion 기쁨
python main.py emotion --text "그때가 그리워요." --emotion 그리움 --output nostalgia.wav

# 자유 감정 설명 (영어)
python main.py emotion --text "테스트입니다." --emotion "soft, whispering, calm voice"

# 여러 감정 배치 생성
python main.py emotion --text "안녕하세요." --batch

# 다른 참조 파일 사용
python main.py emotion --text "테스트입니다." --emotion 기쁨 --ref other_speaker.wav
```

---

## 주의사항

- 참조 WAV 파일은 깨끗한 단일 화자 음성일수록 클로닝 품질이 좋아집니다.
- 보이스 디자인 / 스타일 설명은 **영어**로 입력할 때 더 안정적입니다.
- 원하는 결과가 나오지 않으면 동일한 설정으로 1~3번 재시도해 보세요.
- **절대 금지**: 사칭, 사기, 허위 정보 등 악의적 목적 사용

---

## 관련 링크

- [Hugging Face 모델 페이지](https://huggingface.co/openbmb/VoxCPM2)
- [Hugging Face 라이브 데모](https://huggingface.co/spaces/OpenBMB/VoxCPM-Demo)
- [라이선스: Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0)
