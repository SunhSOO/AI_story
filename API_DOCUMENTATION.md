# AI Story Generator API 명세서

현재 FastAPI 애플리케이션(`app/main.py`) 기준의 API 명세입니다.

**버전**: 3.0.0  
**최종 수정**: 2026-05-12

## 기본 정보

- 기본 URL (로컬): `http://127.0.0.1:8000`
- 기본 URL (외부): `https://mystorybook.loca.lt`
- Swagger UI: `http://127.0.0.1:8000/docs`
- 응답 포맷: JSON, SSE, PNG, WAV
- CORS: 모든 origin, method, header 허용

---

## 외부 접속 (Localtunnel)

`START_ALL.bat` 실행 시 Localtunnel이 자동으로 시작됩니다.

| 항목 | 값 |
| --- | --- |
| 터널 URL | `https://mystorybook.loca.lt` |
| 마스터 공인 IP | `59.3.103.182` |
| 포트 포워딩 대상 | `localhost:8000` |
| 재연결 | 끊기면 3초 후 자동 재시작 (`start_tunnel.ps1`) |

**브라우저 첫 접속 우회**

```
https://mystorybook.loca.lt/?bypass-tunnel-reminder=true
```

또는 우회 확인 페이지에 공인 IP `59.3.103.182` 입력.

---

## 공통 에러 응답

```json
{ "detail": "Run 20260429_173423_d118aa not found" }
```

검증 오류 (422):

```json
{
  "detail": [
    { "type": "missing", "loc": ["body", "era_ko"], "msg": "Field required", "input": {} }
  ]
}
```

---

## 엔드포인트 요약

| Method | Path | 설명 |
| --- | --- | --- |
| `GET` | `/` | 정적 UI(`static/index.html`) 또는 서버 상태 |
| `GET` | `/health` | 헬스 체크 |
| `POST` | `/api/stt/field` | 음성 파일 → 텍스트 변환 |
| `POST` | `/api/runs` | 동화 생성 작업 시작 |
| `GET` | `/api/runs/{run_id}` | 작업 상태 및 결과물 URL 조회 |
| `GET` | `/api/runs/{run_id}/events` | SSE 실시간 스트림 |
| `GET` | `/api/runs/{run_id}/story` | 원본 story.json 다운로드 |
| `GET` | `/api/runs/{run_id}/images/{filename}` | 생성 이미지 다운로드 |
| `GET` | `/api/runs/{run_id}/audio/{filename}` | 생성 오디오 다운로드 |

---

## `GET /`

정적 UI가 있으면 `static/index.html` 반환. 없으면 JSON 상태 반환.

```json
{ "status": "ok", "version": "3.0.0" }
```

---

## `GET /health`

```json
{ "status": "ok" }
```

---

## `POST /api/stt/field`

업로드한 음성 파일을 Whisper로 텍스트 변환합니다.

### Request

`Content-Type: multipart/form-data`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `audio_file` | file | O | 음성 파일. `webm`, `mp4`, `mp3`, `wav` 등 |
| `field_type` | string | O | `era` / `place` / `characters` / `topic` 중 하나 |
| `language` | string | X | 언어 코드. 기본값 `ko-KR` |

### 성공 응답 (200)

```json
{
  "stt_text": "조선 시대",
  "parsed_value": "조선 시대",
  "confidence": 0.91
}
```

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `stt_text` | string | Whisper 원문 인식 결과 |
| `parsed_value` | string | 정규화된 입력 값 (이 값을 사용하세요) |
| `confidence` | number | 인식 신뢰도. `0.0` ~ `1.0` |

### 에러

| 코드 | 원인 |
| --- | --- |
| `400` | `field_type` 값 무효 또는 빈 음성 파일 |
| `500` | STT 처리 실패 |

---

## `POST /api/runs`

동화 생성 작업을 생성하고 백그라운드 파이프라인을 시작합니다.

파이프라인 구조:
- **Stage 1 (LLM)**: 워커(RTX 5080)에서 스토리 JSON 생성
- **Stage 2 (PARALLEL)**: 워커와 마스터가 병렬 처리
  - 워커: 배치 TTS(cover + 모든 씬 내레이션/대사 분할 생성) → 배정 씬 이미지
  - 마스터(RTX 3080 Ti): 표지 이미지 → 배정 씬 이미지

