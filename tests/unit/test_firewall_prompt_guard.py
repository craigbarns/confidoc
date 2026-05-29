"""Unit tests for the outbound prompt guard (AI Firewall, prompt side)."""

from app.services.firewall.prompt_guard import inspect_prompt
from app.services.firewall.risk import ALLOW, BLOCK, REDACT


def test_clean_prompt_passes_through_unchanged():
    prompt = "Résume le document anonymisé [SOCIETE] pour l'exercice [DATE]."
    scan = inspect_prompt(prompt, sensitive_mode=False)

    assert scan.direction == "prompt"
    assert scan.verdict == ALLOW
    assert scan.sanitized_text == prompt


def test_prompt_with_residual_pii_is_redacted_in_normal_mode():
    prompt = "Analyse le bilan de la société, contact gerant@societe.fr."
    scan = inspect_prompt(prompt, sensitive_mode=False)

    assert scan.verdict == REDACT
    assert "gerant@societe.fr" not in scan.sanitized_text


def test_prompt_with_residual_pii_is_blocked_in_sensitive_mode():
    prompt = "Analyse le bilan, contact gerant@societe.fr."
    scan = inspect_prompt(prompt, sensitive_mode=True)

    assert scan.verdict == BLOCK
    assert scan.blocked is True


def test_empty_prompt_is_allowed():
    scan = inspect_prompt("", sensitive_mode=False)
    assert scan.verdict == ALLOW
    assert scan.findings == []
