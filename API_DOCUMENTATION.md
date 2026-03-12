# Storybook Generation API Documentation

이 문서는 현재 코드베이스의 FastAPI 서버([server.py](/c:/Users/user/Desktop/make_story/server.py))를 기준으로 작성한 API 명세서입니다.

## Overview

- Base URL: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`
- Content type:
  - JSON API: `application/json`
  - STT 업로드: `multipart/form-data`
  - 진행 이벤트: `text/event-stream`

## Constraints

- 한 번에 하나의 스토리 생성 작업만 실행할 수 있습니다.
- 새 작업 생성 중 다른 작업이 실행 중이면 `503`을 반환합니다.
- 생성 결과는 실행별 디렉터리에 저장되며, 이미지와 오디오는 별도 다운로드 엔드포인트로 접근합니다.

## Data Models

### Status

- `QUEUED`: 작업 생성 직후, 대기 상태
- `RUNNING`: 파이프라인 실행 중
- `DONE`: 전체 완료
- `FAILED`: 실패

### Stage

- `LLM`: 스토리 구조 생성
- `COVER`: 표지 이미지 생성
- `PANEL_1`
- `PANEL_2`
- `PANEL_3`
- `PANEL_4`
- `TTS`: 오디오 생성 마무리 단계

### PageInfo

```json
{
  "page": 0,
  "title": "표지 제목",
  "summary": "",
  "image_url": "/api/runs/20260312_143000_ab12cd/images/cover.png",
  "audio_url": "/api/runs/20260312_143000_ab12cd/audio/page_0.wav"
}
```

- `page`: `0`부터 `4`까지
- `title`: 보통 표지 페이지에서 사용
- `summary`: 본문 페이지 요약 텍스트
- `image_url`: 이미지 다운로드 상대 경로
- `audio_url`: 오디오 다운로드 상대 경로

## Endpoints

### 1. Root / Health Check

- Method: `GET`
- Path: `/`

정적 프론트엔드 파일이 있으면 `index.html`을 반환하고, 없으면 헬스체크 JSON을 반환합니다.

예시 응답:

```json
{
  "status": "ok",
  "version": "2.0.0"
}
```

### 2. Field STT

- Method: `POST`
- Path: `/api/stt/field`
- Content-Type: `multipart/form-data`

폼 필드:

- `audio_file`: 업로드 파일, 필수
- `field_type`: `era | place | characters | topic`
- `language`: 선택, 기본값 `ko-KR`

예시 `curl`:

```bash
curl -X POST "http://127.0.0.1:8000/api/stt/field" \
  -F "audio_file=@sample.webm" \
  -F "field_type=topic" \
  -F "language=ko-KR"
```

성공 응답:

```json
{
  "stt_text": "용감한 토끼의 모험",
  "parsed_value": "용감한 토끼의 모험",
  "confidence": 0.93
}
```

오류 조건:

- `400`: 빈 파일, 잘못된 `field_type`, 파일 읽기 실패
- `500`: Whisper 처리 또는 오디오 변환 실패

### 3. Create Run

- Method: `POST`
- Path: `/api/runs`
- Content-Type: `application/json`

요청 본문:

```json
{
  "era_ko": "조선 시대",
  "place_ko": "한양",
  "characters_ko": "호기심 많은 아이와 말하는 호랑이",
  "topic_ko": "서로를 믿는 우정",
  "tts_enabled": true
}
```

필드 설명:

- `era_ko`: 시대
- `place_ko`: 장소
- `characters_ko`: 등장인물
- `topic_ko`: 주제
- `tts_enabled`: 오디오 생성 여부, 기본값 `true`

성공 응답:

```json
{
  "run_id": "20260312_143000_ab12cd"
}
```

상태 코드:

- `201`: 생성 성공
- `503`: 다른 작업이 이미 실행 중
- `422`: 요청 바디 검증 실패

### 4. Get Run State

- Method: `GET`
- Path: `/api/runs/{run_id}`

성공 응답:

```json
{
  "status": "RUNNING",
  "stage": "PANEL_2",
  "ready_max_page": 1,
  "ready_max_audio_page": 0,
  "pages": [
    {
      "page": 0,
      "title": "달빛 아래 작은 약속",
      "summary": "",
      "image_url": "/api/runs/20260312_143000_ab12cd/images/cover.png",
      "audio_url": "/api/runs/20260312_143000_ab12cd/audio/page_0.wav"
    },
    {
      "page": 1,
      "title": "",
      "summary": "아이는 달빛이 비추는 골목에서 길 잃은 호랑이를 만났다.",
      "image_url": "/api/runs/20260312_143000_ab12cd/images/panel_1.png",
      "audio_url": ""
    },
    {
      "page": 2,
      "title": "",
      "summary": "",
      "image_url": "",
      "audio_url": ""
    },
    {
      "page": 3,
      "title": "",
      "summary": "",
      "image_url": "",
      "audio_url": ""
    },
    {
      "page": 4,
      "title": "",
      "summary": "",
      "image_url": "",
      "audio_url": ""
    }
  ],
  "error": null
}
```

응답 필드:

- `status`: `QUEUED | RUNNING | DONE | FAILED`
- `stage`: 현재 파이프라인 단계
- `ready_max_page`: 준비된 마지막 이미지 페이지 번호, 없으면 `-1`
- `ready_max_audio_page`: 준비된 마지막 오디오 페이지 번호, 없으면 `-1`
- `pages`: 항상 길이 5의 배열
- `error`: 실패 시 에러 메시지

오류 조건:

- `404`: 존재하지 않는 `run_id`

### 5. Run Events (SSE)

- Method: `GET`
- Path: `/api/runs/{run_id}/events`
- Response type: `text/event-stream`

실행 상태 변화를 Server-Sent Events로 전달합니다.

이벤트 종류:

- `event: update`
- `event: keepalive`

`update` 예시:

```text
event: update
data: {"status":"RUNNING","stage":"LLM","ready_max_page":-1,"ready_max_audio_page":-1}

