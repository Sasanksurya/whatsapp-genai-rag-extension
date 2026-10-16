
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

    Document access is restricted to the authenticated owner and
    requested conversation. An optional document_id narrows retrieval
    to one document within that conversation.
    """

    # 1. Verify conversation membership.
    verify_conversation_membership(
        conversation_id=payload.conversation_id,
        user_id=owner_id,
    )

    # 2. Rate limit the authenticated owner.
    enforce_rate_limit(owner_id)

    # 3. Run the conversational orchestrator.
    try:
        result = handle_turn(
            conversation_id=payload.conversation_id,
            owner_id=owner_id,
            message=payload.message,
            document_id=payload.document_id,
        )

    except HTTPException:
        # Preserve authorization and other intentional HTTP errors.
        raise

    except ValueError as e:
        # Invalid or inaccessible document ID.
        raise HTTPException(
            status_code=400,
            detail=str(e),
        ) from e

    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e),
        ) from e

    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM provider error: {e}",
        ) from e

    # 4. Audit the completed request.
    log_event(
        owner_id,
        "converse",
        {
            "agent_used": result["agent_used"],
            "conversation_id": payload.conversation_id,
            "document_id": payload.document_id,
            "sources": result["sources"],
        },
    )

    # 5. Return the response.
    return ConverseResponse(**result)
