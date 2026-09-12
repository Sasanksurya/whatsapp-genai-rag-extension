"""
Thin client for the Twilio REST API.
"""

import httpx

from app.core.config import settings

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"


class TwilioAPIError(Exception):
    pass


def _auth() -> tuple[str, str]:
    return (settings.twilio_account_sid, settings.twilio_auth_token)


def send_text_message(to_whatsapp: str, body: str) -> None:
    """Send a WhatsApp message using the Twilio Trial template."""

    url = (
        f"{TWILIO_API_BASE}/Accounts/"
        f"{settings.twilio_account_sid}/Messages.json"
    )

    data = {
        "From": settings.twilio_whatsapp_number,
        "To": to_whatsapp,
        "ContentSid": settings.twilio_content_sid,
    }

    try:
        response = httpx.post(
            url,
            data=data,
            auth=_auth(),
            timeout=15.0,
        )
        response.raise_for_status()

    except httpx.HTTPError as e:
        detail = response.text if "response" in dir() else "no response"
        raise TwilioAPIError(
            f"Failed to send message to {to_whatsapp}: "
            f"{e} | Twilio said: {detail}"
        )


def download_media(media_url: str) -> tuple[bytes, str]:
    """Download media from Twilio."""

    try:
        response = httpx.get(
            media_url,
            auth=_auth(),
            timeout=30.0,
            follow_redirects=True,
        )
        response.raise_for_status()

    except httpx.HTTPError as e:
        raise TwilioAPIError(
            f"Failed to download media from '{media_url}': {e}"
        )

    return response.content, response.headers.get(
        "Content-Type",
        "application/octet-stream",
    )