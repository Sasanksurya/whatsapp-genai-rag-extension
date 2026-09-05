"""
Adds standard security response headers to every response.

Small but standard hardening: stops the API being framed in a hidden
iframe (clickjacking), stops browsers MIME-sniffing responses into
something they're not, and disables caching of potentially sensitive
JSON responses.
"""
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        return response
