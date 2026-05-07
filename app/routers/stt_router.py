"""STT router: POST /api/stt/field"""
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas.stt_schema import FieldSTTResponse, FieldType
from app.services.stt_service import process_stt

router = APIRouter(prefix="/api/stt", tags=["stt"])


@router.post("/field", response_model=FieldSTTResponse)
async def field_stt(
    audio_file: UploadFile = File(...),
    field_type: str = Form(...),
    language: str = Form(default="ko-KR"),
):
    try:
        ft = FieldType(field_type)
    except ValueError:
        raise HTTPException(400, f"Invalid field_type. Must be one of: {[f.value for f in FieldType]}")

    audio_bytes = await audio_file.read()
    if not audio_bytes:
        raise HTTPException(400, "Empty audio file")

    try:
        stt_text, parsed_value, confidence = await process_stt(audio_bytes, ft, language)
    except Exception as e:
        raise HTTPException(500, f"STT failed: {e}")

    return FieldSTTResponse(stt_text=stt_text, parsed_value=parsed_value, confidence=confidence)
