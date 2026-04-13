"""ConfiDoc Backend — Middleware stack (request ID, security headers, timing)."""

import hashlib
import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to every request for traceability."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id

        # Bind to structlog context for all downstream logging
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard security headers to all responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        # HSTS — force HTTPS for 1 year, including subdomains
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )

        # CSP — inline styles replaced by a per-response nonce so 'unsafe-inline' is removed.
        # The nonce is injected into templates via request.state for server-rendered pages.
        nonce = hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:16]
        request.state.csp_nonce = nonce
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}'; "
            f"style-src 'self' 'nonce-{nonce}'; "
            "img-src 'self' data: blob:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )

        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache"
            response.headers["Pragma"] = "no-cache"

        return response


class TimingMiddleware(BaseHTTPMiddleware):
    """Log request duration and add Server-Timing header."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        response.headers["Server-Timing"] = f"total;dur={duration_ms:.1f}"

        # Log slow requests (>2s)
        if duration_ms > 2000:
            logger = structlog.get_logger("timing")
            logger.warning(
                "slow_request",
                path=request.url.path,
                method=request.method,
                duration_ms=round(duration_ms, 1),
            )

        return response
