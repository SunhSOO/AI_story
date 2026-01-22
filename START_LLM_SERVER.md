# LLM 서버 시작 가이드

## llama-server 실행

별도의 PowerShell 터미널에서:

```powershell
cd c:\Users\user\Desktop\make_story\llama.cpp\build\bin

.\llama-server.exe `
  -m "c:\Users\user\Desktop\make_story\llm_model\Qwen3-14B-Q6_K.gguf" `
  --grammar-file "c:\Users\user\Desktop\make_story\story_spec.gbnf" `
  --ctx-size 4096 `
  --n-gpu-layers 999 `
  --port 8080 `
  --host 127.0.0.1
```

## 확인

서버가 시작되면:
```
llama server listening at http://127.0.0.1:8080
```

브라우저에서 확인: http://127.0.0.1:8080

## 주요 옵션

- `--ctx-size 4096`: 컨텍스트 크기
- `--n-gpu-layers 999`: 모든 레이어 GPU로
- `--port 8080`: 포트 번호
- `--grammar-file`: JSON 형식 강제

## 종료

`Ctrl+C`로 중지
