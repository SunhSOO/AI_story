# AI Story Generator API 명세서

현재 FastAPI 애플리케이션(`app/main.py`) 기준의 API 명세입니다.

## 기본 정보

- API 버전: `3.0.0`
- 기본 URL: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`
- 응답 포맷: JSON, SSE, PNG, WAV
- CORS: 모든 origin, method, header 허용

## 공통 에러 응답

FastAPI 기본 검증 오류:

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "era_ko"],
      "msg": "Field required",
      "input": {}
    }
  ]
}
```

애플리케이션 내부 오류:

```json
{
  "detail": "Internal server error",
  "error": "error message"
}
```

`HTTPException` 오류는 다음 형태입니다.

```json
{
  "detail": "Run 20260429_173423_d118aa not found"
}
```

## 엔드포인트 요약

| Method | Path | 설명 |
| --- | --- | --- |
| `GET` | `/` | 정적 UI(`static/index.html`) 또는 서버 상태 반환 |
| `GET` | `/health` | 헬스 체크 |
| `POST` | `/api/stt/field` | 음성 파일을 특정 입력 필드 텍스트로 변환 |
| `POST` | `/api/runs` | 동화 생성 작업 시작 |
| `GET` | `/api/runs/{run_id}` | 생성 작업 상태 조회 |
| `GET` | `/api/runs/{run_id}/events` | 생성 작업 상태 SSE 스트림 |
| `GET` | `/api/runs/{run_id}/story` | 생성된 원본 story JSON 다운로드 |
| `GET` | `/api/runs/{run_id}/images/{filename}` | 생성 이미지 다운로드 |
| `GET` | `/api/runs/{run_id}/audio/{filename}` | 생성 오디오 다운로드 |

## `GET /`

정적 UI가 있으면 `static/index.html`을 반환합니다. 없으면 JSON 상태를 반환합니다.

### 응답 예시

```json
{
  "status": "ok",
  "version": "3.0.0"
}
```

## `GET /health`

서버 상태 확인용 엔드포인트입니다.

### 응답

```json
{
  "status": "ok"
}
```

## `POST /api/stt/field`

업로드한 음성 파일을 Whisper로 텍스트 변환하고, 특정 입력 필드 값으로 사용할 문자열을 반환합니다.

### Request

Content-Type: `multipart/form-data`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `audio_file` | file | O | 음성 파일. 브라우저에서는 `webm`, `mp4`, `mp3`, `wav` 등이 전달될 수 있음 |
| `field_type` | string | O | 변환 대상 필드. `era`, `place`, `characters`, `topic` 중 하나 |
| `language` | string | X | 언어 코드. 기본값 `ko-KR` |

### 성공 응답

Status: `200 OK`

```json
{
  "stt_text": "조선 시대",
  "parsed_value": "조선 시대",
  "confidence": 0.91
}
```

### 응답 필드

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `stt_text` | string | Whisper 원문 인식 결과 |
| `parsed_value` | string | 입력 필드에 넣을 정리된 값. 현재 구현은 `stt_text.trim()` |
| `confidence` | number | 인식 신뢰도. `0.0` 이상 `1.0` 이하 |

### 에러

- `400 Bad Request`: `field_type` 값이 유효하지 않음
- `400 Bad Request`: 빈 음성 파일
- `500 Internal Server Error`: STT 처리 실패

### curl 예시

```bash
curl -X POST http://127.0.0.1:8000/api/stt/field \
  -F "audio_file=@sample.wav" \
  -F "field_type=topic" \
  -F "language=ko-KR"
```

## `POST /api/runs`

동화 생성 작업을 생성하고 백그라운드 파이프라인을 시작합니다. 파이프라인은 LLM 스토리 생성, 이미지 생성, TTS 생성 순서로 항상 진행됩니다.

### Request

Content-Type: `application/json`

```json
{
  "era_ko": "조선 시대",
  "place_ko": "한양의 작은 서당",
  "characters_ko": "호기심 많은 아이와 말하는 호랑이",
  "topic_ko": "서로를 믿는 우정"
}
```

### 요청 필드

| 필드 | 타입 | 필수 | 기본값 | 설명 |
| --- | --- | --- | --- | --- |
| `era_ko` | string | O | - | 시대 |
| `place_ko` | string | O | - | 장소 |
| `characters_ko` | string | O | - | 등장인물 |
| `topic_ko` | string | O | - | 주제 |

### 성공 응답

Status: `201 Created`

```json
{
  "run_id": "20260429_173423_d118aa"
}
```

### 처리 결과 저장 위치

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
  audio/
    scene_01.wav
    scene_02.wav
    scene_03.wav
    scene_04.wav
