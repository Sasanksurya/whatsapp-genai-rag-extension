from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import ChatRequest, ChatResponse
from app.core.auth import get_current_owner
from app.core.config import settings
from app.core.rate_limit import enforce_rate_limit
from app.llm.groq_client import llm_gateway

router = APIRouter()

SYSTEM_PROMPT = (
    "You are a helpful assistant embedded in a WhatsApp conversation "
    "workflow. Keep answers concise."
)


@router.get("/health")
def health():
    return {
        "status": "ok",
        "llm_configured": llm_gateway.is_configured(),
        "provider": "groq",
        "model": settings.groq_model,
    }


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, owner_id: str = Depends(get_current_owner)):
    enforce_rate_limit(owner_id)
    try:
        reply = llm_gateway.generate(SYSTEM_PROMPT, payload.message)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        # Covers Groq SDK errors: bad/placeholder key, rate limits,
        # network egress restrictions, etc. Never leak a raw stack trace.
        raise HTTPException(status_code=502, detail=f"LLM provider error: {e}")
    return ChatResponse(reply=reply, model=settings.groq_model)
