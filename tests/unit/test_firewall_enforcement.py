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


def test_disabled_firewall_is_passthrough(monkeypatch):
    _patch_settings(monkeypatch, AI_FIREWALL_ENABLED=False)
    text = "Contact gerant@societe.fr"
    out, summary = _firewall.guard_outbound_prompt(text)
    assert out == text
    assert summary is None


def test_clean_prompt_returns_allow_summary(monkeypatch):
    _patch_settings(monkeypatch)
    text = "Résume le document [SOCIETE]."
    out, summary = _firewall.guard_outbound_prompt(text)
    assert out == text
    assert summary["verdict"] == "allow"


def test_prompt_redacted_in_normal_mode(monkeypatch):
    _patch_settings(monkeypatch, SENSITIVE_CLIENT_MODE=False)
    text = "Analyse, contact gerant@societe.fr."
    out, summary = _firewall.guard_outbound_prompt(text)
    assert "gerant@societe.fr" not in out
    assert summary["verdict"] == "redact"


def test_prompt_blocked_raises_http_400_in_sensitive_mode(monkeypatch):
    _patch_settings(monkeypatch, SENSITIVE_CLIENT_MODE=True)
    with pytest.raises(HTTPException) as exc:
        _firewall.guard_outbound_prompt("Analyse, contact gerant@societe.fr.")
    assert exc.value.status_code == 400


def test_prompt_blocked_raises_on_critical_even_in_normal_mode(monkeypatch):
    _patch_settings(monkeypatch, SENSITIVE_CLIENT_MODE=False)
    with pytest.raises(HTTPException):
        _firewall.guard_outbound_prompt("RIB FR76 3000 4000 0500 0012 3456 789")


def test_response_redacted_in_normal_mode(monkeypatch):
    _patch_settings(monkeypatch, SENSITIVE_CLIENT_MODE=False)
    text = "Le contact est marie.martin@cabinet.fr."
    out, summary = _firewall.guard_inbound_response(text)
    assert "marie.martin@cabinet.fr" not in out
    assert summary["verdict"] == "redact"


def test_response_block_returns_safe_placeholder_without_raising(monkeypatch):
    """A blocked response must NOT raise (the AI already ran) but must hide the leak."""
    _patch_settings(monkeypatch, SENSITIVE_CLIENT_MODE=False)
    text = "Le RIB est FR76 3000 4000 0500 0012 3456 789."
    out, summary = _firewall.guard_inbound_response(text)
    assert "FR76 3000 4000 0500 0012 3456 789" not in out
    assert summary["verdict"] == "block"
    assert out  # a non-empty safe message is returned
