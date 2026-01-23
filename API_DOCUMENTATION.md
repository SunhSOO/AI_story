# AI 동화책 생성 API 문서

## 📡 API Base URL

**개발 서버**: `https://mystorybook.loca.lt`

> ⚠️ password : 59.3.103.182

## 🔐 인증

현재는 인증이 필요하지 않습니다.

## 📋 API 엔드포인트

### 1. STT (음성-텍스트 변환)

**Endpoint**: `POST /api/stt/field`

**Request**:
```http
Content-Type: multipart/form-data

audio_file: File (webm, mp4, wav, etc.)
field_type: string ("era" | "place" | "characters" | "topic")
language: string (optional, default: "ko-KR")
```

**Response**:
```json
{
  "stt_text": "현대",
  "parsed_value": "현대",
  "confidence": 0.95
}
```

### 2. 동화 생성 시작

**Endpoint**: `POST /api/runs`

**Request**:
```json
{
  "era_ko": "현대",
  "place_ko": "숲",
  "characters_ko": "토끼",
  "topic_ko": "우정",
  "tts_enabled": true
}
```

**Response**:
```json
{
  "run_id": "20260122_130741_a3f2c1"
}
```

### 3. 진행 상태 조회

**Endpoint**: `GET /api/runs/{run_id}`

**Response**:
```json
{
  "status": "IN_PROGRESS",
  "stage": "PANEL_2",
  "ready_max_page": 1,
  "ready_max_audio_page": 0,
  "pages": [
    {
      "page": 0,
      "title": "토끼의 우정",
      "image_url": "/api/runs/{run_id}/images/cover.png",
      "audio_url": "/api/runs/{run_id}/audio/page_0.wav"
    }
  ]
}
```

### 4. 실시간 진행 이벤트 (SSE)

**Endpoint**: `GET /api/runs/{run_id}/events`

**Response** (Server-Sent Events):
```javascript
event: update
data: {"status":"IN_PROGRESS","stage":"PANEL_1","ready_max_page":1,"ready_max_audio_page":1}

event: update
data: {"status":"DONE","stage":"TTS","ready_max_page":4,"ready_max_audio_page":4}
```

### 5. 이미지 다운로드

**Endpoint**: `GET /api/runs/{run_id}/images/{filename}`

예시: `/api/runs/20260122_130741_a3f2c1/images/cover.png`

**Response**: PNG 이미지 파일

### 6. 오디오 다운로드

**Endpoint**: `GET /api/runs/{run_id}/audio/{filename}`

예시: `/api/runs/20260122_130741_a3f2c1/audio/page_0.wav`

**Response**: WAV 오디오 파일

## 📊 Status & Stage

### Status
- `PENDING`: 대기 중
- `IN_PROGRESS`: 생성 중
- `DONE`: 완료
- `FAILED`: 실패

### Stage
- `INIT`: 초기화
- `LLM`: 스토리 생성 중
- `COVER`: 표지 이미지 생성 중
- `PANEL_1` ~ `PANEL_4`: 각 페이지 이미지 생성 중
- `TTS`: 음성 생성 중

## 🔄 전체 플로우 예시

```javascript
// 1. 동화 생성 시작
const response = await fetch('https://mystorybook.loca.lt/api/runs', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    era_ko: "현대",
    place_ko: "숲",
    characters_ko: "토끼",
    topic_ko: "우정",
    tts_enabled: true
  })
});
const { run_id } = await response.json();

// 2. SSE로 실시간 진행상황 모니터링
const eventSource = new EventSource(`https://mystorybook.loca.lt/api/runs/${run_id}/events`);

eventSource.addEventListener('update', (event) => {
  const data = JSON.parse(event.data);
  console.log(`진행률: ${data.stage}, 이미지: ${data.ready_max_page + 1}/5`);
  
  if (data.status === 'DONE') {
    eventSource.close();
    loadResults(run_id);
  }
});

// 3. 완료 후 결과 조회
async function loadResults(run_id) {
  const response = await fetch(`https://mystorybook.loca.lt/api/runs/${run_id}`);
  const result = await response.json();
  
  // 이미지 및 오디오 URL 사용
  result.pages.forEach(page => {
    const imageUrl = `https://mystorybook.loca.lt${page.image_url}`;
    const audioUrl = `https://mystorybook.loca.lt${page.audio_url}`;
    // UI에 표시...
  });
}
```

## ⏱️ 예상 처리 시간

- LLM 스토리 생성: ~20-30초
- 이미지 생성 (5장): ~2분
- 음성 생성 (5개): ~30초
- **총 소요 시간**: 약 2-3분

## ⚠️ 주의사항

1. **CORS**: 모든 도메인에서 접근 가능하도록 설정되어 있습니다.
2. **타임아웃**: 장시간 응답이 없으면 서버가 다운되었을 수 있습니다.
3. **동시 요청**: 여러 동화를 동시에 생성 가능하지만, 서버 리소스에 따라 속도가 느려질 수 있습니다.


## 🐛 오류 처리

모든 오류는 표준 HTTP 상태 코드와 함께 JSON 형식으로 반환됩니다:

```json
{
  "detail": "오류 메시지"
}
```

- `400`: 잘못된 요청
- `404`: 리소스를 찾을 수 없음
- `422`: 유효성 검사 실패
- `500`: 서버 내부 오류


