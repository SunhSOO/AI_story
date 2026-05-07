"""FastAPI application entry point."""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError

from app.middlewares.request_id_middleware import RequestIDMiddleware
from app.middlewares.logging_middleware import LoggingMiddleware
from app.middlewares.error_handler_middleware import ErrorHandlerMiddleware
from app.routers.stt_router import router as stt_router
from app.routers.run_router import router as run_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

app = FastAPI(
    title="AI Story Generator",
    description="Local AI storybook generation: 4 scenes × 3 images + emotion TTS",
    version="3.0.0",
)

# ── Middlewares ────────────────────────────────────────────────────────────────
app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(stt_router)
app.include_router(run_router)

# ── Static files ──────────────────────────────────────────────────────────────
_static_dir = Path(__file__).parent.parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


# ── Exception handlers ────────────────────────────────────────────────────────
@app.exception_handler(RequestValidationError)
async def validation_handler(request, exc):
    logging.getLogger("app").error("Validation error %s: %s", request.url, exc.errors())
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


# ── Health / root ─────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    index = _static_dir / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"status": "ok", "version": "3.0.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
