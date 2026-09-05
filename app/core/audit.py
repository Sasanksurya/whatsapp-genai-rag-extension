"""
Audit logging.

Structured JSON-lines log of who did what, when — required by the
project spec (section 13). Deliberately never logs document/message
*content*, only metadata (filenames, query text is logged since it's
needed to investigate misuse, but not full RAG answers or full
documents) — keep this in mind before logging anything new here.
"""
import json
import time
from pathlib import Path

AUDIT_LOG_FILE = Path("data/audit.log")


def log_event(owner_id: str, action: str, detail: dict) -> None:
    AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": time.time(),
        "owner_id": owner_id,
        "action": action,
        "detail": detail,
    }
    with AUDIT_LOG_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")