이미지 분배:

| 처리 위치 | 생성 이미지 |
| --- | --- |
| 워커 (RTX 5080) | `scene_02_img_01.png`, `scene_02_img_02.png`, `scene_03_img_01.png`, `scene_03_img_02.png` |
| 마스터 (RTX 3080 Ti) | `cover.png`, `scene_01_img_01.png`, `scene_01_img_02.png`, `scene_04_img_01.png`, `scene_04_img_02.png` |

> TTS는 워커에서만 수행합니다. 내레이션과 대사가 각각 별도 WAV로 생성됩니다.

### Request

```json
{
  "era_ko": "조선 시대",
  "place_ko": "한양의 작은 서당",
  "characters_ko": "호기심 많은 아이와 말하는 호랑이",
  "topic_ko": "서로를 믿는 우정"
}
```

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `era_ko` | string | O | 시대 |
| `place_ko` | string | O | 장소 |
| `characters_ko` | string | O | 등장인물 |
| `topic_ko` | string | O | 주제 |

### 성공 응답 (201)

```json
{ "run_id": "20260429_173423_d118aa" }
```

### 처리 결과 저장 위치

```
outputs/runs/{run_id}/
  story.json
  events.jsonl
  images/
    cover.png
    scene_01_img_01.png ~ scene_04_img_02.png
  audio/
    cover.wav
    scene_01_0.wav ~ scene_04_0.wav   ← 씬 내레이션 TTS
    scene_01_1.wav ~ scene_04_1.wav   ← 씬 대사 TTS
```

---

## `GET /api/runs/{run_id}`

작업의 현재 상태와 생성된 결과물 URL을 조회합니다.

### 성공 응답 (200)

```json
{
  "run_id": "20260429_173423_d118aa",
  "status": "DONE",
  "stage": "IMAGE",
  "story_title": "말하는 호랑이와 작은 약속",
  "cover": {
    "scene_no": 0,
    "status": "End",
    "scenarios": [
      {
        "index": 0,
        "msg": "",
        "audio_url": "",
        "image_url": "/api/runs/20260429_173423_d118aa/images/cover.png",
        "delay": 0
      },
      {
        "index": 1,
        "msg": "말하는 호랑이와 작은 약속",
        "audio_url": "/api/runs/20260429_173423_d118aa/audio/cover.wav",
        "image_url": "",
        "delay": 0
      }
    ]
  },
  "scenes": [
    {
      "scene_no": 1,
      "status": "End",
      "scenarios": [
        {
          "index": 0,
          "msg": "",
          "audio_url": "",
          "image_url": "/api/runs/20260429_173423_d118aa/images/scene_01_img_01.png",
          "delay": 4
        },
        {
          "index": 1,
          "msg": "한양의 작은 서당 앞에 커다란 발자국이 남아 있었습니다.",
          "audio_url": "/api/runs/20260429_173423_d118aa/audio/scene_01_0.wav",
          "image_url": "",
          "delay": 0
        },
        {
          "index": 2,
          "msg": "",
          "audio_url": "",
          "image_url": "/api/runs/20260429_173423_d118aa/images/scene_01_img_02.png",
          "delay": 4
        },
        {
          "index": 3,
          "msg": "누가 이렇게 큰 발자국을 남긴 걸까?",
          "audio_url": "/api/runs/20260429_173423_d118aa/audio/scene_01_1.wav",
          "image_url": "",
          "delay": 0
        }
      ]
    }
  ],
  "error": null
}
```

### 최상위 응답 필드

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `run_id` | string | 작업 ID |
| `status` | string | `QUEUED` / `RUNNING` / `DONE` / `FAILED` |
| `stage` | string | 현재 단계. `LLM` / `PARALLEL` / `IMAGE` |
| `story_title` | string | 생성된 동화 제목. LLM 완료 전에는 빈 문자열 |
| `cover` | object | 표지 정보 (`SceneScenarioInfo`). 항상 존재 |
| `scenes` | array | 씬 목록. **항상 4개**. LLM 완료 전에는 빈 배열 `[]` |
| `error` | string\|null | 실패 시 에러 메시지 |

