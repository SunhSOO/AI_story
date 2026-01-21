# AI Story Generator - 동화책 생성 API

FastAPI 기반 동화책 생성 백엔드 서버

## 주요 기능

- 🎙️ **음성 인식 (STT)**: Whisper 기반 필드별 음성-텍스트 변환
- 📖 **스토리 생성**: LLM 기반 4컷 동화 자동 생성
- 🎨 **이미지 생성**: ComfyUI 연동 워터컬러 스타일 일러스트
- 🔊 **음성 합성 (TTS)**: Supertonic M1 음성, 한국어
- ⚡ **병렬 처리**: 이미지와 오디오 동시 생성으로 빠른 처리
- 📡 **실시간 업데이트**: SSE를 통한 진행상황 스트리밍

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/stt/field` | 음성 → 텍스트 변환 |
| POST | `/api/runs` | 동화 생성 시작 |
| GET | `/api/runs/{run_id}` | 생성 상태 조회 |
| GET | `/api/runs/{run_id}/events` | SSE 이벤트 스트림 |
| GET | `/api/runs/{run_id}/images/{filename}` | 이미지 다운로드 |
| GET | `/api/runs/{run_id}/audio/{filename}` | 오디오 다운로드 |

## 설치 및 실행

### 사전 요구사항

- Python 3.10+
- CUDA GPU (권장, 이미지 생성용)
- 8GB+ RAM

### 1. 종속성 설치

```bash
pip install -r requirements.txt
```

### 2. 필수 컴포넌트

#### LLM (llama.cpp)
```bash
cd llama.cpp
mkdir build && cd build
cmake ..
cmake --build . --config Release
```

#### ComfyUI
별도 터미널에서 실행:
```bash
cd ComfyUI
python main.py
```

### 3. 서버 실행

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

API 문서: http://localhost:8000/docs

## 사용 예시

### 동화 생성

```bash
curl -X POST http://localhost:8000/api/runs \
  -H "Content-Type: application/json" \
  -d '{
    "era_ko": "현대",
    "place_ko": "숲",
    "characters_ko": "토끼",
    "topic_ko": "우정",
    "tts_enabled": true
  }'
```

응답:
```json
{"run_id": "abc123..."}
```

### 진행상황 확인

```bash
curl http://localhost:8000/api/runs/{run_id}
```

### 결과 다운로드

```bash
curl http://localhost:8000/api/runs/{run_id}/images/cover.png -o cover.png
curl http://localhost:8000/api/runs/{run_id}/audio/page_0.wav -o page_0.wav
```

## 프로젝트 구조

```
make_story/
├── server.py              # FastAPI 메인 서버
├── models.py              # API 데이터 모델
├── run_manager.py         # 실행 상태 관리
├── pipeline/
│   ├── stt.py            # Whisper STT
│   ├── image_gen.py      # ComfyUI 이미지 생성
│   ├── tts_gen.py        # Supertonic TTS
│   └── story_pipeline.py # 통합 파이프라인
├── storygen/             # LLM 스토리 생성
├── make_panel.json       # ComfyUI 워크플로우
└── requirements.txt
```

## 기술 스택

- **백엔드**: FastAPI, Uvicorn
- **STT**: OpenAI Whisper
- **LLM**: llama.cpp (Qwen 모델)
- **이미지**: ComfyUI (Stable Diffusion)
- **TTS**: Supertonic
- **비동기**: asyncio, SSE

## 성능

- LLM: ~30초
- 이미지 5개: ~1-2분
- TTS 5개: ~2-3분
- **총 처리시간**: ~2-3분 (병렬 처리)

## 라이선스

MIT License

## 기여

이슈 및 PR 환영합니다!
