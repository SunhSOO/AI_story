# AGENT.md

# AI Story Generator 개발 에이전트 지침서

## 1. 프로젝트 개요

본 프로젝트는 로컬 기반 AI 동화책 생성 시스템이다.  
사용자의 입력 또는 음성 입력을 기반으로 4개의 장면으로 구성된 동화를 생성하고, 각 장면마다 3장의 이미지를 생성하며, 감정 표현이 가능한 TTS 음성을 함께 생성한다.

기존 레거시 시스템은 단일 이미지 생성, 단순 API 구조, 제한적인 TTS 기능을 중심으로 구성되어 있었으나, 현재 개발 방향은 DGX Spark 기반 고성능 생성 환경과 FastAPI 기반 모듈형 백엔드 구조로 확장하는 것이다.

---

## 2. 핵심 개발 방향

### 2.1 로컬 중심 AI 생성 구조

본 시스템은 외부 클라우드 API 의존도를 최소화하고, 주요 생성 기능을 로컬 또는 자체 서버 환경에서 처리하는 것을 목표로 한다.

주요 로컬 처리 대상은 다음과 같다.

- STT: Whisper 기반 음성 인식
- LLM: llama.cpp 기반 동화 스토리 생성
- Image Generation: ComfyUI 기반 이미지 생성
- TTS: voxcpm2 기반 감정 표현 음성 합성
- API Server: FastAPI 기반 백엔드 서버
- 실시간 상태 전달: SSE 기반 진행상황 스트리밍

---

## 3. 변경된 주요 요구사항

### 3.1 이미지 생성 구조 변경

기존 구조에서는 장면별 단일 이미지 생성 또는 제한된 수량의 이미지 생성이 중심이었다.

현재 구조에서는 다음과 같이 변경한다.

| 항목 | 기존 | 변경 |
|---|---|---|
| 전체 장면 수 | 4장면 | 4장면 유지 |# AGENT.md

# AI Story Generator 개발 에이전트 지침서

## 1. 프로젝트 목적

본 프로젝트는 로컬 기반 AI 동화책 생성 시스템이다.  
사용자 입력 또는 음성 입력을 기반으로 **4개의 장면**을 생성하고, 각 장면마다 **3장의 이미지**와 **감정 표현 TTS 음성**을 생성한다.

기존 레거시 구조는 단일 이미지 생성, 단순 API 구조, 제한적인 TTS 기능 중심이었다.  
현재 개발 방향은 **DGX Spark 기반 이미지 생성 확장**, **FastAPI 모듈형 백엔드**, **GBNF 기반 LLM 출력 고정**, **voxcpm2 감정 TTS**, **개발 과정 MD 보고서화**이다.

---

## 2. 핵심 요구사항

### 2.1 로컬 기반 생성 구조

주요 기능은 외부 클라우드 의존도를 최소화하고 로컬 또는 자체 서버에서 처리한다.

- STT: Whisper 기반 음성 인식
- LLM: llama.cpp 기반 스토리 생성
- LLM 출력 제어: GBNF 기반 JSON 구조 고정
- 이미지 생성: ComfyUI 기반 이미지 생성
- 이미지 생성 환경: DGX Spark 활용
- TTS: voxcpm2 기반 감정 표현 음성 합성
- API 서버: FastAPI 기반 모듈형 백엔드
- 진행상황 전달: SSE 기반 이벤트 스트리밍

---

## 3. 주요 변경사항

| 구분 | 기존 | 변경 |
|---|---|---|
| 장면 수 | 4장면 | 4장면 유지 |
| 이미지 수 | 장면당 1장 중심 | 장면당 3장 |
| 총 이미지 수 | 약 4장 | 총 12장 |
| 이미지 생성 환경 | 일반 CUDA GPU | DGX Spark |
| LLM 출력 | 자유 텍스트 또는 불안정 JSON | GBNF 기반 JSON 고정 |
| TTS | 제한적 한국어 TTS | voxcpm2 감정 표현 TTS |
| API 구조 | 단순 서버 구조 | Router / Service / Client 분리 |
| 개발 문서 | 수동 작성 | Codex Agent가 MD 보고서 작성 |

