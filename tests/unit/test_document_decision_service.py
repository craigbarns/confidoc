"""Tests for user-facing document decision labels."""

from app.services.document_decision_service import (
    build_document_decision,
    build_timeline_steps,
    normalize_risk_score,
)


def test_normalize_risk_score_accepts_fraction_and_percent() -> None:
    assert normalize_risk_score(0.42) == 42
    assert normalize_risk_score(42) == 42
    assert normalize_risk_score(120) == 100


def test_medium_score_maps_to_review_recommended() -> None:
    decision = build_document_decision(
        status="ready",
        risk_score=55,
        risk_level="medium",
        human_validated=False,
        entity_types=["EMAIL"],
        detections_count=1,
        audit_events_count=3,
    )

    assert decision["code"] == "review_recommended"
    assert decision["label"] == "Revue recommandée"
    assert decision["decision"] == "Vous devez vérifier avant export"
    assert "Email détecté" in decision["reasons"]


def test_critical_score_blocks_export() -> None:
    decision = build_document_decision(
        status="ready",
        risk_score=0.9,
        risk_level="critical",
        human_validated=False,
        entity_types=["IBAN"],
        detections_count=1,
        audit_events_count=3,
    )

    assert decision["code"] == "blocked"
    assert decision["label"] == "Export bloqué"
    assert "Export bloqué" in decision["decision"]
    assert "IBAN détecté" in decision["reasons"]


def test_human_validation_returns_manual_status() -> None:
    decision = build_document_decision(
        status="ready",
        risk_score=5,
        risk_level="low",
        human_validated=True,
        entity_types=[],
        detections_count=0,
        audit_events_count=3,
    )

    assert decision["code"] == "human_validated"
    assert decision["label"] == "Validé manuellement"
    assert decision["decision"] == "Vous pouvez exporter"


def test_timeline_marks_ready_document_export_step_done() -> None:
    timeline = build_timeline_steps(
        status="ready",
        extraction_done=True,
        anonymization_done=True,
        risk_score_done=True,
        human_validated=True,
        export_allowed=True,
    )

    assert [step["key"] for step in timeline] == [
        "upload",
        "ocr",
        "detect",
        "anonymize",
        "score",
        "review",
        "export",
    ]
    assert timeline[-1]["state"] == "done"
