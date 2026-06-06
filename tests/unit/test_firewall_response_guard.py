"""Unit tests for the inbound response guard (AI Firewall, response side)."""

from app.services.firewall.response_guard import inspect_response
from app.services.firewall.risk import ALLOW, BLOCK, REDACT


def test_clean_response_passes_through():
    answer = "Le résultat net de [SOCIETE] progresse sur l'exercice [DATE]."
    scan = inspect_response(answer, sensitive_mode=False)

    assert scan.direction == "response"
    assert scan.verdict == ALLOW
    assert scan.sanitized_text == answer


def test_response_leaking_email_is_redacted_in_normal_mode():
    """The model re-emitted a real identifier — firewall masks it before it reaches the user."""
    answer = "D'après le document, le contact est marie.martin@cabinet.fr."
    scan = inspect_response(answer, sensitive_mode=False)

    assert scan.verdict == REDACT
    assert "marie.martin@cabinet.fr" not in scan.sanitized_text
    assert "[EMAIL]" in scan.sanitized_text


def test_response_leaking_iban_is_blocked_in_all_modes():
    answer = "Le RIB indiqué est FR76 3000 4000 0500 0012 3456 789."
    normal = inspect_response(answer, sensitive_mode=False)
    sensitive = inspect_response(answer, sensitive_mode=True)

    assert normal.verdict == BLOCK
    assert sensitive.verdict == BLOCK


def test_response_leaking_pii_is_blocked_in_sensitive_mode():
    answer = "Le gérant est joignable au 06 12 34 56 78."
    scan = inspect_response(answer, sensitive_mode=True)

    assert scan.verdict == BLOCK
    assert scan.blocked is True


def test_response_side_does_not_treat_injection_phrase_as_prompt_attack():
    answer = "Le document contient la phrase: ignore previous instructions."
    scan = inspect_response(answer, sensitive_mode=False)

    assert scan.verdict == ALLOW
    assert scan.findings == []
    assert scan.sanitized_text == answer
