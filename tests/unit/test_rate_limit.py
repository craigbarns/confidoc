"""Tests for rate limiting configuration."""

from app.rate_limit import limiter, rate_limit_exceeded_handler


def test_limiter_exists():
    """Rate limiter should be configured."""
    assert limiter is not None


def test_rate_limit_handler_returns_429():
    """Custom handler should return 429 status."""
    from unittest.mock import MagicMock

    request = MagicMock()
    # RateLimitExceeded is an HTTPException subclass — create via mock
    exc = MagicMock()
    exc.detail = "10 per minute"
    response = rate_limit_exceeded_handler(request, exc)
    assert response.status_code == 429


def test_rate_limit_config_values():
    """Rate limit settings should have expected defaults."""
    from app.config import Settings
    s = Settings()
    assert s.RATE_LIMIT_LOGIN == "10/minute"
    assert s.RATE_LIMIT_UPLOAD == "30/minute"
    assert s.RATE_LIMIT_DEFAULT == "120/minute"
