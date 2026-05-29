"""API tests for the AI Firewall governance endpoint."""

import uuid

import pytest

from app.api.deps import get_current_user
from app.api.v1 import firewall as firewall_api
from app.main import app


@pytest.fixture
def _firewall_setup(monkeypatch):
    user = type("User", (), {"id": uuid.uuid4(), "is_active": True, "email": "dpo@confidoc.test"})()

    async def _override_user():
        return user

    app.dependency_overrides[get_current_user] = _override_user

    async def _fake_stats():
        return {
            "available": True,
            "prompts_scanned": 12,
            "responses_scanned": 10,
            "redactions": 3,
            "blocks": 1,
            "critical_risks": 1,
        }

    monkeypatch.setattr(firewall_api, "get_stats", _fake_stats)

    yield app

    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_firewall_stats_returns_counters(client, _firewall_setup) -> None:
    resp = await client.get(
        "/api/v1/firewall/stats",
        headers={"Authorization": "Bearer fake-token"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["firewall"]["enabled"] is True
    assert body["firewall"]["mode"] in {"redact", "strict"}
    assert body["counters"]["prompts_scanned"] == 12
    assert body["counters"]["responses_scanned"] == 10
    assert body["counters"]["blocks"] == 1
    assert body["counters"]["critical_risks"] == 1


@pytest.mark.asyncio
async def test_firewall_stats_requires_authentication(client) -> None:
    """Without an auth override the endpoint must not return data."""
    resp = await client.get("/api/v1/firewall/stats")
    assert resp.status_code in {401, 403}