### `cover` 필드 구조

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `scene_no` | number | 항상 `0` |
| `status` | string | `Pending` / `Running` / `End` |
| `scenarios` | array | 항상 2개 (index 0, 1) |

Cover `scenarios`:

| index | 포함 데이터 | 설명 |
| --- | --- | --- |
| `0` | `image_url` | 표지 이미지 URL |
| `1` | `msg`, `audio_url` | `msg` = 동화 제목, `audio_url` = 제목 낭독 오디오 |

### `cover.status` 값

| 값 | 조건 |
| --- | --- |
| `Pending` | 이미지·오디오 모두 미생성 |
| `Running` | 일부 생성 완료 |
| `End` | 이미지 + 오디오 모두 완료 |

### `scenes[]` 필드

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `scene_no` | number | 씬 번호. `1` ~ `4` |
| `status` | string | `Pending` / `Running` / `End` |
| `scenarios` | array | 재생 시퀀스. 항상 4개 (index 0~3) |

### `scenarios[]` 필드

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `index` | number | 재생 순서. `0` ~ `3` |
| `msg` | string | 자막 텍스트 |
| `audio_url` | string | 오디오 URL. 빈 문자열이면 미생성 |
| `image_url` | string | 이미지 URL. 빈 문자열이면 미생성 |
| `delay` | number | 이미지 표시 후 대기 시간(초) |

### Scenarios 인덱스별 역할

| index | 포함 데이터 | 설명 |
| --- | --- | --- |
| `0` | `image_url`, `delay` | 첫 번째 이미지 표시 후 delay초 대기 |
| `1` | `msg`, `audio_url` | 내레이션 자막 + `scene_NN_0.wav` 재생 (`delay: 0` = 오디오 완료까지 대기) |
| `2` | `image_url`, `delay` | 두 번째 이미지로 전환 후 delay초 대기 |
| `3` | `msg`, `audio_url` | 대사 자막 + `scene_NN_1.wav` 재생 |

> **delay 계산**: `round(scene_NN_0.wav 재생시간 ÷ 씬당_이미지_수)`. 최솟값 1초.
> **index 3 audio_url**: 대사 오디오(`scene_NN_1.wav`). 비어 있으면 자막만 표시.

### `status` / `stage` 값

| status | 설명 |
| --- | --- |
| `QUEUED` | 작업 생성 직후 |
| `RUNNING` | 파이프라인 실행 중 |
| `DONE` | 모든 처리 완료 |
| `FAILED` | 처리 실패 |

| stage | 설명 |
| --- | --- |
| `LLM` | 워커에서 스토리 JSON 생성 중 |
| `PARALLEL` | TTS + 이미지 병렬 실행 중 |
| `IMAGE` | 최종 완료 상태 또는 파일 복구 상태 |

### 허용 감정 코드 (`dialogue_emotion`)

| 감정 코드 |
| --- |
| `기쁨` |
| `슬픔` |
| `무서움` |

### 에러

- `404 Not Found`: 메모리에 없고 파일에서도 복구 불가

---

## `GET /api/runs/{run_id}/events`

Server-Sent Events로 작업 진행 상황을 스트리밍합니다.

`Content-Type: text/event-stream`

### 이벤트 종류

| 이벤트 | 설명 |
| --- | --- |
| `update` | 상태 변경 또는 미디어 생성 완료 |
| `keepalive` | 30초마다 전송되는 연결 유지 이벤트. data 없음 |

### `update` 이벤트 기본 필드 (항상 포함)

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `run_id` | string | 작업 ID |
| `status` | string | 현재 작업 상태 |
| `stage` | string | 현재 처리 단계 |

### 상황별 추가 필드

