"""Tests for custom middleware."""

import pytest


class TestSecurityHeaders:
    """Test that security headers are present on API responses."""

    @pytest.mark.asyncio
    async def test_health_has_security_headers(self, client):
        resp = await client.get("/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("X-XSS-Protection") == "1; mode=block"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    @pytest.mark.asyncio
    async def test_request_id_header(self, client):
        resp = await client.get("/health")
        assert resp.headers.get("X-Request-ID") is not None

    @pytest.mark.asyncio
    async def test_custom_request_id_echoed(self, client):
        resp = await client.get("/health", headers={"X-Request-ID": "my-test-id"})
        assert resp.headers.get("X-Request-ID") == "my-test-id"

    @pytest.mark.asyncio
    async def test_server_timing_header(self, client):
        resp = await client.get("/health")
        timing = resp.headers.get("Server-Timing")
        assert timing is not None
        assert "total;dur=" in timing

    @pytest.mark.asyncio
    async def test_api_no_cache(self, client):
        resp = await client.get("/api/v1/auth/login")
        # Even on error, Cache-Control should be set for API paths
        cache = resp.headers.get("Cache-Control")
        assert cache == "no-store"
