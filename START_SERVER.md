# 외부 접속 가능한 동화책 API 서버 실행 가이드

## 🚀 빠른 시작

### 1. ComfyUI 실행 (터미널 1)
```powershell
cd c:\Users\user\Desktop\make_story\ComfyUI
python main.py
```
- http://127.0.0.1:8188 에서 실행됨
- **창을 닫지 마세요!**

### 2. FastAPI 서버 실행 (터미널 2)
```powershell
cd c:\Users\user\Desktop\make_story
.\venv\Scripts\activate
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```
- http://127.0.0.1:8000 에서 실행됨
- **창을 닫지 마세요!**

### 3. ngrok 터널 실행 (터미널 3)
```powershell
ngrok http 8000
```
- 외부 접속 URL이 표시됩니다
- 예: `https://abc-123-xyz.ngrok-free.app`

## 📱 휴대폰에서 접속

1. 터미널 3에 표시된 ngrok URL 확인
2. 휴대폰 브라우저에서 해당 URL 접속
3. 프론트엔드 화면에서 동화 생성!

## 🎯 테스트 예시

**입력:**
- 시대: 현대
- 장소: 숲
- 등장인물: 토끼
- 주제: 우정
- TTS: 생성 / 생성 안함

**결과:**
- 실시간 진행상황 표시
- 이미지 5개 (표지 + 패널 4개)
- 오디오 5개 (TTS 활성화 시)

## ⚠️ 주의사항

- 3개 터미널 모두 실행 상태 유지 필요
- ngrok URL은 무료 플랜에서 세션마다 변경됨
- 첫 접속 시 ngrok 경고 화면 나타날 수 있음 (Visit Site 클릭)

## 🛑 종료

각 터미널에서 `Ctrl+C` 눌러서 종료
