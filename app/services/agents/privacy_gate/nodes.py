"""Nodes for the deterministic DPO Privacy Gate agent."""

from __future__ import annotations

from app.services.agents.privacy_gate.state import (
    EXTERNAL_ACTIONS,
    PROCESSING_STATUSES,
    READY_STATUSES,
    SENSITIVE_ENTITY_TYPES,
    SUPPORTED_ACTIONS,
    PrivacyGateState,
)


def _risk_score_percent(score: float | int | None) -> float:
    value = float(score or 0.0)
    if 0 <= value <= 1:
        value *= 100
    return max(0.0, min(100.0, value))


async def normalize_node(state: PrivacyGateState) -> PrivacyGateState:
    action = str(state.get("requested_action") or "external_ai").strip().lower()
    if action not in SUPPORTED_ACTIONS:
        action = "external_ai"

    status = str(state.get("status") or "").strip().lower()
    risk_level = str(state.get("risk_level") or "low").strip().lower()
    if risk_level not in {"low", "medium", "high", "critical"}:
        risk_level = "low"

    entity_types = sorted(
        {
            str(entity_type or "").strip().upper()
            for entity_type in (state.get("entity_types") or [])
            if str(entity_type or "").strip()
        }
    )

    return {
        **state,
        "normalized_action": action,
        "status": status,
        "risk_level": risk_level,
        "risk_score": _risk_score_percent(state.get("risk_score")),
        "entity_types": entity_types,
        "current_step": "normalize",
        "steps_completed": state.get("steps_completed", []) + ["normalize"],
    }


async def evaluate_node(state: PrivacyGateState) -> PrivacyGateState:
    flags: list[str] = []
    status = state.get("status") or ""
    action = state.get("normalized_action") or "external_ai"
    risk_level = state.get("risk_level") or "low"
    entity_types = set(state.get("entity_types") or [])

    if status in {"failed", "deleted"}:
        flags.append("document_unusable")
    if status not in READY_STATUSES:
        flags.append("document_not_ready")
    if status in PROCESSING_STATUSES:
        flags.append("processing_pending")
    if action in EXTERNAL_ACTIONS and not state.get("anonymized_text_available"):
        flags.append("missing_anonymized_text")
    if risk_level == "critical":
        flags.append("critical_reidentification_risk")
    if risk_level == "high" and not state.get("human_validated"):
        flags.append("high_risk_without_human_validation")
    if risk_level == "medium" and action in {"external_ai", "share", "demo"}:
        flags.append("medium_risk_external_use")
    if entity_types.intersection(SENSITIVE_ENTITY_TYPES):
        flags.append("sensitive_entities_detected")
    if (
        action in {"external_ai", "share", "demo"}
        and entity_types.intersection({"IBAN", "BANK", "CARTE_BANCAIRE", "NSS", "SOCIAL_SECURITY"})
        and not state.get("human_validated")
    ):
        flags.append("direct_identifier_external_use")
    if int(state.get("audit_events_count") or 0) <= 0:
        flags.append("missing_audit_trace")

    return {
        **state,
        "flags": sorted(set(flags)),
        "current_step": "evaluate",
        "steps_completed": state.get("steps_completed", []) + ["evaluate"],
    }


async def decide_node(state: PrivacyGateState) -> PrivacyGateState:
    flags = set(state.get("flags") or [])
    action = state.get("normalized_action") or "external_ai"
    risk_level = state.get("risk_level") or "low"

    decision = "allow"
    reasons: list[str] = []
    required_actions: list[str] = []
    warnings: list[str] = []

    if "document_unusable" in flags:
        decision = "block"
        reasons.append("Le document est en échec ou supprimé.")
        required_actions.append("Ré-uploader ou restaurer un document valide.")
    elif "document_not_ready" in flags or "missing_anonymized_text" in flags:
        decision = "block"
        reasons.append("Le document n'est pas prêt pour cet usage.")
        required_actions.append(
            "Finaliser l'OCR et l'anonymisation avant toute utilisation IA/export."
        )
    elif "critical_reidentification_risk" in flags and action in EXTERNAL_ACTIONS:
        decision = "block"
        reasons.append("Risque de réidentification critique pour un usage externe.")
        required_actions.append("Renforcer l'anonymisation puis recalculer le score de risque.")
    elif "high_risk_without_human_validation" in flags and action in EXTERNAL_ACTIONS:
        decision = "human_review_required"
        reasons.append("Risque élevé sans validation humaine DPO.")
        required_actions.append(
            "Valider manuellement les mappings avant export, partage ou IA externe."
        )
    elif "direct_identifier_external_use" in flags:
        decision = "human_review_required"
        reasons.append("Des identifiants directs sensibles restent dans le périmètre d'analyse.")
        required_actions.append("Contrôler les entités bancaires/sociales avant usage externe.")
    elif "medium_risk_external_use" in flags:
        decision = "human_review_required"
        reasons.append("Risque moyen pour un usage externe.")
        required_actions.append("Effectuer une revue humaine légère avant diffusion externe.")

    if decision == "allow":
        if risk_level in {"medium", "high"}:
            warnings.append("Usage autorisé avec conservation de la preuve DPO et journal d'audit.")
        if "sensitive_entities_detected" in flags:
            warnings.append(
                "Des entités sensibles ont été détectées ; conserver les sorties anonymisées."
            )

    if "missing_audit_trace" in flags:
        warnings.append("Aucune trace d'audit n'a été trouvée pour ce document.")

    return {
        **state,
        "decision": decision,
        "reasons": reasons,
        "required_actions": required_actions,
        "warnings": warnings,
        "current_step": "decide",
        "steps_completed": state.get("steps_completed", []) + ["decide"],
    }


async def explain_node(state: PrivacyGateState) -> PrivacyGateState:
    action = state.get("normalized_action") or "external_ai"
    controls = [
        "Texte anonymisé uniquement",
        "Journal d'audit conservé",
        "Score de réidentification consultable",
    ]
    if state.get("human_validated"):
        controls.append("Validation humaine enregistrée")
    if action in EXTERNAL_ACTIONS:
        controls.append("Sortie limitée aux données minimisées")

    evidence = {
        "document_id": state.get("document_id"),
        "status": state.get("status"),
        "requested_action": action,
        "risk_score": round(float(state.get("risk_score") or 0.0), 1),
        "risk_level": state.get("risk_level"),
        "human_validated": bool(state.get("human_validated")),
        "anonymized_text_available": bool(state.get("anonymized_text_available")),
        "detections_count": int(state.get("detections_count") or 0),
        "entity_types": state.get("entity_types") or [],
        "audit_events_count": int(state.get("audit_events_count") or 0),
        "flags": state.get("flags") or [],
    }

    return {
        **state,
        "allowed_controls": controls,
        "evidence": evidence,
        "current_step": "explain",
        "steps_completed": state.get("steps_completed", []) + ["explain"],
    }
