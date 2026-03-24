"""Tests for auth endpoints."""

import pytest
from unittest.mock import AsyncMock, patch

from app.api.v1.auth import _check_rate_limit, _login_attempts


class TestRateLimit:
    """Test the in-memory rate limiter."""

    def setup_method(self):
        _login_attempts.clear()

    def test_allows_under_limit(self):
        for _ in range(9):
            _check_rate_limit("test:127.0.0.1")

    def test_blocks_over_limit(self):
        from fastapi import HTTPException

        for _ in range(10):
            _check_rate_limit("test:127.0.0.1")
        with pytest.raises(HTTPException) as exc_info:
            _check_rate_limit("test:127.0.0.1")
        assert exc_info.value.status_code == 429

    def test_separate_keys_independent(self):
        for _ in range(10):
            _check_rate_limit("test:10.0.0.1")
        # Different key should still work
        _check_rate_limit("test:10.0.0.2")


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
        from app.api.v1.auth import RecoveryResetRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RecoveryResetRequest(
                email="test@example.com",
                new_password="Ab1",
                recovery_token="tok",
            )

    def test_no_uppercase_rejected(self):
        from app.api.v1.auth import RecoveryResetRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RecoveryResetRequest(
                email="test@example.com",
                new_password="alllowercase1",
                recovery_token="tok",
            )

    def test_no_digit_rejected(self):
        from app.api.v1.auth import RecoveryResetRequest
        from pydantic import ValidationError

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
