"""
Rate limiting — per-owner sliding window, in-memory.

Keyed by owner_id (post-authentication), not by IP — this matters
because in the real WhatsApp deployment, all traffic will originate
from the same few WhatsApp/Meta infrastructure IPs, so per-IP limits
would be meaningless. Per-owner is what actually stops one user from
exhausting the shared Groq free-tier quota for everyone else.

In-memory like the conversation store — same upgrade path to Redis
applies here for a multi-process deployment.
"""
import time
from collections import defaultdict

from fastapi import HTTPException, status

from app.core.config import settings

_requests: dict[str, list[float]] = defaultdict(list)


def enforce_rate_limit(owner_id: str) -> None:
    now = time.monotonic()
    window_start = now - settings.rate_limit_window_seconds

    timestamps = _requests[owner_id]
    # drop anything outside the window
    while timestamps and timestamps[0] < window_start:
        timestamps.pop(0)

    if len(timestamps) >= settings.rate_limit_max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Rate limit exceeded: max {settings.rate_limit_max_requests} "
                f"requests per {settings.rate_limit_window_seconds}s. Try again shortly."
            ),
        )

    timestamps.append(now)
