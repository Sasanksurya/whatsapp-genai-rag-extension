import importlib

import pytest
from fastapi import HTTPException

from app.core import auth as auth_module


@pytest.fixture(autouse=True)
def _isolated_key_store(tmp_path, monkeypatch):
    monkeypatch.setattr(auth_module, "API_KEYS_FILE", tmp_path / "api_keys.json")
    yield


def test_register_and_authenticate_roundtrip():
    key = auth_module.create_api_key("owner_a")
    owner = auth_module.get_current_owner(api_key=key)
    assert owner == "owner_a"


def test_invalid_key_rejected():
    with pytest.raises(HTTPException) as exc_info:
        auth_module.get_current_owner(api_key="not_a_real_key")
    assert exc_info.value.status_code == 401


def test_missing_key_rejected():
    with pytest.raises(HTTPException) as exc_info:
        auth_module.get_current_owner(api_key=None)
    assert exc_info.value.status_code == 401


def test_revoked_key_no_longer_works():
    key = auth_module.create_api_key("owner_b")
    assert auth_module.revoke_api_key(key) is True
    with pytest.raises(HTTPException):
        auth_module.get_current_owner(api_key=key)


def test_rate_limit_blocks_after_threshold():
    from app.core.rate_limit import _requests, enforce_rate_limit
    from app.core.config import settings

    settings.rate_limit_max_requests = 3
    settings.rate_limit_window_seconds = 60
    _requests.clear()

    for _ in range(3):
        enforce_rate_limit("owner_x")

    with pytest.raises(HTTPException) as exc_info:
        enforce_rate_limit("owner_x")
    assert exc_info.value.status_code == 429


def test_rate_limit_is_per_owner():
    from app.core.rate_limit import _requests, enforce_rate_limit
    from app.core.config import settings

    settings.rate_limit_max_requests = 1
    settings.rate_limit_window_seconds = 60
    _requests.clear()

    enforce_rate_limit("owner_y")
    enforce_rate_limit("owner_z")  # different owner, should not raise


def test_drive_token_encryption_roundtrip(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    from app.core.config import settings

    settings.drive_token_encryption_key = Fernet.generate_key().decode()

    import app.mcp.token_store as ts
    importlib.reload(ts)
    monkeypatch.setattr(ts, "TOKEN_DIR", tmp_path)

    ts.save_token("owner_drive", {"token": "secret_value"})
    raw = ts._path_for("owner_drive").read_bytes()
    assert b"secret_value" not in raw  # not stored in plaintext

    loaded = ts.load_token("owner_drive")
    assert loaded == {"token": "secret_value"}


def test_drive_token_save_fails_without_key(tmp_path, monkeypatch):
    from app.core.config import settings

    settings.drive_token_encryption_key = ""
    import app.mcp.token_store as ts
    importlib.reload(ts)
    monkeypatch.setattr(ts, "TOKEN_DIR", tmp_path)

    with pytest.raises(ts.EncryptionNotConfiguredError):
        ts.save_token("owner_x", {"a": 1})
