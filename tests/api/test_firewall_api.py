"""API tests for the AI Firewall governance & demo endpoints."""

import pytest

from app.api.v1 import firewall as firewall_api


@pytest.fixture
def _patched_stats(monkeypatch):
    async def _fake_stats():
        return {
            "available": True,
            "prompts_scanned": 12,
            "responses_scanned": 10,
            "redactions": 3,
            "blocks": 1,
            "critical_risks": 1,
        }

    async def _fake_events(limit: int = 20):
        return [
            {"direction": "response", "verdict": "block", "risk_level": "critical", "findings": []}
        ]

    monkeypatch.setattr(firewall_api, "get_stats", _fake_stats)
    monkeypatch.setattr(firewall_api, "get_recent_events", _fake_events)


@pytest.mark.asyncio
async def test_firewall_stats_is_public_and_returns_counters(client, _patched_stats) -> None:
    """The dashboard must be viewable without login for demos."""
    resp = await client.get("/api/v1/firewall/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["firewall"]["enabled"] is True
    assert body["firewall"]["mode"] in {"redact", "strict"}
    assert body["counters"]["prompts_scanned"] == 12
    assert body["counters"]["blocks"] == 1
    assert isinstance(body["recent_events"], list)


@pytest.mark.asyncio
async def test_firewall_demo_intercepts_iban_leak(client, monkeypatch) -> None:
    """The live demo must allow a clean prompt, redact an email, and block an IBAN."""

    async def _noop_record(_scan):
        return None

    async def _fake_stats():
        return {
            "available": True,
            "prompts_scanned": 0,
            "responses_scanned": 0,
            "redactions": 0,
            "blocks": 0,
            "critical_risks": 0,
        }

    async def _fake_events(limit: int = 20):
        return []

    monkeypatch.setattr(firewall_api, "record_scan", _noop_record)
    monkeypatch.setattr(firewall_api, "get_stats", _fake_stats)
    monkeypatch.setattr(firewall_api, "get_recent_events", _fake_events)

    resp = await client.post("/api/v1/firewall/demo")
    assert resp.status_code == 200
    steps = resp.json()["steps"]
    assert len(steps) == 3

    verdicts = [s["firewall"]["verdict"] for s in steps]
    assert verdicts[0] == "allow"
    assert verdicts[1] == "redact"
    assert verdicts[2] == "block"

    # The IBAN must never appear in the blocked step's output.
    assert "FR76" not in steps[2]["output"]