---

## 4. LLM 출력 고정 규칙

LLM은 llama.cpp를 사용하며, 출력은 반드시 GBNF Grammar로 고정한다.

### 4.1 목적

GBNF를 사용하는 이유는 다음과 같다.

- LLM 출력이 항상 JSON 형식으로 나오도록 제한
- 장면 수 4개 고정
- 장면별 필드 누락 방지
- 이미지 프롬프트와 TTS 감정 태그를 안정적으로 추출
- API 후처리 오류 감소

### 4.2 필수 출력 구조

LLM은 반드시 아래 구조의 JSON만 출력해야 한다.

```json
{
  "title": "동화 제목",
  "scenes": [
    {
      "scene_no": 1,
      "title": "장면 제목",
      "narration": "장면 내레이션",
      "image_prompt": "이미지 생성 프롬프트",
      "emotion": "happy"
    },
    {
      "scene_no": 2,
      "title": "장면 제목",
      "narration": "장면 내레이션",
      "image_prompt": "이미지 생성 프롬프트",
      "emotion": "curious"
    },
    {
      "scene_no": 3,
      "title": "장면 제목",
      "narration": "장면 내레이션",
      "image_prompt": "이미지 생성 프롬프트",
      "emotion": "tense"
    },
    {
      "scene_no": 4,
      "title": "장면 제목",
      "narration": "장면 내레이션",
      "image_prompt": "이미지 생성 프롬프트",
      "emotion": "warm"
    }
  ]
}
```

### 4.3 emotion 허용값

```text
happy
sad
curious
surprised
tense
calm
warm
magical
```

### 4.4 GBNF 파일 위치

```text
app/prompts/story_gbnf_spec.gbnf
```

### 4.5 LLM 관련 구현 규칙

- `story_service.py`는 LLM 결과를 직접 신뢰하지 않는다.
- `llama_cpp_client.py`는 GBNF 파일을 사용하여 llama.cpp를 호출한다.
- LLM 응답은 Pydantic Schema로 2차 검증한다.
- scenes 배열은 반드시 4개여야 한다.
- 각 scene에는 `scene_no`, `title`, `narration`, `image_prompt`, `emotion`이 반드시 있어야 한다.
- JSON 파싱 실패 시 재시도 또는 실패 이벤트를 기록한다.

---


## 5. 이미지 생성 규칙

- 전체 장면 수는 4개로 고정한다.
- 장면당 이미지는 3장 생성한다.
- 총 12장의 이미지를 생성한다.
- 이미지 생성은 ComfyUI API를 통해 수행한다.
- DGX Spark 환경을 활용하여 병렬 생성 또는 큐 기반 생성을 적용한다.
- 각 이미지는 scene 번호와 image index 기준으로 저장한다.

### 파일명 규칙

```text
scene_01_img_01.png
scene_01_img_02.png
scene_01_img_03.png
scene_02_img_01.png
...
scene_04_img_03.png
```

---

## 6. TTS 생성 규칙

- TTS는 voxcpm2를 사용한다.
- 각 장면의 `narration`을 음성으로 변환한다.
- 각 장면의 `emotion` 값을 기반으로 감정 표현을 적용한다.
- 장면별 음성 파일은 1개씩 생성한다.

### 파일명 규칙

```text
scene_01.wav
scene_02.wav
scene_03.wav
scene_04.wav
```

---

## 7. FastAPI 구조 규칙

FastAPI 코드는 책임을 분리하여 작성한다.

```text
app/
├── main.py
├── core/
├── middlewares/
├── routers/
├── schemas/
├── services/
├── clients/
├── jobs/
└── prompts/
```

### 역할 분리

