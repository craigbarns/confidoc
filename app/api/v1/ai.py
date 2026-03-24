"""ConfiDoc Backend — AI endpoints (anonymized-only)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import http_400, http_404
from app.models.document import Document
from app.services.anonymization_service import anonymize_text, classify_document_type
from app.services.ollama_service import generate_summary_with_ollama, generate_audit_with_ollama
from app.services.structured_dataset_service import build_structured_dataset
from app.api.v1.documents import _get_best_text_for_reporting

router = APIRouter()


def _is_safe_placeholder_text(v: str) -> bool:
    up = (v or "").strip().upper()
    # Accept explicit placeholders only, avoid leaking raw text values to LLM payload.
    return bool(up) and ("_" in up) and any(
        up.startswith(prefix)
        for prefix in ("SOCIETE_", "ASSOCIE_", "ADRESSE_", "BIEN_", "PERSONNE_", "VILLE_", "COMPTE_")
    )


def _sanitize_fields_for_ai(fields: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (fields or {}).items():
        if not isinstance(v, dict):
            continue
        value = v.get("value")
        safe_value: Any = value
        if isinstance(value, str) and not _is_safe_placeholder_text(value):
            safe_value = None
        out[k] = {
            "value": safe_value,
            "confidence": v.get("confidence"),
            "review_required": v.get("review_required"),
        }
    return out


def _build_fallback_summary(ai_payload: dict[str, Any]) -> dict[str, Any]:
    quality = ai_payload.get("quality", {}) or {}
    fields = ai_payload.get("fields", {}) or {}
    tables_counts = ai_payload.get("tables_counts", {}) or {}
    doc_type = str(ai_payload.get("doc_type") or "unknown_other")

    if doc_type == "fiscal_2072":
        critical_keys = [
            "denomination_sci",
            "date_cloture_exercice",
            "nombre_associes",
            "revenus_bruts",
            "interets_emprunts",
            "revenu_net_foncier",
        ]
        questions = [
            "Pouvez-vous vérifier les champs critiques manquants dans la 2072 ?",
            "Les montants revenus/charges sont-ils cohérents avec les annexes ?",
        ]
    elif doc_type == "bilan":
        critical_keys = [
            "total_actif",
            "total_passif",
            "capitaux_propres",
            "resultat_exercice",
            "dettes_financieres",
            "dettes_fournisseurs",
        ]
        questions = [
            "Pouvez-vous confirmer les totaux actif/passif sur le bilan source ?",
            "Les dettes financières et fournisseurs sont-elles correctement reprises ?",
        ]
    else:
        critical_keys = []
        questions = [
            "Pouvez-vous valider les champs clés extraits sur le document source ?",
            "Des incohérences métier nécessitent-elles une correction manuelle ?",
        ]

    critical_missing = [k for k in critical_keys if (fields.get(k, {}) or {}).get("value") in (None, "", [])]
    points_cles: list[str] = []
    if doc_type == "fiscal_2072":
        if (fields.get("denomination_sci", {}) or {}).get("value"):
            points_cles.append(f"Société: {(fields['denomination_sci'] or {}).get('value')}.")
        if (fields.get("revenu_net_foncier", {}) or {}).get("value") is not None:
            points_cles.append(f"Revenu net foncier: {(fields['revenu_net_foncier'] or {}).get('value')}.")
        points_cles.append(
            f"Annexes détectées: immeubles={tables_counts.get('immeubles', 0)}, "
            f"associés={tables_counts.get('associes_revenus_fonciers', 0)}."
        )
    elif doc_type == "bilan":
        actif = (fields.get("total_actif", {}) or {}).get("value")
        passif = (fields.get("total_passif", {}) or {}).get("value")
        if actif is not None or passif is not None:
            points_cles.append(f"Totaux bilan: actif={actif}, passif={passif}.")
    else:
        points_cles.append("Aucun point clé métier stable n'a pu être déterminé automatiquement.")

    anomalies: list[str] = []
    if quality.get("needs_review"):
        anomalies.append("Le dossier nécessite une revue humaine avant usage IA.")
    if critical_missing:
        anomalies.append(f"Champs critiques manquants: {', '.join(critical_missing)}.")
    confidence = 0.35 if quality.get("needs_review") else 0.7

    return {
        "resume_executif": "Synthèse générée en mode de secours (LLM vide ou non exploitable).",
        "points_cles": points_cles,
        "anomalies_ou_alertes": anomalies,
        "questions_de_revue": questions,
        "confiance_globale": confidence,
    }


@router.post(
    "/audit/{document_id}",
    response_class=JSONResponse,
    status_code=status.HTTP_200_OK,
    summary="Agent IA de contrôle de cohérence & conformité",
)
async def ai_audit(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
    doc_type: str = Query(default="auto"),
) -> JSONResponse:
    try:
        document_uuid = uuid.UUID(document_id)
    except ValueError as exc:
        raise http_404("Document introuvable") from exc

    result = await db.execute(
        select(Document).where(
            Document.id == document_uuid,
            Document.uploaded_by_user_id == current_user.id,
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise http_404("Document introuvable")

    original_text = await _get_best_text_for_reporting(db, document)
    if not original_text:
        raise http_400("Aucune donnée textuelle disponible pour l'analyse IA")

    effective_type = classify_document_type(original_text, document.original_filename)
    anonymized_text, detections = anonymize_text(
        original_text,
        profile="dataset_accounting",
        document_type=effective_type,
    )

    structured = build_structured_dataset(
        anonymized_text=anonymized_text,
        original_filename=document.original_filename,
        requested_doc_type=doc_type,
        extraction_text=original_text,
    )

    ai_payload = {
        "document_id": str(document.id),
        "doc_type": structured.get("doc_type"),
        "fields": _sanitize_fields_for_ai(structured.get("fields", {})),
        "anonymized_excerpt": anonymized_text[:5000],
    }

    try:
        # Appelle le nouvel agent restrictif
        llm = await generate_audit_with_ollama(ai_payload, doc_type=structured.get("doc_type", "generic"))
    except Exception as exc:
        raise http_400(f"Erreur IA locale (AuditAgent): {exc}") from exc

    parsed = llm.get("validated")
    if not isinstance(parsed, dict):
        err_hint = (llm.get("last_validation_error") or "").strip()
        expl = "L'IA locale n'a pas fourni un JSON conforme au schéma après plusieurs tentatives."
        if err_hint:
            expl = f"{expl} Détail: {err_hint[:800]}"
        parsed = {
            "global_status": "inconclusive",
            "checks": [
                {
                    "code": "CHK_FORMAT",
                    "description": "Validation Pydantic de la sortie JSON (AuditResult)",
                    "status": "failed",
                    "explanation": expl,
                }
            ],
        }

    return JSONResponse(
        {
            "document_id": str(document.id),
            "audit_results": parsed,
            "provider": "ollama (local)",
            "model": llm.get("model", "unknown"),
            "ollama_validation": {
                "ok": bool(llm.get("validation_ok")),
                "attempts": llm.get("validation_attempts"),
            },
        }
    )


@router.post(
    "/summary/{document_id}",
    response_class=JSONResponse,
    status_code=status.HTTP_200_OK,
    summary="Générer une synthèse IA depuis données anonymisées (Ollama)",
)
async def ai_summary(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
    doc_type: str = Query(default="auto"),
) -> JSONResponse:
    try:
        document_uuid = uuid.UUID(document_id)
    except ValueError as exc:
        raise http_404("Document introuvable") from exc

    result = await db.execute(
        select(Document).where(
            Document.id == document_uuid,
            Document.uploaded_by_user_id == current_user.id,
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise http_404("Document introuvable")

    original_text = await _get_best_text_for_reporting(db, document)
    if not original_text:
        raise http_400("Aucune donnée textuelle disponible pour l'analyse IA")

    effective_type = classify_document_type(original_text, document.original_filename)
    anonymized_text, detections = anonymize_text(
        original_text,
        profile="dataset_accounting",
        document_type=effective_type,
    )

    structured = build_structured_dataset(
        anonymized_text=anonymized_text,
        original_filename=document.original_filename,
        requested_doc_type=doc_type,
        extraction_text=original_text,
    )
    quality = structured.get("quality") or {}
    if not bool(quality.get("ready_for_ai")):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "Synthèse IA indisponible: document non prêt pour l'IA (ready_for_ai=false).",
                "summary_available": False,
                "detected_doc_type": structured.get("detected_doc_type"),
                "doc_type": structured.get("doc_type"),
                "quality_snapshot": {
                    "needs_review": bool(quality.get("needs_review", True)),
                    "ready_for_ai": bool(quality.get("ready_for_ai", False)),
                    "coverage_ratio": quality.get("coverage_ratio"),
                    "critical_missing_fields": quality.get("critical_missing_fields", []),
                    "quality_flags": quality.get("quality_flags", []),
                },
            },
        )

    ai_payload = {
        "document_id": str(document.id),
        "doc_type": structured.get("doc_type"),
        "quality": structured.get("quality", {}),
        "fields": _sanitize_fields_for_ai(structured.get("fields", {})),
        "tables_counts": {
            "immeubles": len((structured.get("tables") or {}).get("immeubles", []) or []),
            "associes_revenus_fonciers": len((structured.get("tables") or {}).get("associes_revenus_fonciers", []) or []),
        },
        "anonymized_excerpt": anonymized_text[:4000],
        "detections_count": len(detections),
    }

    try:
        llm = await generate_summary_with_ollama(ai_payload)
    except Exception as exc:
        raise http_400(f"Erreur IA locale (Ollama): {exc}") from exc

    parsed = llm.get("validated")
    used_fallback = not isinstance(parsed, dict)
    if used_fallback:
        parsed = _build_fallback_summary(ai_payload)
    summary_json_text = json.dumps(parsed, ensure_ascii=False)

    return JSONResponse(
        {
            "document_id": str(document.id),
            "provider": "ollama",
            "model": llm.get("model"),
            "ollama_validation": {
                "ok": bool(llm.get("validation_ok")),
                "attempts": llm.get("validation_attempts"),
            },
            "quality_snapshot": {
                "needs_review": bool((structured.get("quality") or {}).get("needs_review", True)),
                "ready_for_ai": bool((structured.get("quality") or {}).get("ready_for_ai", False)),
                "coverage_ratio": (structured.get("quality") or {}).get("coverage_ratio"),
            },
            "payload_policy": {
                "raw_text_sent": False,
                "anonymized_only": True,
                "non_placeholder_text_fields_redacted": True,
            },
            "summary_json_text": summary_json_text,
            "summary_source": "fallback_local" if used_fallback else "ollama",
        }
    )

