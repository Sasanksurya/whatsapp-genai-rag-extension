"""
Twilio webhook signature verification — TEMPORARY debug version.

Adds a check for hidden whitespace/quote characters around the auth
token, which is a very common invisible cause of "everything looks
right but validation still fails" when pasting secrets into .env.
"""
import logging

from twilio.request_validator import RequestValidator

from app.core.config import settings

logger = logging.getLogger(__name__)


def verify_twilio_signature(
    url: str,
    params: dict[str, str],
    signature_header: str | None,
) -> bool:
    raw_token = settings.twilio_auth_token
    stripped_token = raw_token.strip()

    logger.warning(f"[DEBUG] URL used for validation: {url}")
    logger.warning(f"[DEBUG] Signature header received from Twilio: {signature_header}")
    logger.warning(f"[DEBUG] Raw token length: {len(raw_token)}")
    logger.warning(f"[DEBUG] Stripped token length: {len(stripped_token)}")
    logger.warning(f"[DEBUG] Whitespace detected around token: {len(raw_token) != len(stripped_token)}")
    if raw_token:
        logger.warning(f"[DEBUG] First char of token: {repr(raw_token[0])}")
        logger.warning(f"[DEBUG] Last char of token: {repr(raw_token[-1])}")

    if not signature_header or not stripped_token:
        logger.warning("[DEBUG] Missing signature header or auth token — rejecting.")
        return False

    validator = RequestValidator(stripped_token)
    result = validator.validate(url, params, signature_header)

    logger.warning(f"[DEBUG] Validation result: {result}")

    return result