| 필드 | 발생 시점 | 설명 |
| --- | --- | --- |
| `cover_image` | 표지 이미지 생성 완료 | 파일명 (예: `cover.png`) |
| `cover_image_url` | 표지 이미지 생성 완료 | 이미지 URL |
| `cover_audio` | 표지 TTS 완료 | 파일명 (예: `cover.wav`) |
| `cover_audio_url` | 표지 TTS 완료 | 오디오 URL |
| `scene_no` | 씬 미디어 이벤트 | 씬 번호 |
| `image` | 씬 이미지 생성 완료 | 파일명 (`scene_no`와 함께) |
| `image_url` | 씬 이미지 생성 완료 | 이미지 URL (`scene_no`와 함께) |
| `audio` | 씬 내레이션 TTS 완료 | 파일명 (`scene_no`와 함께) |
| `audio_url` | 씬 내레이션 TTS 완료 | 오디오 URL (`scene_no`와 함께) |
| `dialogue_audio` | 씬 대사 TTS 완료 | 파일명 (`scene_no`와 함께) |
| `dialogue_audio_url` | 씬 대사 TTS 완료 | 오디오 URL (`scene_no`와 함께) |
| `error` | `status === "FAILED"` | 에러 메시지 |

### 이벤트 흐름 예시

```
event: update
data: {"run_id":"...","status":"RUNNING","stage":"LLM"}

event: update
data: {"run_id":"...","status":"RUNNING","stage":"PARALLEL"}

event: update
data: {"run_id":"...","status":"RUNNING","stage":"PARALLEL","cover_audio":"cover.wav","cover_audio_url":"/api/runs/.../audio/cover.wav"}

event: update
data: {"run_id":"...","status":"RUNNING","stage":"PARALLEL","scene_no":1,"audio":"scene_01_0.wav","audio_url":"/api/runs/.../audio/scene_01_0.wav"}

event: update
data: {"run_id":"...","status":"RUNNING","stage":"PARALLEL","scene_no":1,"dialogue_audio":"scene_01_1.wav","dialogue_audio_url":"/api/runs/.../audio/scene_01_1.wav"}

event: update
data: {"run_id":"...","status":"RUNNING","stage":"PARALLEL","cover_image":"cover.png","cover_image_url":"/api/runs/.../images/cover.png"}

event: update
data: {"run_id":"...","status":"RUNNING","stage":"PARALLEL","scene_no":2,"image":"scene_02_img_01.png","image_url":"/api/runs/.../images/scene_02_img_01.png"}

event: update
data: {"run_id":"...","status":"DONE","stage":"IMAGE"}

event: keepalive
data:
```

### 브라우저 예시

```js
const source = new EventSource("/api/runs/20260429_173423_d118aa/events");

source.addEventListener("update", (e) => {
  const data = JSON.parse(e.data);
  if (data.status === "DONE" || data.status === "FAILED") source.close();
});
```

### 에러

- `404 Not Found`: 작업이 없고 파일에서도 복구 불가

---

## `GET /api/runs/{run_id}/story`

LLM이 생성한 원본 `story.json`을 반환합니다.

`Content-Type: application/json`

```json
{
  "title": "말하는 호랑이와 작은 약속",
  "cover_prompt": "children's book cover, soft watercolor painting, ...",
  "scenes": [
    {
      "scene_no": 1,
      "narration": "한양의 작은 서당 앞에 커다란 발자국이 남아 있었습니다.",
      "dialogue": "누가 이렇게 큰 발자국을 남긴 걸까?",
      "dialogue_emotion": "기쁨",
      "image_prompts": [
        "watercolor children's book illustration, ...",
        "watercolor children's book illustration, ..."
      ]
    }
  ]
}
```

### `story.json` 스키마

| 필드 | 타입 | 제약 |
| --- | --- | --- |
| `title` | string | 빈 문자열 불가 |
| `cover_prompt` | string | 영어. 빈 문자열 불가 |
| `scenes` | array | 정확히 4개 |

### `scenes[]` 스키마

| 필드 | 타입 | 제약 |
| --- | --- | --- |
| `scene_no` | number | `1` ~ `4`, 순서대로 증가 |
| `narration` | string | 한국어. 외국어/한자 자동 제거 |
| `dialogue` | string | 한국어. 외국어/한자 자동 제거 |
| `dialogue_emotion` | string | `기쁨` / `슬픔` / `무서움` 중 하나 |
| `image_prompts` | string[] | 정확히 2개. 영어. 한자 불가 |

### 에러

- `404 Not Found`: 작업이 없거나 `story.json`이 아직 생성되지 않음

