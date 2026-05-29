"""Unit tests for the AI Firewall core scan engine (risk + verdict + redaction)."""

from app.services.firewall.risk import (
    ALLOW,
    BLOCK,
    REDACT,
    FirewallScan,
    scan_text,
)


def test_clean_anonymized_text_is_allowed():
    """Text already anonymized (tokens only) carries no residual PII -> allow."""
    text = "Le client [PERSONNE] a transmis la facture [REF_FACTURE] pour [MONTANT]."
    scan = scan_text(text, sensitive_mode=False)

    assert isinstance(scan, FirewallScan)
    assert scan.findings == []
    assert scan.risk_level == "low"
    assert scan.risk_score == 0.0
    assert scan.verdict == ALLOW
    assert scan.blocked is False
    assert scan.redacted is False
    assert scan.sanitized_text == text


def test_residual_email_is_redacted_in_normal_mode():
    """A leaked email in normal mode -> redact + sanitized text masks it."""
    text = "Contactez jean.dupont@example.com pour la suite."
    scan = scan_text(text, sensitive_mode=False)

    assert any(f.entity_type == "EMAIL" for f in scan.findings)
    assert scan.verdict == REDACT
    assert scan.redacted is True
    assert scan.blocked is False
    assert "jean.dupont@example.com" not in scan.sanitized_text
    assert "[EMAIL]" in scan.sanitized_text


def test_residual_email_is_blocked_in_sensitive_mode():
    """The same email in SENSITIVE_CLIENT_MODE -> hard block."""
    text = "Contactez jean.dupont@example.com pour la suite."
    scan = scan_text(text, sensitive_mode=True)

    assert scan.verdict == BLOCK
    assert scan.blocked is True


def test_iban_is_critical_and_blocked_in_all_modes():
    """A direct financial identifier (IBAN) is critical -> block even in normal mode."""
    text = "Virement sur FR76 3000 4000 0500 0012 3456 789 avant lundi."

    normal = scan_text(text, sensitive_mode=False)
    sensitive = scan_text(text, sensitive_mode=True)

    assert normal.risk_level == "critical"
    assert normal.verdict == BLOCK
    assert sensitive.verdict == BLOCK
    assert any(f.severity == "critical" for f in normal.findings)


def test_nss_is_critical():
    """French social security number is a critical direct identifier."""
    text = "Assuré n° 1 85 12 75 116 001 23 pour le dossier."
    scan = scan_text(text, sensitive_mode=False)

    assert scan.risk_level == "critical"
    assert any(f.entity_type == "NSS" for f in scan.findings)
    assert scan.verdict == BLOCK


def test_risk_score_is_bounded_and_increases_with_findings():
    """Risk score stays within 0-100 and grows with more residual PII."""
    one = scan_text("Email: a@b.fr", sensitive_mode=False)
    many = scan_text(
        "Email a@b.fr, tel 06 12 34 56 78, SIRET 552 100 554 00021",
        sensitive_mode=False,
    )

    assert 0.0 < one.risk_score <= 100.0
    assert 0.0 < many.risk_score <= 100.0
    assert many.risk_score >= one.risk_score


def test_findings_are_aggregated_by_type_with_counts():
    """Two emails of the same type aggregate into one finding with count=2."""
    text = "Ecrire a a@b.fr ou c@d.fr."
    scan = scan_text(text, sensitive_mode=False)

    email_findings = [f for f in scan.findings if f.entity_type == "EMAIL"]
    assert len(email_findings) == 1
    assert email_findings[0].count == 2


def test_scan_never_returns_raw_pii_in_finding_metadata():
    """Findings expose types/counts only — never the raw matched value (no leak in logs)."""
    text = "Contact secret@confidential.fr"
    scan = scan_text(text, sensitive_mode=False)

    for finding in scan.findings:
        assert "secret@confidential.fr" not in str(finding.__dict__)
