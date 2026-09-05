"""
WhatsApp message handler — the bridge between the adapter and the
existing AI system (Conversation Agent, Supervisor, RAG, Voice,
document ingestion) built in Phases 1-5. None of that code changes
here; this module just adapts WhatsApp's message shape to it.

IDENTITY: owner_id is the sender's phone number, taken directly from
the verified (HMAC-checked) webhook payload — not a client-supplied
header like the demo API-key flow. This is actually a stronger
identity guarantee than Phase 5's /auth/register, and closes the
gap flagged there: "owner_id should come from the verified WhatsApp
sender identity... not be self-declared."
"""
import logging

from app.agents.orchestrator import handle_turn
from app.core.audit import log_event
from app.rag.pipeline import ingest_document
from app.voice.transcriber import transcribe_audio
from app.whatsapp_adapter.client import (
    WhatsAppAPIError,
    download_media,
    send_text_message,
)
from app.whatsapp_adapter.payload_parser import IncomingMessage

logger = logging.getLogger(__name__)


def handle_incoming_message(msg: IncomingMessage) -> None:
    owner_id = f"whatsapp:{msg.from_phone}"
    # One conversation thread per sender for now — matches a 1:1 chat.
    # Group-chat thread scoping is a documented next step, not built here.
    conversation_id = owner_id

    try:
        if msg.message_type == "text":
            _handle_text(conversation_id, owner_id, msg.text or "")

        elif msg.message_type == "audio":
            _handle_audio(conversation_id, owner_id, msg.media_id)

        elif msg.message_type == "document":
            _handle_document(owner_id, msg.media_id, msg.filename)

        else:
            send_text_message(
                msg.from_phone,
                "Sorry, I can only handle text, voice messages, and document "
                "attachments right now.",
            )
    except WhatsAppAPIError as e:
        # Can't message the user back if the API call itself is failing —
        # log and move on rather than raising into the webhook handler,
        # which must always return 200 quickly (see routes_whatsapp.py).
        logger.error(f"WhatsApp send failed for {msg.from_phone}: {e}")


def _handle_text(conversation_id: str, owner_id: str, text: str) -> None:
    if not text.strip():
        return
    result = handle_turn(conversation_id=conversation_id, owner_id=owner_id, message=text)
    log_event(owner_id, "whatsapp_converse", {"agent_used": result["agent_used"]})
    send_text_message(owner_id.removeprefix("whatsapp:"), result["reply"])


def _handle_audio(conversation_id: str, owner_id: str, media_id: str | None) -> None:
    if not media_id:
        return
    audio_bytes, _mime = download_media(media_id)
    transcript = transcribe_audio(audio_bytes, filename_hint="voice.ogg")
    if not transcript:
        send_text_message(
            owner_id.removeprefix("whatsapp:"),
            "Sorry, I couldn't make out that voice message — could you try again?",
        )
        return

    result = handle_turn(conversation_id=conversation_id, owner_id=owner_id, message=transcript)
    log_event(owner_id, "whatsapp_voice_converse", {"agent_used": result["agent_used"]})
    send_text_message(owner_id.removeprefix("whatsapp:"), result["reply"])


def _handle_document(owner_id: str, media_id: str | None, filename: str | None) -> None:
    if not media_id:
        return
    data, _mime = download_media(media_id)
    result = ingest_document(filename=filename or "document", data=data, owner_id=owner_id)
    log_event(owner_id, "whatsapp_document_upload", {"filename": result["filename"]})
    send_text_message(
        owner_id.removeprefix("whatsapp:"),
        f"Got it — indexed \"{result['filename']}\" ({result['chunks_indexed']} sections). "
        "Ask me anything about it.",
    )
