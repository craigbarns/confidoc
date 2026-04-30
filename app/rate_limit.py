"""ConfiDoc Backend — Rate limiting with slowapi."""

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import get_settings


def _key_func(request: Request) -> str:
    """Rate limit key: authenticated user ID if available, else IP address."""
    if hasattr(request.state, "user") and request.state.user:
        return f"user:{request.state.user.id}"
    return get_remote_address(request)


settings = get_settings()


def _limiter_storage_uri() -> str:
    """Backend slowapi : utiliser Redis hors dev pour multi-instance.

    En développement local, Redis est souvent absent : le stockage Redis faisait
    planter le middleware de rate limit (ConnectionError → HTTP 500), notamment
    sur POST /uploads avant même d'atteindre le handler.
    """
    if settings.APP_ENV == "development":
        return "memory://"
    return settings.REDIS_URL


limiter = Limiter(
    key_func=_key_func,
    default_limits=[settings.RATE_LIMIT_DEFAULT],
    storage_uri=_limiter_storage_uri(),
    strategy="fixed-window",
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom handler for rate limit exceeded errors."""
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Trop de requêtes. Veuillez patienter avant de réessayer.",
            "retry_after": exc.detail,
        },
        headers={"Retry-After": str(getattr(exc, "retry_after", 60))},
    )