| 영역 | 역할 |
|---|---|
| Router | HTTP 요청/응답 처리 |
| Service | 비즈니스 로직 처리 |
| Client | llama.cpp, ComfyUI, Whisper, voxcpm2 호출 |
| Schema | 요청/응답 데이터 검증 |
| Job | 비동기 작업 및 상태 관리 |
| Middleware | 로깅, 에러 처리, Request ID 관리 |

### 금지 사항

- Router에 모델 호출 로직 작성 금지
- Router에 파일 저장 로직 작성 금지
- Service에 환경변수 하드코딩 금지
- Client에 비즈니스 판단 로직 작성 금지
- LLM 자유 텍스트 출력 허용 금지

---

## 8. API 기본 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/stt/field` | 음성 입력을 텍스트로 변환 |
| POST | `/api/runs` | 동화 생성 작업 시작 |
| GET | `/api/runs/{run_id}` | 작업 상태 조회 |
| GET | `/api/runs/{run_id}/events` | SSE 이벤트 스트림 |
| GET | `/api/runs/{run_id}/story` | 생성된 동화 JSON 조회 |
| GET | `/api/runs/{run_id}/images` | 생성 이미지 목록 조회 |
| GET | `/api/runs/{run_id}/audio` | 생성 음성 목록 조회 |

---

## 9. 출력 저장 구조

```text
outputs/
└── runs/
    └── {run_id}/
        ├── story.json
        ├── images/
        │   ├── scene_01_img_01.png
        │   └── ...
        ├── audio/
        │   ├── scene_01.wav
        │   └── ...
        └── events.jsonl
```

---

## 10. Agent 개발 보고서 작성 규칙

Codex Agent는 개발 관련 보고서를 **Markdown 파일로만 작성**한다.  
보고서는 API 내부 기능으로 만들지 않는다.

### 10.1 보고서 작성 대상

Codex Agent는 다음 내용을 `reports/` 폴더에 `.md` 파일로 작성한다.

- 개발환경 구성 과정
- 필요한 라이브러리 설치 과정
- llama.cpp 빌드 과정
- ComfyUI 실행 환경 구성 과정
- voxcpm2 설치 및 테스트 과정
- FastAPI 서버 실행 과정
- Dockerfile 작성 과정
- Docker 이미지 빌드 과정
- Docker 컨테이너 실행 과정
- 오류 발생 및 해결 과정
- 최종 실행 검증 결과

### 10.2 보고서 파일 예시

```text
reports/
├── 01_environment_setup.md
├── 02_library_installation.md
├── 03_llama_cpp_build.md
├── 04_comfyui_setup.md
├── 05_voxcpm2_setup.md
├── 06_fastapi_server.md
├── 07_docker_build.md
└── 08_troubleshooting.md
```

### 10.3 보고서 작성 형식

각 보고서는 아래 형식을 따른다.

```md
# 보고서 제목

## 1. 목적

## 2. 작업 환경

## 3. 수행 명령어

## 4. 수행 결과

## 5. 발생 오류

## 6. 해결 방법

## 7. 최종 확인 결과
```

### 10.4 보고서 작성 제한

- 보고서는 반드시 `.md` 파일로 작성한다.
- `.docx`, `.pdf`, `.hwp`로 작성하지 않는다.
- 보고서 생성을 위한 FastAPI API를 만들지 않는다.
- `report_router.py`, `report_service.py`는 만들지 않는다.
- 보고서는 개발 기록용 문서로만 관리한다.

---


## 12. 개발 우선순위

```text
1. FastAPI 기본 구조 생성
2. LLM GBNF 출력 고정
3. Story Schema 검증
4. ComfyUI 이미지 생성 연동
5. 장면당 3장 이미지 생성
6. voxcpm2 감정 TTS 연동
7. SSE 진행상황 이벤트 구현
8. Docker 이미지화
9. 개발 보고서 MD 작성
```

---

## 13. 최종 품질 기준

본 프로젝트는 다음 조건을 만족해야 한다.

