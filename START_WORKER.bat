@echo off
REM START_WORKER.bat — 5080 컴퓨터에서 실행
REM Worker server: LLM + ComfyUI 이미지 생성 담당

echo === Worker Server (RTX 5080) ===
echo.

set "PROJECT_DIR=%~dp0"

REM 1. ComfyUI 실행 (5080 로컬)
echo 1. ComfyUI running on 5080...
start "ComfyUI-Worker" cmd /k "cd /d %PROJECT_DIR% && venv\Scripts\activate.bat && cd ComfyUI && python main.py --listen 0.0.0.0 --port 8188"

REM 3초 대기 (ComfyUI 초기화)
timeout /t 3 /nobreak >nul

REM 2. Worker API 서버 실행 (포트 8001)
echo 2. Worker API server running on port 8001...
start "Worker-API" cmd /k "cd /d %PROJECT_DIR% && venv\Scripts\activate.bat && uvicorn app.workers.worker_server:app --host 0.0.0.0 --port 8001"

echo.
echo === Worker 서버가 시작되었습니다! ===
echo.
echo 이 컴퓨터 IP를 3080 컴퓨터의 .env에 설정:
echo   WORKER_URL=http://[이_컴퓨터_IP]:8001
echo.
echo 상태 확인: http://[이_컴퓨터_IP]:8001/health
echo.
pause