event: update
data: {"status":"RUNNING","stage":"PANEL_1","ready_max_page":0,"ready_max_audio_page":1}

event: update
data: {"status":"DONE","stage":"TTS","ready_max_page":4,"ready_max_audio_page":4}
```

실패 시 예시:

```text
event: update
data: {"status":"FAILED","stage":"PANEL_3","ready_max_page":2,"ready_max_audio_page":1,"error":"..."}
```

특징:

- 연결 직후 현재 상태를 한 번 즉시 보냅니다.
- 30초 동안 변경이 없으면 `keepalive` 이벤트를 보냅니다.
- `DONE` 또는 `FAILED` 이벤트를 보내면 스트림이 종료됩니다.

오류 조건:

- `404`: 존재하지 않는 `run_id`

JavaScript 예시:

```javascript
const eventSource = new EventSource("http://127.0.0.1:8000/api/runs/20260312_143000_ab12cd/events");

eventSource.addEventListener("update", (event) => {
  const data = JSON.parse(event.data);
  console.log(data.status, data.stage, data.ready_max_page, data.ready_max_audio_page);

  if (data.status === "DONE" || data.status === "FAILED") {
    eventSource.close();
  }
});
```

### 6. Download Image

- Method: `GET`
- Path: `/api/runs/{run_id}/images/{filename}`

파일 규칙:

- 표지: `cover.png`
- 본문: `panel_1.png` ~ `panel_4.png`

성공 시 `image/png` 파일을 반환합니다.

예시:

```bash
curl "http://127.0.0.1:8000/api/runs/20260312_143000_ab12cd/images/cover.png" --output cover.png
```

오류 조건:

- `400`: `filename`에 `..`, `/`, `\` 포함
- `404`: `run_id` 또는 파일 없음

### 7. Download Audio

- Method: `GET`
- Path: `/api/runs/{run_id}/audio/{filename}`

파일 규칙:

- `page_0.wav` ~ `page_4.wav`

성공 시 `audio/wav` 파일을 반환합니다.

예시:

```bash
curl "http://127.0.0.1:8000/api/runs/20260312_143000_ab12cd/audio/page_0.wav" --output page_0.wav
```

오류 조건:

- `400`: `filename`에 `..`, `/`, `\` 포함
- `404`: `run_id` 또는 파일 없음

## Recommended Client Flow

1. 필요하면 `/api/stt/field`로 입력 텍스트를 만듭니다.
2. `/api/runs`로 생성 작업을 시작합니다.
3. `run_id`를 받아 `/api/runs/{run_id}/events`에 SSE 연결을 엽니다.
4. 진행 상황은 `update` 이벤트로 반영합니다.
5. 최종 결과는 `/api/runs/{run_id}`에서 확인합니다.
6. `pages[].image_url`, `pages[].audio_url`로 결과 파일을 다운로드합니다.

## Error Format

일반적인 오류 응답 형식:

```json
{
  "detail": "error message"
}
```

요청 검증 실패 시 서버는 디버깅을 위해 다음 형식도 반환할 수 있습니다.

```json
{
  "detail": [
    {
      "loc": ["body", "era_ko"],
      "msg": "Field required",
      "type": "missing"
    }
  ],
  "body": "..."
}
```

## Notes

- `pages` 배열은 항상 5개 원소를 가집니다.
- `tts_enabled=false`이면 오디오 URL은 비어 있을 수 있습니다.
- `ready_max_page`, `ready_max_audio_page`는 일부 결과가 먼저 준비되는 점진적 렌더링에 적합합니다.