```

## `GET /api/runs/{run_id}`

작업의 현재 상태와 생성된 산출물 URL을 조회합니다.

### Path Parameters

| 이름 | 타입 | 설명 |
| --- | --- | --- |
| `run_id` | string | `POST /api/runs`에서 받은 작업 ID |

### 성공 응답

Status: `200 OK`

```json
{
  "run_id": "20260429_173423_d118aa",
  "status": "RUNNING",
  "stage": "IMAGE",
  "story_title": "말하는 호랑이와 작은 약속",
  "cover_image_url": "/api/runs/20260429_173423_d118aa/images/cover.png",
  "scenes": [
    {
      "scene_no": 1,
      "title": "서당 앞의 이상한 발자국",
      "narration": "한양의 작은 서당 앞에 커다란 발자국이 남아 있었습니다.",
      "dialogue": "누가 이렇게 큰 발자국을 남긴 걸까?",
      "emotion": "curious",
      "image_urls": [
        "/api/runs/20260429_173423_d118aa/images/scene_01_img_01.png",
        "/api/runs/20260429_173423_d118aa/images/scene_01_img_02.png",
        "/api/runs/20260429_173423_d118aa/images/scene_01_img_03.png"
      ],
      "audio_url": "/api/runs/20260429_173423_d118aa/audio/scene_01.wav"
    }
  ],
  "error": null
}
```

### 응답 필드

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `run_id` | string | 작업 ID |
| `status` | string | `QUEUED`, `RUNNING`, `DONE`, `FAILED` 중 하나 |
| `stage` | string | 현재 단계. `LLM`, `IMAGE`, `TTS` 중 하나 |
| `story_title` | string | 생성된 동화 제목. LLM 완료 전에는 빈 문자열 |
| `cover_image_url` | string | 표지 이미지 URL. 표지 생성 전에는 빈 문자열 |
| `scenes` | array | 장면 목록. LLM 완료 후 4개 장면으로 채워짐 |
| `error` | string/null | 실패 시 에러 메시지 |

### `scenes[]` 필드

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `scene_no` | number | 장면 번호. `1`부터 `4`까지 |
| `title` | string | 장면 제목 |
| `narration` | string | 내레이션 |
| `dialogue` | string | 장면 대사 |
| `emotion` | string | 감정 코드 |
| `image_urls` | string[] | 장면 이미지 URL 목록. 장면당 최대 3개 |
| `audio_url` | string | 장면 오디오 URL. TTS 단계에서 생성된 뒤 채워짐 |

### 상태 값

| 값 | 설명 |
| --- | --- |
| `QUEUED` | 작업 생성 직후 |
| `RUNNING` | 파이프라인 실행 중 |
| `DONE` | 모든 처리 완료 |
| `FAILED` | 처리 실패 |

### 단계 값

| 값 | 설명 |
| --- | --- |
| `LLM` | 스토리 JSON 생성 중 |
| `IMAGE` | 표지 및 장면 이미지 생성 중 |
| `TTS` | 장면 오디오 생성 중 |

### 감정 코드

`emotion`은 다음 값 중 하나입니다.

```text
happy, sad, curious, surprised, tense, calm, warm, magical
```

### 에러

- `404 Not Found`: 메모리상의 작업 상태가 없음

주의: 작업 상태는 인메모리 레지스트리에 저장됩니다. 서버를 재시작하면 파일이 남아 있어도 `GET /api/runs/{run_id}`는 `404`가 될 수 있습니다.

## `GET /api/runs/{run_id}/events`

작업 진행 상황을 Server-Sent Events(SSE)로 스트리밍합니다.

### 성공 응답

Content-Type: `text/event-stream`

이벤트 타입:

| 이벤트 | 설명 |
| --- | --- |
| `update` | 작업 상태 변경 또는 산출물 생성 알림 |
| `keepalive` | 연결 유지용 빈 이벤트 |

### `update` 이벤트 예시

```text
event: update
data: {"run_id":"20260429_173423_d118aa","status":"RUNNING","stage":"IMAGE","scene_no":1,"images":["scene_01_img_01.png","scene_01_img_02.png","scene_01_img_03.png"]}
```

### `update` data 기본 필드

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `run_id` | string | 작업 ID |
| `status` | string | 현재 작업 상태 |
| `stage` | string | 현재 처리 단계 |

### 상황별 추가 필드

| 필드 | 타입 | 발생 시점 |
| --- | --- | --- |
| `cover_image` | string | 표지 이미지 생성 완료 |
| `scene_no` | number | 특정 장면 산출물 생성 완료 |
| `images` | string[] | 특정 장면 이미지 3개 생성 완료 |
| `audio` | string | 특정 장면 오디오 생성 완료 |
| `error` | string | 작업 실패 |

### 브라우저 예시

```js
const source = new EventSource("/api/runs/20260429_173423_d118aa/events");

