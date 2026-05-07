# AI Story Generator

FastAPI 기반 로컬 동화책 생성 앱입니다. 사용자가 입력한 시대, 장소, 등장인물, 주제를 바탕으로 4개 장면의 동화를 만들고, 표지 이미지, 장면별 이미지 3장, 장면별 TTS 오디오를 생성합니다.

## 주요 기능

- **STT 입력 보조**: Whisper 기반 음성 인식으로 입력 필드 채우기
- **스토리 생성**: llama.cpp CLI와 로컬 GGUF 모델을 사용해 4개 장면 생성
- **이미지 생성**: ComfyUI 워크플로우(`make_panel.json`)로 표지 1장과 장면별 이미지 3장 생성
- **TTS 생성**: voxcpm2 기반 장면별 WAV 오디오 생성. TTS는 항상 실행됩니다.
- **진행 상태 스트리밍**: SSE로 LLM, IMAGE, TTS 단계 진행 상황 전달
- **정적 UI 제공**: `/`에서 `static/index.html` 기반 웹 UI 제공

## 실행 방법

### 전체 실행

Windows에서는 `START_ALL.bat`로 ComfyUI, FastAPI 서버, localtunnel을 함께 실행할 수 있습니다.

```bat
START_ALL.bat
```

실행 후 브라우저에서 접속합니다.

```text
http://127.0.0.1:8000
```

### 수동 실행

가상환경을 활성화한 뒤 의존성을 설치합니다.

```bash
pip install -r requirements.txt
```

ComfyUI를 먼저 실행합니다.

```bash
cd ComfyUI
python main.py
```

별도 터미널에서 FastAPI 서버를 실행합니다.

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API 문서는 다음 주소에서 확인할 수 있습니다.

```text
http://127.0.0.1:8000/docs
```

## API 요약

| Method | Path | 설명 |
| --- | --- | --- |
| `GET` | `/` | 웹 UI 또는 서버 상태 반환 |
| `GET` | `/health` | 헬스 체크 |
| `POST` | `/api/stt/field` | 음성 파일을 입력 필드 텍스트로 변환 |
| `POST` | `/api/runs` | 동화 생성 작업 시작 |
| `GET` | `/api/runs/{run_id}` | 작업 상태 조회 |
| `GET` | `/api/runs/{run_id}/events` | SSE 진행 상태 스트림 |
| `GET` | `/api/runs/{run_id}/story` | 생성된 `story.json` 다운로드 |
| `GET` | `/api/runs/{run_id}/images/{filename}` | PNG 이미지 다운로드 |
| `GET` | `/api/runs/{run_id}/audio/{filename}` | WAV 오디오 다운로드 |

자세한 명세는 [API_DOCUMENTATION.md](API_DOCUMENTATION.md)를 참고하세요.

## 사용 예시

### 동화 생성 요청

```bash
curl -X POST http://127.0.0.1:8000/api/runs \
  -H "Content-Type: application/json" \
  -d '{
    "era_ko": "조선 시대",
    "place_ko": "한양의 작은 서당",
    "characters_ko": "호기심 많은 아이와 말하는 호랑이",
    "topic_ko": "서로를 믿는 우정"
  }'
```

응답:

```json
{
  "run_id": "20260429_173423_d118aa"
}
```

### 진행 상태 조회

```bash
curl http://127.0.0.1:8000/api/runs/20260429_173423_d118aa
```

### SSE 진행 상태 확인

```bash
curl -N http://127.0.0.1:8000/api/runs/20260429_173423_d118aa/events
```

### 결과 다운로드

```bash
curl -o story.json http://127.0.0.1:8000/api/runs/20260429_173423_d118aa/story
curl -o cover.png http://127.0.0.1:8000/api/runs/20260429_173423_d118aa/images/cover.png
curl -o scene_01.wav http://127.0.0.1:8000/api/runs/20260429_173423_d118aa/audio/scene_01.wav
```

## 생성 결과

작업 결과는 `outputs/runs/{run_id}` 아래에 저장됩니다.

```text
outputs/runs/{run_id}/
  story.json
  events.jsonl
  images/
    cover.png
    scene_01_img_01.png
    scene_01_img_02.png
    scene_01_img_03.png
    ...
    scene_04_img_03.png
  audio/
    scene_01.wav
    scene_02.wav
    scene_03.wav
    scene_04.wav
```

## 프로젝트 구조

```text
make_story/
  app/
    main.py                         # FastAPI 앱 진입점
    routers/
      run_router.py                 # 생성 작업, SSE, 파일 다운로드 API
      stt_router.py                 # STT API
    schemas/
      run_schema.py                 # 작업 요청/응답 스키마
      story_schema.py               # LLM story.json 스키마
      stt_schema.py                 # STT 스키마
    jobs/
      story_job.py                  # LLM -> IMAGE -> TTS 파이프라인
    services/
      story_service.py              # 스토리 생성 서비스
      image_service.py              # 이미지 생성 서비스
      tts_service.py                # TTS 생성 서비스
      run_service.py                # 작업 상태 관리
      event_service.py              # SSE 이벤트 버스
      storage_service.py            # 결과 저장
    clients/
      llama_cpp_client.py           # llama.cpp CLI 호출
      comfyui_client.py             # ComfyUI HTTP API 호출
      voxcpm2_client.py             # voxcpm2 TTS 호출
      whisper_client.py             # Whisper STT 호출
  static/
    index.html
    app.js
    style.css
  outputs/runs/                     # 생성 결과
  make_panel.json                   # ComfyUI 워크플로우
  START_ALL.bat                     # Windows 전체 실행 스크립트
  API_DOCUMENTATION.md              # API 명세서
```

## 설정

주요 설정은 [app/core/config.py](app/core/config.py)에 정의되어 있으며 `.env`로 덮어쓸 수 있습니다.

| 설정 | 기본값 | 설명 |
| --- | --- | --- |
| `comfyui_url` | `http://127.0.0.1:8188` | ComfyUI API 주소 |
| `workflow_path` | `make_panel.json` | 이미지 생성 워크플로우 |
| `images_per_scene` | `3` | 장면별 이미지 개수 |
| `scene_count` | `4` | 생성 장면 수 |
| `outputs_dir` | `outputs/runs` | 생성 결과 저장 경로 |
| `whisper_model` | `medium` | STT 모델 |
| `tts_reference_wav` | `voxcpm2TTS/reference_speaker.wav` | TTS 기준 음성 |

## 처리 단계

1. `POST /api/runs` 요청으로 작업 생성
2. LLM이 `story.json` 구조 생성
3. ComfyUI가 표지 1장과 장면별 이미지 3장 생성
4. voxcpm2가 장면별 WAV 오디오 생성
5. 작업 상태가 `DONE`으로 변경

TTS는 선택 옵션이 아니며, 매 작업마다 반드시 생성됩니다.

## 기술 스택

- **Backend**: FastAPI, Uvicorn
- **Realtime**: Server-Sent Events
- **LLM**: llama.cpp, GGUF 모델
- **Image**: ComfyUI
- **TTS**: voxcpm2
- **STT**: Whisper

## 주의 사항

- 작업 상태는 서버 메모리에 저장됩니다. 서버를 재시작하면 기존 `run_id` 상태 조회는 실패할 수 있습니다.
- 생성된 파일은 `outputs/runs/{run_id}`에 남지만, 상태 API는 재시작 후 복원하지 않습니다.
- `max_runs` 설정을 초과하면 오래된 결과 디렉터리가 정리됩니다.
