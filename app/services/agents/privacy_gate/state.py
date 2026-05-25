"""State contract for the DPO Privacy Gate agent."""

from typing import Literal, TypedDict

Decision = Literal["allow", "human_review_required", "block"]

SUPPORTED_ACTIONS = {
    "external_ai",
    "export",
    "share",
    "demo",
    "internal_review",
}

READY_STATUSES = {"ready", "anonymized"}
PROCESSING_STATUSES = {"uploaded", "processing", "extracting", "extracted", "anonymizing"}
SENSITIVE_ENTITY_TYPES = {
    "IBAN",
    "BIC",
    "BANK",
    "CARTE_BANCAIRE",
    "NSS",
    "SOCIAL_SECURITY",
    "SIREN",
    "SIRET",
    "COMPANY_ID",
    "EMAIL",
    "PHONE",
    "TELEPHONE",
}
EXTERNAL_ACTIONS = {"external_ai", "export", "share", "demo"}


class PrivacyGateState(TypedDict, total=False):
    document_id: str
    requested_action: str
    normalized_action: str
    status: str
    risk_score: float
    risk_level: str
    human_validated: bool
    autopilot_validated: bool
    anonymized_text_available: bool
    detections_count: int
    entity_types: list[str]
    audit_events_count: int
    flags: list[str]
    decision: Decision
    reasons: list[str]
    required_actions: list[str]
    allowed_controls: list[str]
    warnings: list[str]
    evidence: dict[str, object]
    current_step: str
    steps_completed: list[str]


def initial_privacy_gate_state(
    *,
    document_id: str,
    requested_action: str,
    status: str,
    risk_score: float | int | None = None,
    risk_level: str | None = None,
    human_validated: bool = False,
    autopilot_validated: bool = False,
    anonymized_text_available: bool = False,
    detections_count: int = 0,
    entity_types: list[str] | None = None,
    audit_events_count: int = 0,
) -> PrivacyGateState:
    return {
        "document_id": document_id,
        "requested_action": requested_action,
        "normalized_action": "",
        "status": status,
        "risk_score": float(risk_score or 0.0),
        "risk_level": str(risk_level or "low"),
        "human_validated": bool(human_validated),
        "autopilot_validated": bool(autopilot_validated),
        "anonymized_text_available": bool(anonymized_text_available),
        "detections_count": int(detections_count or 0),
        "entity_types": entity_types or [],
        "audit_events_count": int(audit_events_count or 0),
        "flags": [],
        "decision": "block",
        "reasons": [],
        "required_actions": [],
        "allowed_controls": [],
        "warnings": [],
        "evidence": {},
        "current_step": "init",
        "steps_completed": [],
    }

