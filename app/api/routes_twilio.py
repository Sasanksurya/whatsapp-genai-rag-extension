"""
Twilio webhook endpoint.

Simpler than the Meta adapter's routes: Twilio has no separate
verification-handshake step (that's a Meta Cloud API-specific
requirement) — you just paste the webhook URL into the Sandbox
Settings page directly. Every incoming message is a single POST here.

SIGNATURE FIX: Twilio's signature check requires the EXACT public URL
you configured in Twilio's dashboard — not a URL rebuilt from request
headers, which is unreliable behind a tunnel like ngrok (forwarded
headers don't always reflect the exact address Twilio actually used).
Using TWILIO_WEBHOOK_URL directly from settings removes that guesswork.
"""
import logging

from fastapi import APIRouter, BackgroundTasks, Request, Response

from app.core.config import settings
from app.whatsapp_adapter.twilio_handler import handle_incoming_twilio_message
from app.whatsapp_adapter.twilio_security import verify_twilio_signature

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/twilio", tags=["twilio"])


@router.post("/webhook")
async def receive_twilio_webhook(request: Request, background_tasks: BackgroundTasks):
    form = await request.form()
    params = {key: str(value) for key, value in form.items()}

    signature = request.headers.get("X-Twilio-Signature")

    # Use the exact URL configured in Twilio's dashboard (saved in
    # .env as TWILIO_WEBHOOK_URL) rather than reconstructing it from
    # request headers — that reconstruction is unreliable behind ngrok.
    url = settings.twilio_webhook_url

    if not verify_twilio_signature(url, params, signature):
        logger.warning("Rejected Twilio webhook with invalid/missing signature.")
        # Same reasoning as the Meta adapter: still 200, don't leak
        # that the signature check failed to a potential attacker.
        return Response(status_code=200, media_type="text/xml", content="<Response></Response>")

    background_tasks.add_task(handle_incoming_twilio_message, params)

    # Twilio expects a 200 with either empty content or valid TwiML —
    # an empty <Response/> means "no automatic reply", since we send
    # the actual reply asynchronously via the REST API instead.
    return Response(status_code=200, media_type="text/xml", content="<Response></Response>")