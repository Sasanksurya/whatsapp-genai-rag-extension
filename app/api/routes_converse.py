from fastapi import APIRouter, Depends, HTTPException

from app.agents.orchestrator import handle_turn
from app.api.converse_schemas import ConverseRequest, ConverseResponse
from app.core.audit import log_event
from app.core.auth import get_current_owner
from app.core.rate_limit import enforce_rate_limit

router = APIRouter(tags=["converse"])


@router.post("/converse", response_model=ConverseResponse)
def converse(payload: ConverseRequest, owner_id: str = Depends(get_current_owner)):
    enforce_rate_limit(owner_id)
    try:
        result = handle_turn(
            conversation_id=payload.conversation_id,
            owner_id=owner_id,
            message=payload.message,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM provider error: {e}")

    log_event(owner_id, "converse", {"agent_used": result["agent_used"], "conversation_id": payload.conversation_id})
    return ConverseResponse(**result)
