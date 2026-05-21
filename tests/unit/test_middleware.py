"""Tests for custom middleware."""

import pytest


class TestSecurityHeaders:
    """Test that security headers are present on API responses."""

    @pytest.mark.asyncio
    async def test_health_has_security_headers(self, client):
        resp = await client.get("/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
        # X-XSS-Protection est obsolète (remplacé par CSP) — non envoyé
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    @pytest.mark.asyncio
    async def test_health_has_hsts(self, client):
        resp = await client.get("/health")
        hsts = resp.headers.get("Strict-Transport-Security", "")
        assert "max-age=" in hsts

    @pytest.mark.asyncio
    async def test_health_has_csp(self, client):
        resp = await client.get("/health")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "default-src" in csp
        assert "nonce-" in csp

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
        cache = resp.headers.get("Cache-Control", "")
        # Must contain no-store (+ possibly no-cache, Pragma)
        assert "no-store" in cache
