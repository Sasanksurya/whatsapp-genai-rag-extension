"""
API key authentication.

This is what turns `owner_id` from "whatever the client claims" into
"whoever this key was actually issued to." Every endpoint that used
to accept `owner_id` in the request body now derives it from
`Depends(get_current_owner)` instead — the client can no longer
impersonate another owner just by changing a string in the JSON body.

DEMO SIMPLIFICATION: `/auth/register` lets anyone mint a key for any
owner_id name they choose, with no real identity check. That's fine
for local testing but is NOT how this should work once WhatsApp is
wired up (Phase 6) — there, owner_id should be derived from the
verified WhatsApp sender identity (phone number via the official
integration), not self-declared.

Keys are stored as SHA-256 hashes, never in plaintext — the raw key
is shown to the caller exactly once, at creation time, same pattern
as GitHub personal access tokens / API keys generally.
"""
import hashlib
import json
import secrets
from pathlib import Path

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

API_KEYS_FILE = Path("data/api_keys.json")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _load_keys() -> dict:
    if not API_KEYS_FILE.exists():
        return {}
    return json.loads(API_KEYS_FILE.read_text())


def _save_keys(data: dict) -> None:
    API_KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    API_KEYS_FILE.write_text(json.dumps(data))


def create_api_key(owner_id: str) -> str:
    raw_key = f"wgk_{secrets.token_urlsafe(32)}"
    keys = _load_keys()
    keys[_hash_key(raw_key)] = owner_id
    _save_keys(keys)
    return raw_key


def revoke_api_key(raw_key: str) -> bool:
    keys = _load_keys()
    hashed = _hash_key(raw_key)
    if hashed in keys:
        del keys[hashed]
        _save_keys(keys)
        return True
    return False


def get_current_owner(api_key: str | None = Security(api_key_header)) -> str:
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header. Call /api/v1/auth/register first.",
        )
    keys = _load_keys()
    owner_id = keys.get(_hash_key(api_key))
    if owner_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")
    return owner_id
