"""
Webhook signature verification.

Meta signs every webhook POST body with your app secret
(X-Hub-Signature-256 header, HMAC-SHA256). Without checking this,
anyone who discovers your webhook URL could POST fake "messages" and
have them processed as if they came from a real WhatsApp user —
this is the single most important check in the whole adapter.
"""
import hashlib
import hmac

from app.core.config import settings


def verify_signature(payload_bytes: bytes, signature_header: str | None) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    if not settings.whatsapp_app_secret:
        return False

    expected = hmac.new(
        settings.whatsapp_app_secret.encode(),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    provided = signature_header.removeprefix("sha256=")

    # constant-time comparison — a naive == leaks timing info that
    # could theoretically help an attacker forge a valid signature
    return hmac.compare_digest(expected, provided)
