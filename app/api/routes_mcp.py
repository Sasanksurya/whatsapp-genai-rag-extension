from fastapi import APIRouter, Depends, HTTPException

from app.api.mcp_schemas import (
    DriveAuthUrlResponse,
    DriveIngestRequest,
    IngestResult,
    IngestUrlRequest,
)
from app.core.audit import log_event
from app.core.auth import get_current_owner
from app.core.config import settings
from app.core.rate_limit import enforce_rate_limit
from app.mcp.drive_client import DriveNotAuthorizedError, build_auth_url, exchange_code
from app.mcp.mcp_agent import ingest_drive_file, ingest_website
from app.mcp.security import UnsafeURLError
from app.mcp.website_fetcher import FetchError

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.post("/ingest-url", response_model=IngestResult)
def ingest_url(payload: IngestUrlRequest, owner_id: str = Depends(get_current_owner)):
    enforce_rate_limit(owner_id)
    try:
        result = ingest_website(url=payload.url, owner_id=owner_id)
    except UnsafeURLError as e:
        log_event(owner_id, "mcp_url_blocked", {"url": payload.url, "reason": str(e)})
        raise HTTPException(status_code=400, detail=f"Blocked URL: {e}")
    except FetchError as e:
        raise HTTPException(status_code=422, detail=str(e))

    log_event(owner_id, "mcp_url_ingest", {"url": payload.url, "chunks": result["chunks_indexed"]})
    return IngestResult(**result)


@router.get("/drive/auth-url", response_model=DriveAuthUrlResponse)
def drive_auth_url(owner_id: str = Depends(get_current_owner)):
    """
    Returns the real Google OAuth consent URL for the authenticated
    owner. owner_id travels through OAuth's `state` param so Google
    echoes it back to /drive/callback automatically.
    """
    try:
        url = build_auth_url(settings.google_oauth_redirect_uri, state=owner_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Missing '{settings.google_client_secrets_file}'. See README "
                "'Google Drive setup' for how to create free OAuth credentials."
            ),
        )
    return DriveAuthUrlResponse(auth_url=url)


@router.get("/drive/callback")
def drive_callback(code: str, state: str):
    # No X-API-Key here by nature — this is Google redirecting the
    # user's browser, not an authenticated API call. `state` is what
    # Google echoes back from the auth-url step above, so it's tied
    # to a real prior authenticated request, not client-supplied here.
    owner_id = state
    exchange_code(owner_id, code, settings.google_oauth_redirect_uri)
    log_event(owner_id, "mcp_drive_authorized", {})
    return {"status": "authorized", "owner_id": owner_id}


@router.post("/drive/ingest", response_model=IngestResult)
def drive_ingest(payload: DriveIngestRequest, owner_id: str = Depends(get_current_owner)):
    enforce_rate_limit(owner_id)
    try:
        result = ingest_drive_file(owner_id=owner_id, file_id=payload.file_id)
    except DriveNotAuthorizedError as e:
        raise HTTPException(status_code=401, detail=str(e))

    log_event(owner_id, "mcp_drive_ingest", {"file_id": payload.file_id, "chunks": result["chunks_indexed"]})
    return IngestResult(**result)
