"""ConfiDoc — Tests health endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_health_check(client: AsyncClient):
    """Le health check doit retourner 200 et status healthy."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "confidoc-backend"


@pytest.mark.anyio
async def test_health_response_structure(client: AsyncClient):
    """Le health check retourne la structure attendue."""
    response = await client.get("/health")
    data = response.json()
    assert "status" in data
    assert "service" in data
