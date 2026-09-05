"""
Per-owner OAuth token storage — encrypted at rest.

Uses Fernet (symmetric encryption) keyed by DRIVE_TOKEN_ENCRYPTION_KEY
from settings. This replaces the Phase 4 plaintext-JSON version that
was explicitly flagged as demo-only — tokens are real credentials
that grant read access to a user's Google Drive, so they're treated
accordingly now.

If no encryption key is configured, this fails loudly rather than
silently falling back to plaintext — better to break obviously than
to store secrets unencrypted without anyone noticing.
"""
import json
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

TOKEN_DIR = Path("data/drive_tokens")


class EncryptionNotConfiguredError(Exception):
    pass


def _get_fernet() -> Fernet:
    key = settings.drive_token_encryption_key
    if not key:
        raise EncryptionNotConfiguredError(
            "DRIVE_TOKEN_ENCRYPTION_KEY is not set. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\" "
            "and add it to your .env file."
        )
    return Fernet(key.encode())


def _path_for(owner_id: str) -> Path:
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = "".join(c for c in owner_id if c.isalnum() or c in "-_")
    return TOKEN_DIR / f"{safe_id}.enc"


def save_token(owner_id: str, token_data: dict) -> None:
    fernet = _get_fernet()
    plaintext = json.dumps(token_data).encode()
    encrypted = fernet.encrypt(plaintext)
    _path_for(owner_id).write_bytes(encrypted)


def load_token(owner_id: str) -> dict | None:
    path = _path_for(owner_id)
    if not path.exists():
        return None
    fernet = _get_fernet()
    try:
        plaintext = fernet.decrypt(path.read_bytes())
    except InvalidToken:
        raise EncryptionNotConfiguredError(
            "Could not decrypt stored Drive token — DRIVE_TOKEN_ENCRYPTION_KEY "
            "may have changed since this token was saved. Re-authorize via "
            "/mcp/drive/auth-url."
        )
    return json.loads(plaintext)


def delete_token(owner_id: str) -> None:
    path = _path_for(owner_id)
    if path.exists():
        path.unlink()
