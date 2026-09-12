import base64
import hashlib
import hmac

from app.core.config import settings
from app.whatsapp_adapter.twilio_security import verify_twilio_signature


def _sign(url: str, params: dict[str, str], auth_token: str) -> str:
    data = url
    for key in sorted(params.keys()):
        data += key + params[key]
    return base64.b64encode(
        hmac.new(auth_token.encode(), data.encode("utf-8"), hashlib.sha1).digest()
    ).decode()


def test_valid_twilio_signature_accepted():
    settings.twilio_auth_token = "test_auth_token"
    url = "https://example.ngrok-free.app/api/v1/twilio/webhook"
    params = {"From": "whatsapp:+15551234567", "Body": "hello"}
    sig = _sign(url, params, "test_auth_token")
    assert verify_twilio_signature(url, params, sig) is True


def test_wrong_auth_token_rejected():
    settings.twilio_auth_token = "test_auth_token"
    url = "https://example.ngrok-free.app/api/v1/twilio/webhook"
    params = {"From": "whatsapp:+15551234567", "Body": "hello"}
    sig = _sign(url, params, "wrong_token")
    assert verify_twilio_signature(url, params, sig) is False


def test_tampered_params_rejected():
    settings.twilio_auth_token = "test_auth_token"
    url = "https://example.ngrok-free.app/api/v1/twilio/webhook"
    original_params = {"From": "whatsapp:+15551234567", "Body": "hello"}
    sig = _sign(url, original_params, "test_auth_token")

    tampered_params = {"From": "whatsapp:+15551234567", "Body": "something else entirely"}
    assert verify_twilio_signature(url, tampered_params, sig) is False


def test_missing_signature_rejected():
    settings.twilio_auth_token = "test_auth_token"
    url = "https://example.ngrok-free.app/api/v1/twilio/webhook"
    assert verify_twilio_signature(url, {"Body": "hi"}, None) is False


def test_no_auth_token_configured_rejects_everything():
    settings.twilio_auth_token = ""
    assert verify_twilio_signature("https://x.com/webhook", {}, "anything") is False
