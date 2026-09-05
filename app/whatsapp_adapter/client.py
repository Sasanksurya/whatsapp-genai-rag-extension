"""
Thin client for the WhatsApp Cloud API (Graph API) — the isolation
boundary between WhatsApp-specific HTTP calls and the rest of the
system (see project spec section 17: the AI system shouldn't be
tightly coupled to WhatsApp-specific code).
"""
import httpx

from app.core.config import settings

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


class WhatsAppAPIError(Exception):
    pass


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.whatsapp_access_token}"}


def send_text_message(to_phone: str, body: str) -> None:
    url = f"{GRAPH_API_BASE}/{settings.whatsapp_phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": body},
    }
    try:
        response = httpx.post(url, json=payload, headers=_headers(), timeout=15.0)
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise WhatsAppAPIError(f"Failed to send message to {to_phone}: {e}")


def download_media(media_id: str) -> tuple[bytes, str]:
    """Returns (raw_bytes, mime_type). Two-step per Meta's API: first
    resolve the media_id to a temporary download URL, then fetch it."""
    meta_url = f"{GRAPH_API_BASE}/{media_id}"
    try:
        meta_response = httpx.get(meta_url, headers=_headers(), timeout=15.0)
        meta_response.raise_for_status()
        media_info = meta_response.json()

        file_response = httpx.get(media_info["url"], headers=_headers(), timeout=30.0)
        file_response.raise_for_status()
    except httpx.HTTPError as e:
        raise WhatsAppAPIError(f"Failed to download media '{media_id}': {e}")

    return file_response.content, media_info.get("mime_type", "application/octet-stream")
