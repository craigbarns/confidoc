"""Product-facing document decision labels for RGPD/AI readiness."""

from __future__ import annotations

from typing import Any

_READY_STATUSES = {"ready", "anonymized"}
_PROCESSING_STATUSES = {"uploaded", "processing", "extracting", "extracted", "anonymizing"}

_ENTITY_REASONS = {
    "IBAN": "IBAN détecté",
    "CARTE_BANCAIRE": "Donnée bancaire détectée",
    "EMAIL": "Email détecté",
    "PHONE": "Téléphone détecté",
    "TELEPHONE": "Téléphone détecté",
    "PHONE_FR": "Téléphone détecté",
    "PERSONNE": "Nom ou prénom détecté",
    "PERSON": "Nom ou prénom détecté",
    "ADRESSE": "Adresse détectée",
    "ADDRESS": "Adresse détectée",
    "VILLE": "Ville ou code postal détecté",
    "SIREN": "SIREN détecté",
    "SIRET": "SIRET détecté",
    "NSS": "Numéro de sécurité sociale détecté",
    "SOCIAL_SECURITY": "Numéro de sécurité sociale détecté",
    "DATE_NAISSANCE": "Date de naissance détectée",
}


def normalize_risk_score(score: float | int | None) -> int | None:
    """Normalize fractional or percentage scores to a 0-100 integer."""
    if score is None:
        return None
    value = float(score)
    if 0 <= value <= 1:
        value *= 100
    return int(max(0, min(100, round(value))))


def _unique_reasons(entity_types: list[str] | tuple[str, ...] | set[str]) -> list[str]:
    reasons: list[str] = []
    for raw in entity_types:
        key = str(raw or "").upper()
        label = _ENTITY_REASONS.get(key)
        if label and label not in reasons:
            reasons.append(label)
    return reasons


def build_document_decision(
    *,
    status: str,
    risk_score: float | int | None,
    risk_level: str | None,
    human_validated: bool,
    entity_types: list[str] | tuple[str, ...] | set[str],
    detections_count: int = 0,
    audit_events_count: int = 0,
) -> dict[str, Any]:
    """Return a clear, user-facing decision object for the document page."""
    normalized_status = str(status or "").lower()
    normalized_level = str(risk_level or "low").lower()
    score = normalize_risk_score(risk_score)
    reasons = _unique_reasons(entity_types)

    if detections_count > 20 and "Trop de quasi-identifiants" not in reasons:
        reasons.append("Trop de quasi-identifiants")
    if not reasons and detections_count > 0:
        reasons.append(f"{detections_count} entité(s) masquée(s)")
    if audit_events_count <= 0:
        reasons.append("Historique d'audit incomplet")

    if normalized_status == "failed":
        decision = {
            "code": "processing_error",
            "label": "Erreur de traitement",
            "severity": "error",
            "decision": "Le document n'est pas utilisable pour le moment",
            "explanation": (
                "Le traitement n'a pas pu être terminé. Relancez ou contactez "
                "l'administrateur."
            ),
            "recommended_action": "Relancer le traitement",
            "actions": ["Relancer anonymisation", "Voir audit trail"],
        }
    elif normalized_status not in _READY_STATUSES:
        decision = {
            "code": "processing",
            "label": "Traitement en cours",
            "severity": "neutral",
            "decision": "Attendez la fin du traitement",
            "explanation": (
                "Le document est en cours d'OCR, d'anonymisation ou de scoring."
            ),
            "recommended_action": "Patienter ou relancer le traitement",
            "actions": ["Voir audit trail"],
        }
    elif normalized_level == "critical" or (score is not None and score >= 80):
        decision = {
            "code": "blocked",
            "label": "Export bloqué",
            "severity": "danger",
            "decision": "Export bloqué tant que les risques ne sont pas corrigés",
            "explanation": (
                "Des données sensibles critiques semblent encore présentes. Le "
                "document doit être corrigé ou validé par un administrateur."
            ),
            "recommended_action": "Corriger les risques",
            "actions": [
                "Corriger les risques",
                "Voir les données détectées",
                "Télécharger rapport DPO",
            ],
        }
    elif normalized_level in {"medium", "high"} or (score is not None and score >= 40):
        action = "Valider manuellement" if not human_validated else "Télécharger le rapport DPO"
        decision = {
            "code": "review_recommended",
            "label": "Revue recommandée",
            "severity": "warning",
            "decision": "Vous devez vérifier avant export",
            "explanation": (
                "Certaines données sensibles ou quasi-identifiants peuvent encore "
                "permettre une réidentification. Vérifiez le document avant export."
            ),
            "recommended_action": action,
            "actions": [
                "Corriger l'anonymisation",
                "Valider manuellement",
                "Voir pourquoi",
                "Relancer anonymisation",
            ],
        }
    elif human_validated:
        decision = {
            "code": "human_validated",
            "label": "Validé manuellement",
            "severity": "success",
            "decision": "Vous pouvez exporter",
            "explanation": (
                "Le document anonymisé a été relu et validé par un utilisateur "
                "autorisé."
            ),
            "recommended_action": "Analyser avec IA ou exporter le rapport",
            "actions": ["Analyser avec IA", "Exporter rapport", "Voir audit trail"],
        }
    else:
        decision = {
            "code": "ready_for_ai",
            "label": "Prêt pour IA",
            "severity": "success",
            "decision": "Vous pouvez exporter",
            "explanation": (
                "Le document anonymisé ne présente pas de risque évident. Il peut "
                "être utilisé pour une analyse IA ou un export."
            ),
            "recommended_action": "Analyser avec IA",
            "actions": ["Analyser avec IA", "Exporter rapport", "Voir audit trail"],
        }

    if not reasons:
        reasons = ["Aucun risque évident détecté"]

    return {
        **decision,
        "risk_score": score,
        "risk_level": normalized_level,
        "reasons": reasons[:6],
        "human_validated": human_validated,
        "decision_notice": (
            "Ce score aide à prioriser les risques. Il ne remplace pas une "
            "validation juridique ou DPO."
        ),
    }


def build_timeline_steps(
    *,
    status: str,
    extraction_done: bool,
    anonymization_done: bool,
    risk_score_done: bool,
    human_validated: bool,
    export_allowed: bool,
) -> list[dict[str, str]]:
    """Build a concise seven-step document timeline for the UI."""
    normalized_status = str(status or "").lower()
    failed = normalized_status == "failed"

    def state(done: bool, active: bool = False) -> str:
        if failed and active:
            return "error"
        if done:
            return "done"
        if active:
            return "current"
        return "pending"

    return [
        {"key": "upload", "label": "Document importé", "state": "done"},
        {
            "key": "ocr",
            "label": "OCR terminé",
            "state": state(extraction_done, normalized_status in _PROCESSING_STATUSES),
        },
        {
            "key": "detect",
            "label": "Entités détectées",
            "state": state(anonymization_done, normalized_status == "anonymizing"),
        },
        {
            "key": "anonymize",
            "label": "Anonymisation générée",
            "state": state(anonymization_done, normalized_status == "anonymizing"),
        },
        {
            "key": "score",
            "label": "Score calculé",
            "state": state(risk_score_done, anonymization_done and not risk_score_done),
        },
        {
            "key": "review",
            "label": "Revue humaine",
            "state": state(human_validated, risk_score_done and not human_validated),
        },
        {
            "key": "export",
            "label": "Export ou analyse IA",
            "state": state(export_allowed, risk_score_done and not export_allowed),
        },
    ]