- LLM 출력이 GBNF 기반 JSON 구조로 고정될 것
- 장면 수가 항상 4개일 것
- 장면당 이미지가 3장 생성될 것
- 총 이미지가 12장 생성될 것
- 각 장면별 TTS 음성이 생성될 것
- FastAPI 구조가 Router / Service / Client로 분리될 것
- SSE로 진행상황을 확인할 수 있을 것
- Docker 이미지로 실행 가능할 것
- 개발 과정은 Codex Agent가 Markdown 보고서로만 정리할 것

| 장면당 이미지 수 | 1장 중심 | 장면당 3장 |
| 총 이미지 수 | 4장 내외 | 총 12장 |
| 이미지 생성 환경 | 일반 CUDA GPU | DGX Spark 기반 고성능 생성 |
| 생성 방식 | 순차 또는 제한적 병렬 | 병렬 생성 및 큐 기반 관리 |

### 3.2 TTS 구조 변경

기존 구조에서는 Supertonic M1 기반 한국어 음성 합성이 중심이었다.

현재 구조에서는 `voxcpm2` TTS 라이브러리를 사용하여 장면별 감정 표현이 가능한 음성 합성 구조로 변경한다.

지원해야 하는 감정 예시는 다음과 같다.

- 기쁨
- 슬픔
- 놀람
- 긴장
- 따뜻함
- 차분함
- 신비로움
- 즐거움

### 3.3 API 구조 변경

기존 구조는 단일 서버 파일 또는 단순 라우팅 구조에 가까웠다.

현재 구조는 FastAPI 기반으로 다음 책임을 분리한다.

- Middleware
- Router
- Service
- Schema
- Core Config
- Model Client
- Job Manager
- Storage Manager
- Event Stream Manager
- Report Generator

---

## 4. 목표 시스템 구조

```text
AI_story/
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   ├── logging.py
│   │   ├── exceptions.py
│   │   └── constants.py
│   │
│   ├── middlewares/
│   │   ├── request_id_middleware.py
│   │   ├── logging_middleware.py
│   │   └── error_handler_middleware.py
│   │
│   ├── routers/
│   │   ├── stt_router.py
│   │   ├── story_router.py
│   │   ├── run_router.py
│   │   ├── image_router.py
│   │   ├── tts_router.py
│   │   └── report_router.py
│   │
│   ├── schemas/
│   │   ├── stt_schema.py
│   │   ├── story_schema.py
│   │   ├── run_schema.py
│   │   ├── image_schema.py
│   │   ├── tts_schema.py
│   │   └── report_schema.py
│   │
│   ├── services/
│   │   ├── stt_service.py
│   │   ├── story_service.py
│   │   ├── image_service.py
│   │   ├── tts_service.py
│   │   ├── run_service.py
│   │   ├── storage_service.py
│   │   ├── event_service.py
│   │   └── report_service.py
│   │
│   ├── clients/
│   │   ├── llama_cpp_client.py
│   │   ├── comfyui_client.py
│   │   ├── whisper_client.py
│   │   └── voxcpm2_client.py
│   │
│   ├── jobs/
│   │   ├── job_manager.py
│   │   ├── image_job.py
│   │   ├── tts_job.py
│   │   └── story_job.py
│   │
│   ├── prompts/
│   │   ├── story_gbnf_spec.gbnf
│   │   ├── story_prompt_template.md
│   │   ├── image_prompt_template.md
│   │   └── tts_emotion_prompt.md
│   │
│   └── reports/
│       ├── report_template.md
│       └── development_log_template.md
│
├── outputs/
│   └── runs/
│       └── {run_id}/
│           ├── story.json
│           ├── images/
│           │   ├── scene_01_img_01.png
│           │   ├── scene_01_img_02.png
│           │   ├── scene_01_img_03.png
│           │   └── ...
│           ├── audio/
│           │   ├── scene_01.wav
│           │   └── ...
│           ├── events.jsonl
│           └── report.md
│
├── tests/
│   ├── test_story_service.py
│   ├── test_image_service.py
│   ├── test_tts_service.py
│   ├── test_run_service.py
│   └── test_api.py
│
├── requirements.txt
├── README.md
├── AGENT.md
└── .env.example