---

## `GET /api/runs/{run_id}/images/{filename}`

생성된 PNG 이미지를 반환합니다.

| 항목 | 값 |
| --- | --- |
| Content-Type | `image/png` |
| Cache-Control | `no-store` |

### 파일명 패턴

```
cover.png
scene_01_img_01.png ~ scene_04_img_02.png
```

### 에러

- `400 Bad Request`: 파일명에 `..`, `/`, `\` 포함
- `404 Not Found`: 파일 없음

---

## `GET /api/runs/{run_id}/audio/{filename}`

생성된 WAV 오디오를 반환합니다.

| 항목 | 값 |
| --- | --- |
| Content-Type | `audio/wav` |
| 포맷 | RIFF PCM, 비압축, 모노 |
| Cache-Control | `no-store` |

### 파일명 패턴

```
cover.wav              ← 표지 제목 낭독
scene_01_0.wav         ← 씬 1 내레이션
scene_01_1.wav         ← 씬 1 대사
scene_02_0.wav         ← 씬 2 내레이션
scene_02_1.wav         ← 씬 2 대사
...
scene_04_0.wav         ← 씬 4 내레이션
scene_04_1.wav         ← 씬 4 대사
```

### 에러

- `400 Bad Request`: 파일명에 `..`, `/`, `\` 포함
- `404 Not Found`: 파일 없음

---

## 클라이언트 호출 흐름

1. `POST /api/runs`로 작업 생성 → `run_id` 수신
2. `GET /api/runs/{run_id}/events` SSE 연결 + 1500ms 폴링 병행
3. `scenes.length === 4` 감지 → LLM 완료, 씬 카드 4개 표시
4. 각 씬 `status === "End"` → 해당 씬 재생 가능
5. `status === "DONE"` → 전체 완료

### 진행률 계산

전체 생성 결과물 구성 (앱 기준):

| 분류 | 항목 | 개수 |
| --- | --- | --- |
| 스토리 | story_title 1 + scenes 4 | **5** |
| 이미지 | cover 1 + 씬 이미지 2×4 | **9** |
| 오디오 | cover 1 + 씬 내레이션 4 | **5** |
| **합계** | | **19** |

> 씬 대사 오디오 4개(`scene_NN_1.wav`)는 진행률 계산에서 제외됩니다.

### 표지 URL 추출

```js
const scenarios = data.cover?.scenarios || [];
const coverImageUrl = (scenarios.find(s => s.index === 0) || {}).image_url || '';
const coverAudioUrl = (scenarios.find(s => s.index === 1) || {}).audio_url || '';
```

### 씬 재생 흐름

```
index 0 → img_01 표시, delay초 대기
index 1 → 내레이션 자막 + scene_NN_0.wav 재생, 완료까지 대기
index 2 → img_02 전환, delay초 대기
index 3 → 대사 자막 표시 (+ scene_NN_1.wav 있으면 재생)
```

---

## curl 예시

```bash
# 헬스 체크
curl http://127.0.0.1:8000/health

# 작업 생성
curl -X POST http://127.0.0.1:8000/api/runs \
  -H "Content-Type: application/json" \
  -d '{"era_ko":"조선 시대","place_ko":"한양","characters_ko":"호기심 많은 아이와 말하는 호랑이","topic_ko":"우정"}'

# 상태 조회
curl http://127.0.0.1:8000/api/runs/20260429_173423_d118aa

# SSE 확인
curl -N http://127.0.0.1:8000/api/runs/20260429_173423_d118aa/events

# 산출물 다운로드
curl -o cover.png    http://127.0.0.1:8000/api/runs/20260429_173423_d118aa/images/cover.png
curl -o cover.wav    http://127.0.0.1:8000/api/runs/20260429_173423_d118aa/audio/cover.wav
curl -o scene_1_narr.wav http://127.0.0.1:8000/api/runs/20260429_173423_d118aa/audio/scene_01_0.wav
curl -o scene_1_dial.wav http://127.0.0.1:8000/api/runs/20260429_173423_d118aa/audio/scene_01_1.wav
curl -o story.json   http://127.0.0.1:8000/api/runs/20260429_173423_d118aa/story
```
