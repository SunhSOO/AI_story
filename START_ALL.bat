@echo off
REM START_ALL.bat
REM 모든 서버를 한번에 실행하는 배치 파일

echo === AI 스토리북 서버 시작 ===
echo.

REM 현재 디렉토리 저장
set "PROJECT_DIR=%~dp0"

REM 1. ComfyUI 실행
echo 1. ComfyUI 실행 중...
start "ComfyUI" cmd /k "cd /d %PROJECT_DIR%ComfyUI && venv\Scripts\activate.bat && python main.py"

REM 2초 대기
timeout /t 2 /nobreak >nul

REM 2. FastAPI 서버 실행 (가상환경 활성화)
echo 2. FastAPI 서버 실행 중 (가상환경 포함)...
start "FastAPI Server" cmd /k "cd /d %PROJECT_DIR% && venv\Scripts\activate.bat && uvicorn server:app --host 127.0.0.1 --port 8000 --reload"

REM 3초 대기
timeout /t 3 /nobreak >nul

REM 3. Localtunnel 실행
echo 3. Localtunnel 실행 중...
start "Localtunnel" cmd /k "cd /d %PROJECT_DIR% && powershell -ExecutionPolicy Bypass -File start_tunnel.ps1"

echo.
echo === 모든 서버가 실행되었습니다! ===
echo.
echo 브라우저에서 접속:
echo   로컬: http://127.0.0.1:8000
echo   외부: https://mystorybook.loca.lt (터널 URL 확인)
echo.
echo 각 터미널 창에서:
echo   - (venv) 표시가 있으면 가상환경 활성화 성공
echo   - 서버 종료는 Ctrl+C 또는 창 닫기
echo.
pause