source.addEventListener("update", (event) => {
  const data = JSON.parse(event.data);
  console.log(data.status, data.stage);
});
```

### 에러

- `404 Not Found`: 메모리상의 작업 상태가 없음

## `GET /api/runs/{run_id}/story`

생성된 원본 `story.json`을 다운로드합니다. LLM이 만든 제목, 표지 프롬프트, 4개 장면, 장면별 이미지 프롬프트가 포함됩니다.

### 성공 응답

Content-Type: `application/json`

```json
{
  "title": "말하는 호랑이와 작은 약속",
  "cover_prompt": "children's book cover, ...",
  "scenes": [
    {
      "scene_no": 1,
      "title": "서당 앞의 이상한 발자국",
      "narration": "한양의 작은 서당 앞에 커다란 발자국이 남아 있었습니다.",
      "dialogue": "누가 이렇게 큰 발자국을 남긴 걸까?",
      "image_prompts": [
        "watercolor children's book illustration, ...",
        "watercolor children's book illustration, ...",
        "watercolor children's book illustration, ..."
      ],
      "emotion": "curious"
    }
  ]
}
```

### `story.json` 스키마

| 필드 | 타입 | 제약 |
| --- | --- | --- |
| `title` | string | 빈 문자열 불가 |
| `cover_prompt` | string | 빈 문자열 불가 |
| `scenes` | array | 정확히 4개 |

### `scenes[]` 스키마

| 필드 | 타입 | 제약 |
| --- | --- | --- |
| `scene_no` | number | `1` 이상 `4` 이하, 순서대로 증가 |
| `title` | string | 빈 문자열 불가 |
| `narration` | string | 빈 문자열 불가 |
| `dialogue` | string | 빈 문자열 불가 |
| `image_prompts` | string[] | 정확히 3개, 빈 문자열 불가, 한자 포함 불가 |
| `emotion` | string | 허용 감정 코드 중 하나 |

### 에러

- `404 Not Found`: 작업 상태가 없음
- `404 Not Found`: 아직 `story.json`이 생성되지 않음

## `GET /api/runs/{run_id}/images/{filename}`

생성된 PNG 이미지를 반환합니다.

### Path Parameters

| 이름 | 타입 | 설명 |
| --- | --- | --- |
| `run_id` | string | 작업 ID |
| `filename` | string | 이미지 파일명 |

### 파일명

```text
cover.png
scene_01_img_01.png
scene_01_img_02.png
scene_01_img_03.png
scene_02_img_01.png
...
scene_04_img_03.png
```

### 성공 응답

- Status: `200 OK`
- Content-Type: `image/png`
- Header: `Cache-Control: no-store`

### 에러

- `400 Bad Request`: 파일명에 `..`, `/`, `\` 포함
- `404 Not Found`: 이미지 파일 없음

## `GET /api/runs/{run_id}/audio/{filename}`

생성된 WAV 오디오를 반환합니다.

### Path Parameters

| 이름 | 타입 | 설명 |
| --- | --- | --- |
| `run_id` | string | 작업 ID |
| `filename` | string | 오디오 파일명 |

### 파일명

```text
scene_01.wav
scene_02.wav
scene_03.wav
scene_04.wav
```

### 성공 응답

- Status: `200 OK`
- Content-Type: `audio/wav`
- Header: `Cache-Control: no-store`

### 에러

- `400 Bad Request`: 파일명에 `..`, `/`, `\` 포함
- `404 Not Found`: 오디오 파일 없음

## 클라이언트 호출 흐름

1. `POST /api/runs`로 작업 생성
2. 반환된 `run_id`로 `GET /api/runs/{run_id}/events` SSE 연결
3. SSE `update` 이벤트 또는 주기적인 `GET /api/runs/{run_id}`로 진행 상태 갱신
4. `cover_image_url`, `scenes[].image_urls`, `scenes[].audio_url`을 사용해 파일 다운로드
5. `status`가 `DONE`이면 완료, `FAILED`이면 `error` 확인

## curl 예시

### 작업 생성

```bash
curl -X POST http://127.0.0.1:8000/api/runs \
  -H "Content-Type: application/json" \
  -d '{
    "era_ko": "조선 시대",
    "place_ko": "한양",
    "characters_ko": "호기심 많은 아이와 말하는 호랑이",
    "topic_ko": "우정"
  }'
```

### 상태 조회

```bash
curl http://127.0.0.1:8000/api/runs/20260429_173423_d118aa
```

### SSE 확인

```bash
curl -N http://127.0.0.1:8000/api/runs/20260429_173423_d118aa/events
```

### 산출물 다운로드

```bash
curl -o cover.png http://127.0.0.1:8000/api/runs/20260429_173423_d118aa/images/cover.png
curl -o scene_01.wav http://127.0.0.1:8000/api/runs/20260429_173423_d118aa/audio/scene_01.wav
curl -o story.json http://127.0.0.1:8000/api/runs/20260429_173423_d118aa/story
```
