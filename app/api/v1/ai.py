"""ConfiDoc Backend — AI endpoints (anonymized-only)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import http_400, http_404
from app.models.document import Document
from app.models.llm_request import LlmRequest
from app.models.llm_suggestion import LlmSuggestion
from app.services.anonymization_service import anonymize_text, classify_document_type
from app.services.ollama_service import generate_summary_with_ollama, generate_audit_with_ollama
from app.services.kimi_service import generate_summary_with_kimi, generate_audit_with_kimi, stream_kimi_response
from app.services.structured_dataset_service import build_structured_dataset
from app.api.v1.documents import _get_best_text_for_reporting
from app.config import get_settings

router = APIRouter()


def _select_llm_provider(requested: str) -> str:
    """Select best available LLM provider based on configuration."""
    _settings = get_settings()
    kimi_available = getattr(_settings, "KIMI_ENABLED", False) and getattr(_settings, "KIMI_API_KEY", "")
    ollama_available = getattr(_settings, "OLLAMA_ENABLED", True)
    
    if requested == "kimi" and kimi_available:
        return "kimi"
    if requested == "ollama" and ollama_available:
        return "ollama"
    if requested == "auto":
        # Prioritize Kimi if available (better quality), fallback to Ollama
        if kimi_available:
            return "kimi"
        if ollama_available:
            return "ollama"
    # Fallback: try Kimi first, then Ollama
    if kimi_available:
        return "kimi"
    if ollama_available:
        return "ollama"
    return "kimi"  # Default to kimi even if not configured (will fail gracefully)


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


def _apply_quality_facts_guardrails(summary: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    """Force output consistency: backend quality facts remain authoritative."""
    if not isinstance(summary, dict):
        return summary
    out = dict(summary)
    critical_missing = quality.get("critical_missing_fields", []) or []
    ready_for_ai = bool(quality.get("ready_for_ai", False))
    ready_for_ai_core = bool(quality.get("ready_for_ai_core", False))

    # Remove contradictions when backend reports no critical missing fields.
    if not critical_missing:
        anomalies = out.get("anomalies_ou_alertes")
        if isinstance(anomalies, list):
            filtered: list[str] = []
            for item in anomalies:
                text = str(item or "")
                low = text.lower()
                if "champ" in low and "manquan" in low and "crit" in low:
                    continue
                filtered.append(text)
            out["anomalies_ou_alertes"] = filtered

    # Optional factual line to pin the backend quality status.
    points = out.get("points_cles")
    if isinstance(points, list):
        points.insert(
            0,
            (
                "Statut qualité backend: "
                f"ready_for_ai={str(ready_for_ai).lower()}, "
                f"ready_for_ai_core={str(ready_for_ai_core).lower()}, "
                f"critical_missing_fields={len(critical_missing)}."
            ),
        )
        out["points_cles"] = points
    return out


def _humanize_quality_flags(quality_flags: list[str]) -> list[str]:
    mapping = {
        "critical_fields_missing": "Des champs critiques manquent; une vérification humaine est nécessaire.",
        "low_field_coverage": "La couverture d'extraction est faible; prudence sur l'interprétation.",
        "manual_review_recommended": "Une revue humaine est recommandée avant exploitation complète.",
        "numeric_consistency_low": "Certains montants semblent insuffisamment cohérents pour une exploitation fiable.",
        "bilan_balance_mismatch": "Le bilan ne semble pas équilibré; vérifier actif/passif.",
        "bilan_balance_minor_gap": "Le bilan présente un léger écart; une vérification est conseillée.",
    }
    out: list[str] = []
    for flag in quality_flags or []:
        out.append(mapping.get(flag, f"Indicateur qualité: {flag}."))
    return out


def _generate_quality_warning(quality: dict[str, Any]) -> str | None:
    """Generate a user-friendly warning when suspicious fields are present."""
    suspicious = quality.get("suspicious_fields", []) or []
    if not suspicious:
        return None
    
    count = len(suspicious)
    if count == 1:
        return f"Vérification recommandée sur 1 champ ({suspicious[0]})."
    elif count <= 3:
        return f"Vérification recommandée sur {count} champs ({', '.join(suspicious)})."
    else:
        return f"Certains champs sont calculés ou issus d'un fallback et doivent être vérifiés ({count} champs)."


def _add_suspicious_fields_to_payload(payload: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    """Add suspicious_fields info to AI payload so LLM knows which fields are uncertain."""
    out = dict(payload)
    suspicious = quality.get("suspicious_fields", []) or []
    if suspicious:
        out["uncertain_fields"] = suspicious
        out["data_quality_notes"] = (
            "Attention: Les champs suivants sont calculés ou issus de fallbacks "
            f"et doivent être interprétés avec prudence: {', '.join(suspicious)}. "
            "Privilégier les questions sur les champs directement lus dans le document."
        )
    return out


def _apply_audit_quality_guardrails(audit: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    """Normalize audit output so backend quality facts remain authoritative."""
    if not isinstance(audit, dict):
        return audit
    out = dict(audit)
    critical_missing = quality.get("critical_missing_fields", []) or []
    ready_for_ai = bool(quality.get("ready_for_ai", False))
    ready_for_ai_core = bool(quality.get("ready_for_ai_core", False))
    needs_review = bool(quality.get("needs_review", True))
    quality_flags = quality.get("quality_flags", []) or []

    checks = out.get("checks")
    if not isinstance(checks, list):
        checks = []
    normalized_checks: list[dict[str, Any]] = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        exp = str(check.get("explanation") or "")
        low = exp.lower()
        if not critical_missing and ("champ" in low and "manquan" in low and "crit" in low):
            # Drop contradictory check explanation against backend facts.
            continue
        normalized_checks.append(check)

    # Insert authoritative backend-facts check first.
    normalized_checks.insert(
        0,
        {
            "code": "CHK_BACKEND_FACTS",
            "description": "Statut qualité backend (source de vérité)",
            "status": "passed",
            "explanation": (
                f"ready_for_ai={str(ready_for_ai).lower()}, "
                f"ready_for_ai_core={str(ready_for_ai_core).lower()}, "
                f"needs_review={str(needs_review).lower()}, "
                f"critical_missing_fields={len(critical_missing)}, "
                f"quality_flags={quality_flags}."
            ),
        },
    )
    out["checks"] = normalized_checks
    return out


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
    llm_provider: str = Query(default="auto"),
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

    # Merge accepted LLM suggestions (RGPD: replacement only) - same as document_dataset_summary
    llm_suggestions_result = await db.execute(
        select(LlmSuggestion)
        .join(LlmRequest, LlmRequest.id == LlmSuggestion.llm_request_id)
        .where(
            LlmRequest.document_id == document.id,
            LlmRequest.human_status == "accepted",
        )
    )
    llm_suggestions = list(llm_suggestions_result.scalars().all())
    merged = list(detections)
    for s in llm_suggestions:
        cand = {
            "entity_type": s.entity_type,
            "start_index": int(s.start_index),
            "end_index": int(s.end_index),
            "replacement": s.replacement_token,
        }
        overlap = any(
            not (cand["end_index"] <= ex["start_index"] or cand["start_index"] >= ex["end_index"])
            for ex in merged
        )
        if not overlap:
            merged.append(cand)

    # Apply replacements so quality gate matches the final dataset text.
    dataset_text = original_text
    for match in sorted(merged, key=lambda m: m["start_index"], reverse=True):
        dataset_text = (
            dataset_text[: match["start_index"]]
            + match["replacement"]
            + dataset_text[match["end_index"] :]
        )

    structured = build_structured_dataset(
        anonymized_text=dataset_text,
        original_filename=document.original_filename,
        requested_doc_type=doc_type,
        extraction_text=dataset_text,  # RGPD: use anonymized text, not original
    )

    ai_payload = {
        "document_id": str(document.id),
        "doc_type": structured.get("doc_type"),
        "quality": structured.get("quality", {}),
        "fields": _sanitize_fields_for_ai(structured.get("fields", {})),
        "anonymized_excerpt": anonymized_text[:5000],
    }

    # Select best available provider
    selected_provider = _select_llm_provider(llm_provider)
    
    try:
        if selected_provider == "kimi":
            llm = await generate_audit_with_kimi(
                ai_payload, doc_type=structured.get("doc_type", "generic")
            )
            provider_name = "kimi"
        else:
            llm = await generate_audit_with_ollama(
                ai_payload, doc_type=structured.get("doc_type", "generic")
            )
            provider_name = "ollama (local)"
    except Exception as exc:
        raise http_400(f"Erreur IA ({selected_provider}) AuditAgent: {exc}") from exc

    parsed = llm.get("validated")
    quality = structured.get("quality") or {}
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
    parsed = _apply_audit_quality_guardrails(parsed, quality)

    # Get suspicious fields for audit response
    suspicious = quality.get("suspicious_fields", []) or []
    
    return JSONResponse(
        {
            "document_id": str(document.id),
            "audit_results": parsed,
            "provider": provider_name,
            "model": llm.get("model", "unknown"),
            "ollama_validation": {
                "ok": bool(llm.get("validation_ok")),
                "attempts": llm.get("validation_attempts"),
            },
            "quality_snapshot": {
                "ready_for_ai_core": bool(quality.get("ready_for_ai_core", False)),
                "suspicious_fields": suspicious,
                "warning": _generate_quality_warning(quality),
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
    llm_provider: str = Query(default="auto"),
    kimi_mode: str = Query(default="summary"),
    question: str = Query(default=""),
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
    ready_for_ai = bool(quality.get("ready_for_ai"))
    ready_for_ai_core = bool(quality.get("ready_for_ai_core"))
    if (not ready_for_ai) and (not ready_for_ai_core):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "Synthèse IA indisponible: document non prêt pour l'IA (ready_for_ai_core=false).",
                "summary_available": False,
                "detected_doc_type": structured.get("detected_doc_type"),
                "doc_type": structured.get("doc_type"),
                "quality_snapshot": {
                    "needs_review": bool(quality.get("needs_review", True)),
                    "ready_for_ai": bool(quality.get("ready_for_ai", False)),
                    "ready_for_ai_core": bool(quality.get("ready_for_ai_core", False)),
                    "coverage_ratio": quality.get("coverage_ratio"),
                    "critical_missing_fields": quality.get("critical_missing_fields", []),
                    "quality_flags": quality.get("quality_flags", []),
                    "suspicious_fields": quality.get("suspicious_fields", []),
                    "warning": _generate_quality_warning(quality),
                },
            },
        )

    ai_payload_base = {
        "document_id": str(document.id),
        "doc_type": structured.get("doc_type"),
        "quality": structured.get("quality", {}),
        "quality_flags_humanized": _humanize_quality_flags((structured.get("quality") or {}).get("quality_flags", [])),
        "fields": _sanitize_fields_for_ai(structured.get("fields", {})),
        "tables_counts": {
            "immeubles": len((structured.get("tables") or {}).get("immeubles", []) or []),
            "associes_revenus_fonciers": len((structured.get("tables") or {}).get("associes_revenus_fonciers", []) or []),
        },
        "anonymized_excerpt": anonymized_text[:4000],
        "detections_count": len(detections),
    }
    if question.strip():
        ai_payload_base["user_question"] = question.strip()
    
    # Add suspicious fields info so IA knows which fields are uncertain
    ai_payload = _add_suspicious_fields_to_payload(ai_payload_base, quality)

    prudent_mode = ready_for_ai_core and (not ready_for_ai)
    if kimi_mode not in {"summary", "review", "draft", "question"}:
        raise http_400("Paramètre kimi_mode invalide. Valeurs: summary|review|draft|question.")
    if kimi_mode == "question" and not question.strip():
        raise http_400("Paramètre question requis quand kimi_mode=question.")
    # Select best available provider
    selected_provider = _select_llm_provider(llm_provider)
    
    try:
        if selected_provider == "kimi":
            llm = await generate_summary_with_kimi(
                ai_payload,
                prudent_mode=prudent_mode,
                mode=kimi_mode,
            )
            provider_name = "kimi"
        else:
            llm = await generate_summary_with_ollama(ai_payload)
            provider_name = "ollama"
    except Exception as exc:
        raise http_400(f"Erreur IA ({selected_provider}): {exc}") from exc

    parsed = llm.get("validated")
    used_fallback = not isinstance(parsed, dict)
    if used_fallback:
        parsed = _build_fallback_summary(ai_payload)
    parsed = _apply_quality_facts_guardrails(parsed, quality)
    summary_json_text = json.dumps(parsed, ensure_ascii=False)

    return JSONResponse(
        {
            "document_id": str(document.id),
            "provider": provider_name,
            "model": llm.get("model"),
            "ollama_validation": {
                "ok": bool(llm.get("validation_ok")),
                "attempts": llm.get("validation_attempts"),
            },
            "quality_snapshot": {
                "needs_review": bool((structured.get("quality") or {}).get("needs_review", True)),
                "ready_for_ai": bool((structured.get("quality") or {}).get("ready_for_ai", False)),
                "ready_for_ai_core": bool((structured.get("quality") or {}).get("ready_for_ai_core", False)),
                "coverage_ratio": (structured.get("quality") or {}).get("coverage_ratio"),
                "suspicious_fields": (structured.get("quality") or {}).get("suspicious_fields", []),
                "warning": _generate_quality_warning(structured.get("quality") or {}),
            },
            "payload_policy": {
                "raw_text_sent": False,
                "anonymized_only": True,
                "non_placeholder_text_fields_redacted": True,
            },
            "summary_json_text": summary_json_text,
            "summary_source": "fallback_local" if used_fallback else provider_name,
            "prudent_mode": prudent_mode,
            "kimi_mode": kimi_mode if llm_provider == "kimi" else None,
        }
    )


@router.post(
    "/stream/{document_id}",
    summary="Synthèse IA en streaming (SSE)",
)
async def ai_stream(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
    doc_type: str = Query(default="auto"),
    question: str = Query(default=""),
) -> StreamingResponse:
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
    anonymized_text, _ = anonymize_text(
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
    ready_for_ai = bool(quality.get("ready_for_ai"))
    ready_for_ai_core = bool(quality.get("ready_for_ai_core"))

    if not ready_for_ai and not ready_for_ai_core:
        async def _blocked():
            yield "data: " + json.dumps({"error": "Document non prêt pour l'IA."}) + "\n\n"
        return StreamingResponse(_blocked(), media_type="text/event-stream")

    fields_summary = _sanitize_fields_for_ai(structured.get("fields", {}))
    prompt_question = question.strip() or "Fais une synthèse comptable courte et actionnable."
    user_content = (
        f"Document type: {structured.get('doc_type', 'inconnu')}\n"
        f"Qualité: ready_for_ai={ready_for_ai}, ready_for_ai_core={ready_for_ai_core}\n"
        f"Champs extraits: {json.dumps(fields_summary, ensure_ascii=False)[:3000]}\n"
        f"Extrait anonymisé: {anonymized_text[:2000]}\n\n"
        f"Question: {prompt_question}"
    )

    async def _event_stream():
        try:
            async for chunk in stream_kimi_response(user_content, temperature=0.3):
                payload = json.dumps({"chunk": chunk}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            err = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"data: {err}\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

