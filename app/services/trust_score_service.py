"""Trust Score / AI Readiness scoring.

Scores are intentionally deterministic and explainable. They are not legal
certification; they summarize whether a document is safe enough for AI use or
external sharing based on pipeline state, residual re-identification risk,
human validation, and audit trail coverage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_READY_STATUSES = {"ready", "anonymized"}
_PROCESSING_STATUSES = {"processing", "extracting", "extracted", "anonymizing"}


@dataclass(frozen=True)
class DocumentTrustScore:
    trust_score: int
    ai_readiness_score: int
    ai_readiness_level: str
    grade: str
    controls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trust_score": self.trust_score,
            "ai_readiness_score": self.ai_readiness_score,
            "ai_readiness_level": self.ai_readiness_level,
            "grade": self.grade,
            "controls": self.controls,
        }


def normalize_risk_percent(score: float | int | None) -> float:
    """Normalize risk scores stored as either 0-1 or 0-100."""
    if score is None:
        return 0.0
    value = float(score)
    return max(0.0, min(100.0, value * 100 if 0 <= value <= 1 else value))


def _grade(score: int) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 50:
        return "C"
    return "D"


def _level(ai_score: int, status: str, risk_level: str, human_validated: bool) -> str:
    if status not in _READY_STATUSES:
        return "not_ready"
    if risk_level == "critical":
        return "blocked"
    if risk_level == "high" and not human_validated:
        return "human_review_required"
    if ai_score >= 80:
        return "ready_for_ai"
    if ai_score >= 60:
        return "internal_review"
    return "needs_review"


def compute_document_trust_score(
    *,
    status: str,
    risk_score: float | int | None,
    risk_level: str | None,
    human_validated: bool,
    detections_count: int,
    audit_events_count: int,
    has_anonymized_text: bool,
) -> DocumentTrustScore:
    """Compute document-level Trust Score and AI Readiness Score."""
    normalized_status = str(status or "").lower()
    normalized_level = str(risk_level or "low").lower()
    risk_pct = normalize_risk_percent(risk_score)

    controls: list[str] = []

    if normalized_status in _READY_STATUSES and has_anonymized_text:
        pipeline_points = 25
        controls.append("pipeline_completed")
    elif normalized_status in _PROCESSING_STATUSES:
        pipeline_points = 12
        controls.append("pipeline_in_progress")
    elif normalized_status == "failed":
        pipeline_points = 0
        controls.append("pipeline_failed")
    else:
        pipeline_points = 5
        controls.append("pipeline_not_started")

    privacy_points = max(0, round(40 - (risk_pct * 0.40)))
    if normalized_level in {"low", "medium"}:
        controls.append("residual_risk_scored")
    if normalized_level in {"high", "critical"}:
        controls.append("elevated_risk_detected")

    validation_points = 15 if human_validated else 0
    if human_validated:
        controls.append("human_validation_logged")
    elif normalized_level in {"high", "critical"}:
        controls.append("human_validation_required")

    audit_points = min(12, audit_events_count * 3)
    if audit_events_count:
        controls.append("audit_trail_present")

    detection_points = 8 if detections_count > 0 else 0
    if detections_count > 0:
        controls.append("entities_detected_and_masked")
    elif normalized_status in _READY_STATUSES:
        controls.append("no_entities_detected_review_recommended")

    trust_score = min(
        100,
        max(
            0,
            pipeline_points
            + privacy_points
            + validation_points
            + audit_points
            + detection_points,
        ),
    )

    ai_readiness = trust_score
    if not has_anonymized_text or normalized_status not in _READY_STATUSES:
        ai_readiness = min(ai_readiness, 35)
    if normalized_level == "critical":
        ai_readiness = min(ai_readiness, 20)
    elif normalized_level == "high" and not human_validated:
        ai_readiness = min(ai_readiness, 55)
    elif normalized_level == "medium" and not human_validated:
        ai_readiness = min(ai_readiness, 75)

    ai_readiness = int(max(0, min(100, ai_readiness)))
    trust_score = int(max(0, min(100, trust_score)))

    return DocumentTrustScore(
        trust_score=trust_score,
        ai_readiness_score=ai_readiness,
        ai_readiness_level=_level(
            ai_readiness,
            normalized_status,
            normalized_level,
            human_validated,
        ),
        grade=_grade(trust_score),
        controls=controls,
    )


def compute_portfolio_trust_score(
    *,
    total_documents: int,
    gdpr_score: int | None,
    ready_documents: int,
    failed_documents: int,
    high_or_critical_risks: int,
) -> dict[str, Any]:
    """Compute a lightweight portfolio-level trust score for dashboards."""
    if total_documents <= 0:
        return {
            "score": None,
            "grade": None,
            "status": "Score non disponible",
            "recommendations": ["Ajoutez un document pour calculer le Trust Score."],
        }

    readiness_rate = ready_documents / total_documents
    failure_rate = failed_documents / total_documents
    elevated_risk_rate = high_or_critical_risks / total_documents
    base = gdpr_score if gdpr_score is not None else 50

    score = round(
        base * 0.55
        + readiness_rate * 30
        + max(0.0, 1 - failure_rate) * 10
        + max(0.0, 1 - elevated_risk_rate) * 5
    )
    score = int(max(0, min(100, score)))

    recommendations: list[str] = []
    if failure_rate > 0:
        recommendations.append("Corriger les documents en echec de pipeline.")
    if elevated_risk_rate > 0:
        recommendations.append("Valider manuellement les documents a risque eleve.")
    if readiness_rate < 0.8:
        recommendations.append("Finaliser OCR et anonymisation sur les documents en attente.")
    if not recommendations:
        recommendations.append(
            "Portefeuille documentaire pret pour une demonstration IA controlee."
        )

    status = "Investor-ready" if score >= 80 else "A consolider" if score >= 60 else "A risque"
    return {
        "score": score,
        "grade": _grade(score),
        "status": status,
        "recommendations": recommendations,
    }
