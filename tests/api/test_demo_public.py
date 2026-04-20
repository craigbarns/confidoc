"""Tests for the public demo endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_public_demo_requires_no_auth(client):
    payload = {
        "status": "ready",
        "original_excerpt": "Societe: DUPONT CONSEIL SAS",
        "anonymized_excerpt": "[SOCIETE_1]",
        "detections_count": 1,
        "entity_summary": {"SOCIETE": 1},
        "risk": {"score": 0.0, "level": "low"},
    }

    with patch("app.services.demo_service.get_demo_result", new_callable=AsyncMock) as get_demo:
        get_demo.return_value = payload
        resp = await client.get("/api/v1/demo/public")

    assert resp.status_code == 200
    assert resp.json()["anonymized_excerpt"] == "[SOCIETE_1]"


@pytest.mark.asyncio
async def test_public_demo_warming_up_returns_202(client):
    with patch("app.services.demo_service.get_demo_result", new_callable=AsyncMock) as get_demo:
        get_demo.return_value = None
        resp = await client.get("/api/v1/demo/public")

    assert resp.status_code == 202
    assert resp.json()["status"] == "warming_up"
