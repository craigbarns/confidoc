"""Tests for auth endpoints."""

from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1.auth import _RATE_MAX, _RATE_WINDOW, _login_attempts_fallback


class TestRateLimitFallback:
    """Test the in-memory fallback rate limiter (used when Redis is unavailable)."""

    def setup_method(self):
        _login_attempts_fallback.clear()

    @pytest.mark.asyncio
    async def test_allows_under_limit(self):
        """Under the limit, no exception raised (Redis unavailable → fallback)."""
        from app.api.v1.auth import _check_rate_limit

        with patch("redis.asyncio.from_url", side_effect=Exception("no redis")):
            for _ in range(_RATE_MAX - 1):
                await _check_rate_limit("test:127.0.0.1")

    @pytest.mark.asyncio
    async def test_blocks_over_limit_fallback(self):
        """Fallback rate limiter blocks after _RATE_MAX attempts."""
        from fastapi import HTTPException

        from app.api.v1.auth import _check_rate_limit

        with patch("redis.asyncio.from_url", side_effect=Exception("no redis")):
            for _ in range(_RATE_MAX):
                await _check_rate_limit("test:127.0.0.2")
            with pytest.raises(HTTPException) as exc_info:
                await _check_rate_limit("test:127.0.0.2")
            assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_separate_keys_independent_fallback(self):
        """Different IP keys are tracked independently in the fallback."""
        from app.api.v1.auth import _check_rate_limit

        with patch("redis.asyncio.from_url", side_effect=Exception("no redis")):
            for _ in range(_RATE_MAX):
                await _check_rate_limit("test:10.0.0.1")
            # Different key should still work
            await _check_rate_limit("test:10.0.0.3")


class TestRecoveryResetRequest:
    """Test password validation in RecoveryResetRequest."""

    def test_valid_password(self):
        from app.api.v1.auth import RecoveryResetRequest

        req = RecoveryResetRequest(
            email="test@example.com",
            new_password="SecurePass1",
            recovery_token="tok",
        )
        assert req.new_password == "SecurePass1"

    def test_short_password_rejected(self):
        from pydantic import ValidationError

        from app.api.v1.auth import RecoveryResetRequest

        with pytest.raises(ValidationError):
            RecoveryResetRequest(
                email="test@example.com",
                new_password="Ab1",
                recovery_token="tok",
            )

    def test_no_uppercase_rejected(self):
        from pydantic import ValidationError

        from app.api.v1.auth import RecoveryResetRequest

        with pytest.raises(ValidationError):
            RecoveryResetRequest(
                email="test@example.com",
                new_password="alllowercase1",
                recovery_token="tok",
            )

    def test_no_digit_rejected(self):
        from pydantic import ValidationError

        from app.api.v1.auth import RecoveryResetRequest

        with pytest.raises(ValidationError):
            RecoveryResetRequest(
                email="test@example.com",
                new_password="NoDigitsHere",
                recovery_token="tok",
            )


class TestLoginEndpoint:
    """Test the login API endpoint via ASGI client."""

    @pytest.mark.asyncio
    async def test_login_missing_body(self, client):
        resp = await client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_login_invalid_email(self, client):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "not-an-email", "password": "test"},
        )
        assert resp.status_code == 422


class TestBootstrapAdmin:
    """Test the bootstrap-admin endpoint."""

    @pytest.mark.asyncio
    async def test_bootstrap_missing_fields(self, client):
        resp = await client.post("/api/v1/auth/bootstrap-admin", json={})
        assert resp.status_code == 422
