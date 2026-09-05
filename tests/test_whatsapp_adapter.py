import hashlib
import hmac

from app.core.config import settings
from app.whatsapp_adapter.payload_parser import extract_messages
from app.whatsapp_adapter.security import verify_signature


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_accepted():
    settings.whatsapp_app_secret = "test_secret"
    body = b'{"entry": []}'
    assert verify_signature(body, _sign(body, "test_secret")) is True


def test_tampered_body_rejected():
    settings.whatsapp_app_secret = "test_secret"
    body = b'{"entry": []}'
    sig = _sign(body, "test_secret")
    tampered = b'{"entry": ["injected"]}'
    assert verify_signature(tampered, sig) is False


def test_wrong_secret_rejected():
    settings.whatsapp_app_secret = "test_secret"
    body = b'{"entry": []}'
    assert verify_signature(body, _sign(body, "wrong_secret")) is False


def test_missing_signature_rejected():
    settings.whatsapp_app_secret = "test_secret"
    assert verify_signature(b"{}", None) is False


def test_extract_text_message():
    payload = {
        "entry": [{"changes": [{"value": {"messages": [
            {"from": "15551234567", "type": "text", "text": {"body": "hello"}}
        ]}}]}]
    }
    msgs = extract_messages(payload)
    assert len(msgs) == 1
    assert msgs[0].message_type == "text"
    assert msgs[0].text == "hello"
    assert msgs[0].from_phone == "15551234567"


def test_extract_document_message():
    payload = {
        "entry": [{"changes": [{"value": {"messages": [
            {"from": "1", "type": "document", "document": {"id": "M1", "filename": "f.pdf"}}
        ]}}]}]
    }
    msgs = extract_messages(payload)
    assert msgs[0].message_type == "document"
    assert msgs[0].media_id == "M1"
    assert msgs[0].filename == "f.pdf"


def test_status_update_produces_no_messages():
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"status": "delivered"}]}}]}]}
    assert extract_messages(payload) == []


def test_empty_payload_does_not_crash():
    assert extract_messages({}) == []
