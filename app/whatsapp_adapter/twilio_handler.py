"""
Twilio message handler — the Twilio equivalent of
app/whatsapp_adapter/handler.py. Reuses the exact same downstream
pipeline (Conversation Agent, Supervisor, RAG, Voice, document
ingestion) built in Phases 1-5 — only the incoming payload shape and
outbound send mechanism differ from the Meta adapter.

Twilio's webhook body is form-encoded (not JSON like Meta's), with a
NumMedia count and MediaUrl0/MediaContentType0 fields for the first
attachment rather than Meta's media_id + separate lookup call.
"""
import logging

from app.agents.orchestrator import handle_turn
from app.core.audit import log_event
from app.rag.pipeline import ingest_document
from app.voice.transcriber import transcribe_audio
from app.whatsapp_adapter.twilio_client import (
    TwilioAPIError,
    download_media,
    send_text_message,
)

logger = logging.getLogger(__name__)

# Twilio gives us a content-type, not a filename — map to an extension
# our existing extractors already know how to handle.
MIME_TO_EXTENSION = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/plain": "txt",
}


def handle_incoming_twilio_message(params: dict[str, str]) -> None:
    from_whatsapp = params.get("From", "")  # e.g. "whatsapp:+15551234567"
    phone = from_whatsapp.removeprefix("whatsapp:")
    owner_id = f"whatsapp:{phone}"
    conversation_id = owner_id

    num_media = int(params.get("NumMedia", "0") or "0")
    body = params.get("Body", "").strip()

    try:
        if num_media > 0:
            _handle_media(conversation_id, owner_id, from_whatsapp, params)
        elif body:
            _handle_text(conversation_id, owner_id, from_whatsapp, body)
    except TwilioAPIError as e:
        # Same reasoning as the Meta handler: log and move on rather
        # than raise, since the webhook route must return quickly.
        logger.error(f"Twilio send failed for {from_whatsapp}: {e}")


def _handle_text(conversation_id: str, owner_id: str, from_whatsapp: str, body: str) -> None:
    result = handle_turn(conversation_id=conversation_id, owner_id=owner_id, message=body)
    log_event(owner_id, "twilio_converse", {"agent_used": result["agent_used"]})
    send_text_message(from_whatsapp, result["reply"])


def _handle_media(conversation_id: str, owner_id: str, from_whatsapp: str, params: dict[str, str]) -> None:
    media_url = params.get("MediaUrl0")
    content_type = params.get("MediaContentType0", "")
    if not media_url:
        return

    data, _ = download_media(media_url)

    if content_type.startswith("audio"):
        transcript = transcribe_audio(data, filename_hint="voice.ogg")
        if not transcript:
            send_text_message(
                from_whatsapp,
                "Sorry, I couldn't make out that voice message — could you try again?",
            )
            return
        result = handle_turn(conversation_id=conversation_id, owner_id=owner_id, message=transcript)
        log_event(owner_id, "twilio_voice_converse", {"agent_used": result["agent_used"]})
        send_text_message(from_whatsapp, result["reply"])
        return

    ext = MIME_TO_EXTENSION.get(content_type)
    if not ext:
        send_text_message(
            from_whatsapp,
            f"Sorry, I can't read files of type '{content_type}' yet — try PDF, DOCX, XLSX, or TXT.",
        )
        return

    result = ingest_document(filename=f"whatsapp_upload.{ext}", data=data, owner_id=owner_id)
    log_event(owner_id, "twilio_document_upload", {"filename": result["filename"]})
    send_text_message(
        from_whatsapp,
        f"Got it — indexed \"{result['filename']}\" ({result['chunks_indexed']} sections). "
        "Ask me anything about it.",
    )
