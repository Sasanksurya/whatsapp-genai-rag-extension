"""
WhatsApp webhook endpoints.

Two routes, both required by Meta's webhook setup flow:
- GET: the one-time verification handshake when you register the
  webhook URL in the Meta App dashboard.
- POST: every actual incoming event (messages, status updates) after
  that. Must respond 200 quickly — Meta retries/disables webhooks
  that are slow or error out, so heavy work (LLM calls, etc.) happens
  in the background, and errors there are caught and logged, never
  allowed to turn into a non-200 response here.
"""
import logging

from fastapi import APIRouter, BackgroundTasks, Request, Response

from app.core.config import settings
from app.whatsapp_adapter.handler import handle_incoming_message
from app.whatsapp_adapter.payload_parser import extract_messages
from app.whatsapp_adapter.security import verify_signature

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


@router.get("/webhook", include_in_schema=False)
async def verify_webhook(request: Request):
    # Meta sends hub.mode / hub.verify_token / hub.challenge as query
    # params — dots aren't valid Python parameter names, so these are
    # read directly off the raw query string instead of as declared
    # FastAPI parameters.
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.whatsapp_verify_token:
        return Response(content=challenge, media_type="text/plain")
    return Response(content="Verification failed", status_code=403)


@router.post("/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    if not verify_signature(raw_body, signature):
        logger.warning("Rejected webhook POST with invalid/missing signature.")
        # Still return 200 — per Meta's docs, returning an error can
        # cause Meta to disable the webhook after repeated failures.
        # A bad signature should be silently dropped, not surfaced as
        # a retriable error.
        return Response(status_code=200)

    payload = await request.json()
    messages = extract_messages(payload)

    for msg in messages:
        # Processed in the background so this handler returns
        # immediately — Meta expects a fast 200, and LLM/RAG calls are
        # not fast.
        background_tasks.add_task(handle_incoming_message, msg)

    return Response(status_code=200)
