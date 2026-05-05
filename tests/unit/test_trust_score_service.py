"""Tests for Trust Score / AI Readiness scoring."""

from app.services.trust_score_service import (
    compute_document_trust_score,
    compute_portfolio_trust_score,
    normalize_risk_percent,
)


def test_normalize_risk_percent_accepts_fraction_or_percent():
    assert normalize_risk_percent(None) == 0.0
    assert normalize_risk_percent(0.42) == 42
    assert normalize_risk_percent(42) == 42
    assert normalize_risk_percent(150) == 100


def test_ready_low_risk_document_is_ai_ready():
    score = compute_document_trust_score(
        status="ready",
        risk_score=0.08,
        risk_level="low",
        human_validated=False,
        detections_count=12,
        audit_events_count=4,
        has_anonymized_text=True,
    )

    assert score.trust_score >= 80
    assert score.ai_readiness_score >= 80
    assert score.ai_readiness_level == "ready_for_ai"
    assert "pipeline_completed" in score.controls
    assert "audit_trail_present" in score.controls


def test_high_risk_without_validation_caps_ai_readiness():
    score = compute_document_trust_score(
        status="ready",
        risk_score=82,
        risk_level="high",
        human_validated=False,
        detections_count=9,
        audit_events_count=3,
        has_anonymized_text=True,
    )

    assert score.ai_readiness_score <= 55
    assert score.ai_readiness_level == "human_review_required"
    assert "human_validation_required" in score.controls


def test_processing_document_is_not_ready_for_ai():
    score = compute_document_trust_score(
        status="extracting",
        risk_score=0,
        risk_level="low",
        human_validated=False,
        detections_count=0,
        audit_events_count=1,
        has_anonymized_text=False,
    )

    assert score.ai_readiness_score <= 35
    assert score.ai_readiness_level == "not_ready"


def test_portfolio_trust_score_is_null_without_documents():
    score = compute_portfolio_trust_score(
        total_documents=0,
        gdpr_score=None,
        ready_documents=0,
        failed_documents=0,
        high_or_critical_risks=0,
    )

    assert score["score"] is None
    assert score["grade"] is None


def test_portfolio_trust_score_penalizes_failures_and_elevated_risk():
    clean = compute_portfolio_trust_score(
        total_documents=10,
        gdpr_score=90,
        ready_documents=10,
        failed_documents=0,
        high_or_critical_risks=0,
    )
    risky = compute_portfolio_trust_score(
        total_documents=10,
        gdpr_score=90,
        ready_documents=6,
        failed_documents=2,
        high_or_critical_risks=3,
    )

    assert clean["score"] > risky["score"]
    assert risky["recommendations"]
