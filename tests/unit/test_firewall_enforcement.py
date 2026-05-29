"""Unit tests for the API-layer AI Firewall enforcement helpers."""

import pytest
from fastapi import HTTPException

from app.api.v1 import _firewall
from app.config import Settings


def _patch_settings(monkeypatch, **overrides) -> None:
    base = {"AI_FIREWALL_ENABLED": True, "SENSITIVE_CLIENT_MODE": False}
    base.update(overrides)
    settings = Settings(**base)
    monkeypatch.setattr(_firewall, "get_settings", lambda: settings)

    # Stub the Redis-backed counter so unit tests stay hermetic and fast.
    async def _noop_record(_scan):
        return None

    monkeypatch.setattr(_firewall, "record_scan", _noop_record)


async def test_disabled_firewall_is_passthrough(monkeypatch):
    _patch_settings(monkeypatch, AI_FIREWALL_ENABLED=False)
    text = "Contact gerant@societe.fr"
    out, summary = await _firewall.guard_outbound_prompt(text)
    assert out == text
    assert summary is None


async def test_clean_prompt_returns_allow_summary(monkeypatch):
    _patch_settings(monkeypatch)
    text = "Résume le document [SOCIETE]."
    out, summary = await _firewall.guard_outbound_prompt(text)
    assert out == text
    assert summary["verdict"] == "allow"


async def test_prompt_redacted_in_normal_mode(monkeypatch):
    _patch_settings(monkeypatch, SENSITIVE_CLIENT_MODE=False)
    text = "Analyse, contact gerant@societe.fr."
    out, summary = await _firewall.guard_outbound_prompt(text)
    assert "gerant@societe.fr" not in out
    assert summary["verdict"] == "redact"


async def test_prompt_blocked_raises_http_400_in_sensitive_mode(monkeypatch):
    _patch_settings(monkeypatch, SENSITIVE_CLIENT_MODE=True)
    with pytest.raises(HTTPException) as exc:
        await _firewall.guard_outbound_prompt("Analyse, contact gerant@societe.fr.")
    assert exc.value.status_code == 400


async def test_prompt_blocked_raises_on_critical_even_in_normal_mode(monkeypatch):
    _patch_settings(monkeypatch, SENSITIVE_CLIENT_MODE=False)
    with pytest.raises(HTTPException):
        await _firewall.guard_outbound_prompt("RIB FR76 3000 4000 0500 0012 3456 789")


async def test_response_redacted_in_normal_mode(monkeypatch):
    _patch_settings(monkeypatch, SENSITIVE_CLIENT_MODE=False)
    text = "Le contact est marie.martin@cabinet.fr."
    out, summary = await _firewall.guard_inbound_response(text)
    assert "marie.martin@cabinet.fr" not in out
    assert summary["verdict"] == "redact"


async def test_response_block_returns_safe_placeholder_without_raising(monkeypatch):
    """A blocked response must NOT raise (the AI already ran) but must hide the leak."""
    _patch_settings(monkeypatch, SENSITIVE_CLIENT_MODE=False)
    text = "Le RIB est FR76 3000 4000 0500 0012 3456 789."
    out, summary = await _firewall.guard_inbound_response(text)
    assert "FR76 3000 4000 0500 0012 3456 789" not in out
    assert summary["verdict"] == "block"
    assert out  # a non-empty safe message is returned


async def test_record_scan_is_invoked_for_every_scan(monkeypatch):
    """Each guarded scan must be recorded for the governance counters."""
    _patch_settings(monkeypatch)
    recorded: list = []

    async def _capture(scan):
        recorded.append(scan)

    monkeypatch.setattr(_firewall, "record_scan", _capture)
    await _firewall.guard_outbound_prompt("Résume le document [SOCIETE].")
    assert len(recorded) == 1
    assert recorded[0].direction == "prompt"
