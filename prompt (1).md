# prompt.md — Storybook App Backend (External API v2.0) / Antigravity용



> 프론트에서 시대, 장소, 등장인물, 주제를 입력받고, 녹음한 음성 또는 텍스트를 서버로 전송하면, 서버는 동화를 생성하고, 이미지를 생성하고, 음성을 생성한다.

> 현재 일부 구현이 되어있는데 이미지 생성 시 
make_panel.json사용하여 첫번째 시드는 랜덤배정하고, 나머지 4개 시드는 첫번째 시드를 사용한다. make_panel.json은 긍정조건 앞에는 항상 watercolor painting, children's book illustrationf를 붙여서 사용한다.
부정조건은 make_panel.json에 있는 내용 그대로 사용한다.

> 총 output이 100개가 넘어가면 가장 오래된 순으로 자동 삭제한다.

>음성 생성 시 M1 음성을 생성하며 사용언어는 ko, 내용은 패널별로 생성한다.

> 목표: **프론트 개발 없이** 서버(AI)만 구현/유지한다.  
> 기준 문서: **External API Specification v2.0 (Field-level STT Enabled)** :contentReference[oaicite:0]{index=0}


---

## 0) 절대 규칙 (Non-negotiables)
- **가상환경**: 루트 디렉토리의 venv를 사용할 것
- **API 스펙 우선**: 이 문서의 엔드포인트/필드/상태는 변경하지 말 것. 호환성 깨면 “완료” 아님. :contentReference[oaicite:1]{index=1}
- **비파괴 원칙**: 기본값으로 `rm -rf`, `git reset --hard`, 대규모 리팩터링 금지.
- **작게 쪼개서 검증**: 계획 → 구현 → 스모크 테스트 → 변경 요약.
- **로컬 우선**: 서버는 로컬에서 동작 가능해야 한다(모델 로딩/추론 포함). 외부 유료 API 의존 금지.
- **시크릿 금지**: 키/토큰/쿠키/개인 파일 로그 출력 금지. 발견 시 마스킹.

---

## 1) 시스템 역할 (서버만 담당)
### 서버(AI)의 책임
- Field STT 요청을 받아 **음성→텍스트 변환 + 정규화(parsed_value)** 를 반환한다. :contentReference[oaicite:2]{index=2}
- Run 생성 요청을 받아 **동화 생성 파이프라인(LLM→이미지→TTS)** 을 비동기로 실행한다. :contentReference[oaicite:3]{index=3}
- Run 상태 조회 / SSE 이벤트 스트림 / 이미지·오디오 다운로드를 제공한다. :contentReference[oaicite:4]{index=4}

### 프론트는 서버 밖(우리가 안 함)
- 항목별 입력 UI/녹음/사용자 수정 확인/렌더링은 **클라이언트 책임**이다. :contentReference[oaicite:5]{index=5}

---

## 2) API 스펙 (반드시 준수)
### 기본
- Base URL: `http://127.0.0.1:8000` :contentReference[oaicite:6]{index=6}
- 인증: 없음 :contentReference[oaicite:7]{index=7}
- 인코딩: UTF-8 :contentReference[oaicite:8]{index=8}

### Content-Type
- JSON: `application/json`
- STT 업로드: `multipart/form-data`
- SSE: `text/event-stream`
- 이미지: `image/png`
- 오디오: `audio/wav` :contentReference[oaicite:9]{index=9}

### 공통 개념
- `run_id`: Run 생성 시 발급되는 고유 ID (상태/이벤트/결과 다운로드에 사용) :contentReference[oaicite:10]{index=10}
- Status: `QUEUED | RUNNING | DONE | FAILED` :contentReference[oaicite:11]{index=11}
- Stage: `LLM | COVER | PANEL_1 | PANEL_2 | PANEL_3 | PANEL_4 | TTS` :contentReference[oaicite:12]{index=12}
- Ready Indicator:
  - `ready_max_page`: `-1~4`
  - `ready_max_audio_page`: `-1~4` :contentReference[oaicite:13]{index=13}

---

## 3) 데이터 모델 (서버 응답 형태 고정)
### 3.1 Field STT
**Request**: `POST /api/stt/field`  
- `audio_file`: file (필수)  
- `field_type`: string (필수) in `era | place | characters | topic`  
- `language`: string (옵션, default `ko-KR`) :contentReference[oaicite:14]{index=14}

**Response (200)**: FieldSTTResponse
- `stt_text`: string (전사 원문)
- `parsed_value`: string (정규화 값)
- `confidence`: number (0~1) :contentReference[oaicite:15]{index=15}

### 3.2 Run 생성
**Request**: `POST /api/runs` (JSON)
- `era_ko`: string (필수)
- `place_ko`: string (필수)
- `characters_ko`: string (필수)
- `topic_ko`: string (필수)
- `tts_enabled`: boolean (옵션, default true) :contentReference[oaicite:16]{index=16}

**Response**:
- `201 Created` 권장, `200 OK` 호환
- Body: `{ "run_id": "..." }` :contentReference[oaicite:17]{index=17}

### 3.3 Run 상태 조회
`GET /api/runs/{run_id}` → RunStateResponse :contentReference[oaicite:18]{index=18}

