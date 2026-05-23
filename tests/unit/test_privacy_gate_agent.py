import pytest

from app.services.agents.privacy_gate import run_privacy_gate


@pytest.mark.asyncio
async def test_privacy_gate_allows_low_risk_ready_document() -> None:
    result = await run_privacy_gate(
        document_id="doc-low",
        requested_action="external_ai",
        status="ready",
        risk_score=0.08,
        risk_level="low",
        human_validated=False,
        anonymized_text_available=True,
        detections_count=2,
        entity_types=["EMAIL"],
        audit_events_count=3,
    )

    assert result["decision"] == "allow"
    assert result["requested_action"] == "external_ai"
    assert result["risk_score"] == 8
    assert "Texte anonymisé uniquement" in result["allowed_controls"]


@pytest.mark.asyncio
async def test_privacy_gate_blocks_document_without_anonymized_text() -> None:
    result = await run_privacy_gate(
        document_id="doc-uploaded",
        requested_action="export",
        status="uploaded",
        risk_score=0,
        risk_level="low",
        anonymized_text_available=False,
        audit_events_count=1,
    )

    assert result["decision"] == "block"
    assert "Finaliser l'OCR" in result["required_actions"][0]
    assert "document_not_ready" in result["evidence"]["flags"]


@pytest.mark.asyncio
async def test_privacy_gate_blocks_critical_external_action() -> None:
    result = await run_privacy_gate(
        document_id="doc-critical",
        requested_action="share",
        status="ready",
        risk_score=92,
        risk_level="critical",
        human_validated=True,
        anonymized_text_available=True,
        entity_types=["IBAN", "SIRET"],
        audit_events_count=5,
    )

    assert result["decision"] == "block"
    assert any("critique" in reason for reason in result["reasons"])
    assert result["evidence"]["risk_level"] == "critical"


@pytest.mark.asyncio
async def test_privacy_gate_requires_review_for_high_risk_without_validation() -> None:
    result = await run_privacy_gate(
        document_id="doc-high",
        requested_action="external_ai",
        status="ready",
        risk_score=0.71,
        risk_level="high",
        human_validated=False,
        anonymized_text_available=True,
        entity_types=["BANK"],
        audit_events_count=4,
    )

    assert result["decision"] == "human_review_required"
    assert any("validation humaine" in reason for reason in result["reasons"])
    assert "high_risk_without_human_validation" in result["evidence"]["flags"]


@pytest.mark.asyncio
async def test_privacy_gate_allows_internal_review_for_high_risk_document() -> None:
    result = await run_privacy_gate(
        document_id="doc-high-internal",
        requested_action="internal_review",
        status="ready",
        risk_score=0.71,
        risk_level="high",
        human_validated=False,
        anonymized_text_available=True,
        entity_types=["BANK"],
        audit_events_count=4,
    )

    assert result["decision"] == "allow"
    assert "high_risk_without_human_validation" in result["evidence"]["flags"]
    assert result["warnings"]
