from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.agents.orchestrator import handle_turn
from app.api.voice_schemas import ConverseVoiceResponse, TranscribeResponse
from app.core.audit import log_event
from app.core.auth import get_current_owner
from app.core.rate_limit import enforce_rate_limit
from app.voice.transcriber import transcribe_audio

router = APIRouter(prefix="/voice", tags=["voice"])

MAX_AUDIO_BYTES = 15_000_000  # 15MB cap


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(file: UploadFile = File(...), owner_id: str = Depends(get_current_owner)):
    data = await file.read()
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail=f"Audio exceeds {MAX_AUDIO_BYTES} byte limit.")

    text = transcribe_audio(data, filename_hint=file.filename)
    if not text:
        raise HTTPException(status_code=422, detail="Could not transcribe any speech from the audio.")
    return TranscribeResponse(transcript=text)


@router.post("/converse", response_model=ConverseVoiceResponse)
async def converse_voice(
    conversation_id: str = Form(...),
    file: UploadFile = File(...),
    owner_id: str = Depends(get_current_owner),
):
    """
    The full 'user speaks, no manual prompt-writing' flow from the spec:
    voice -> transcript -> Conversation Agent -> Supervisor -> RAG/chat.
    """
    enforce_rate_limit(owner_id)
    data = await file.read()
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail=f"Audio exceeds {MAX_AUDIO_BYTES} byte limit.")

    transcript = transcribe_audio(data, filename_hint=file.filename)
    if not transcript:
        raise HTTPException(status_code=422, detail="Could not transcribe any speech from the audio.")

    try:
        result = handle_turn(conversation_id=conversation_id, owner_id=owner_id, message=transcript)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM provider error: {e}")

    log_event(owner_id, "voice_converse", {"agent_used": result["agent_used"], "conversation_id": conversation_id})
    return ConverseVoiceResponse(transcript=transcript, **result)