RunStateResponse 필드:
- `status`: Status
- `stage`: Stage
- `ready_max_page`: int (-1~4)
- `ready_max_audio_page`: int (-1~4)
- `pages`: PageInfo[]
- `error`: string|null :contentReference[oaicite:19]{index=19}

PageInfo:
- `page`: int (0~4)
- `title`: string (cover)
- `summary`: string (panel)
- `image_url`: string
- `audio_url`: string :contentReference[oaicite:20]{index=20}

### 3.4 SSE 진행 이벤트
`GET /api/runs/{run_id}/events` (SSE) :contentReference[oaicite:21]{index=21}  
- 최소 요구: status/stage/ready_max_page/ready_max_audio_page 변화가 “스트림으로 관측” 가능해야 함.

### 3.5 결과 다운로드
- `GET /api/runs/{run_id}/images/{filename}` :contentReference[oaicite:22]{index=22}
- `GET /api/runs/{run_id}/audio/{filename}` :contentReference[oaicite:23]{index=23}

---

## 4) 구현 요구사항 (Backend 품질 기준)
### 4.1 비동기 파이프라인
Run 생성 요청은 즉시 `run_id`를 반환하고,
백그라운드 작업이 다음 순서로 진행되도록 구성한다:
1) LLM (스토리 스펙 생성)
2) COVER 생성
3) PANEL_1~4 생성
4) TTS 생성(옵션)

각 단계 완료 시:
- `stage` 갱신
- `ready_max_page / ready_max_audio_page` 갱신
- SSE 이벤트 발행 :contentReference[oaicite:24]{index=24}

### 4.2 출력 파일 규칙(권장)
`outputs/{run_id}/`
- `cover.png` (page 0)
- `panel_1.png` ... `panel_4.png`
- `page_0.wav` ... `page_4.wav` (또는 패널별 wav)
- `run_state.json` (서버 내부 상태 캐시, 외부 계약 아님)

※ 중요한 건 “프론트가 image_url/audio_url로 다운로드 가능”하게 filename과 URL을 일관되게 만드는 것.

### 4.3 STT UX 필수 조건(서버 관점)
`audio_file`에는 **사용자 음성만** 포함되어야 한다(안내 멘트 포함 금지). :contentReference[oaicite:25]{index=25}  
서버는 이를 강제할 수 없지만, 아래를 반드시 제공한다:
- `confidence` 기반 실패/재입력 유도 정책(클라이언트가 판단 가능) :contentReference[oaicite:26]{index=26}
- 너무 긴 무음/잡음은 confidence 낮게 나오도록(가능하면) 전처리/검출

---

## 5) 에이전트 작업 방식 (Antigravity)
요청이 오면 아래 순서로만 움직인다.
1) **스펙/현재 코드 인벤토리**: 기존 엔드포인트/모델/폴더 구조 확인
2) **변경 계획(짧게)**: 어떤 파일을 왜 바꾸는지
3) **구현**
4) **검증**
   - 최소: 서버 부팅 + 3개 스모크 호출(STT/Run 생성/상태 조회)
5) **리포트**
   - 변경 파일 목록, 실행 방법, 남은 리스크

---

## 6) 수용 기준 (Acceptance Criteria)
- `/api/stt/field`가 multipart 업로드를 받고 FieldSTTResponse를 반환한다. :contentReference[oaicite:27]{index=27}
- `/api/runs`가 `run_id`를 즉시 반환하고, 비동기로 진행된다. :contentReference[oaicite:28]{index=28}
- `/api/runs/{run_id}`에서 status/stage/ready_max_*가 단계 진행에 따라 갱신된다. :contentReference[oaicite:29]{index=29}
- `/api/runs/{run_id}/events`가 SSE로 진행 이벤트를 송출한다. :contentReference[oaicite:30]{index=30}
- 이미지/오디오 다운로드 엔드포인트가 실제 파일을 내려준다. :contentReference[oaicite:31]{index=31}

---

## 7) 날카로운 개선 포인트 (이거 안 하면, 결국 망가진다)
- **Stage 정의가 너무 빈약**: Stage는 있는데 “진행률” 정의가 없다.  
  → 서버 내부적으로는 `%`를 갖고 있어도 되지만, 최소한 SSE payload에 `ready_max_page/audio_page`를 자주 내보내서 UX를 살려라. (스펙의 Ready Indicator를 최대한 활용) :contentReference[oaicite:32]{index=32}
- **pages(PageInfo[])는 함정**: page 0~4를 항상 채우지 않으면 프론트가 예외처리 지옥에 빠진다.  
  → 서버는 항상 `pages`를 0~4 골격으로 반환하고, 준비 안 된 항목은 url을 빈 문자열/또는 null로 통일하라(스펙과 충돌 없게). :contentReference[oaicite:33]{index=33}
- **filename 규칙을 지금 확정해라**: 다운로드 URL을 “나중에 정하자” 하면, 프론트는 두 번 만든다.  
  → `cover.png`, `panel_1.png`… 같이 단순하게 고정.

---

## 8) 지금 당장 첫 액션
- 기존 서버 코드가 있다면, **현재 엔드포인트가 스펙과 1:1로 맞는지**부터 자동 테스트(스모크 스크립트)로 고정해라.
- 없으면, FastAPI로 위 6개 엔드포인트를 먼저 “동작하는 빈 파이프라인(더미 생성)”으로 만들고,
  그 다음에 LLM/이미지/TTS를 끼워 넣는다.
