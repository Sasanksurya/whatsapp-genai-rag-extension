from fastapi import APIRouter, Depends, HTTPException

from app.agents.orchestrator import handle_turn
from app.api.converse_schemas import ConverseRequest, ConverseResponse
from app.core.audit import log_event
from app.core.auth import get_current_owner
from app.core.conversation_verification import verify_conversation_membership
from app.core.rate_limit import enforce_rate_limit


router = APIRouter(tags=["converse"])


@router.post(
    "/converse",
    response_model=ConverseResponse,
)
def converse(
    payload: ConverseRequest,
    owner_id: str = Depends(get_current_owner),
):
    """
    Main conversational AI endpoint.

    Security flow:

        X-API-Key
             ↓
        get_current_owner()
             ↓
        authenticated owner_id
             ↓
        verify conversation membership
             ↓
        multi-agent orchestrator
             ↓
        Conversation Agent
             ↓
        Supervisor + Retrieval
             ↓
        RAG / General Chat
             ↓
        Verification Agent
             ↓
        final response

    The client can provide a conversation_id as the resource it wants
    to access, but cannot provide a separate user identity. The user
    identity always comes from the authenticated API key.
    """

    # ------------------------------------------------------------
    # 1. Verify that the authenticated user belongs to the requested
    #    conversation.
    #
    # IMPORTANT:
    # owner_id comes from get_current_owner(), not from the request.
    #
    # This prevents a client from simply changing a userId value to
    # impersonate another user.
    # ------------------------------------------------------------
    verify_conversation_membership(
        conversation_id=payload.conversation_id,
        user_id=owner_id,
    )

    # ------------------------------------------------------------
    # 2. Rate limit the authenticated owner.
    # ------------------------------------------------------------
    enforce_rate_limit(owner_id)

    # ------------------------------------------------------------
    # 3. Run the complete multi-agent conversational turn.
    #
    # handle_turn() performs:
    #
    #   Conversation Agent
    #          ↓
    #   query resolution
    #          ↓
    #   conversation-aware retrieval
    #          ↓
    #   Supervisor Agent
    #          ↓
    #   RAG OR General Chat
    #          ↓
    #   Verification Agent
    #          ↓
    #   final answer
    # ------------------------------------------------------------
    try:
        result = handle_turn(
            conversation_id=payload.conversation_id,
            owner_id=owner_id,
            message=payload.message,
        )

    except HTTPException:
        # Preserve FastAPI HTTP errors exactly as they are.
        #
        # This is important because authorization errors such as
        # 403 must remain 403 instead of becoming 502.
        raise

    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e),
        )

    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM provider error: {e}",
        )

    # ------------------------------------------------------------
    # 4. Audit the completed conversational request.
    # ------------------------------------------------------------
    log_event(
        owner_id,
        "converse",
        {
            "agent_used": result["agent_used"],
            "conversation_id": payload.conversation_id,
        },
    )

    # ------------------------------------------------------------
    # 5. Return the multi-agent response.
    # ------------------------------------------------------------
    return ConverseResponse(**result)