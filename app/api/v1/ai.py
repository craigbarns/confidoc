"""ConfiDoc Backend — AI endpoints (anonymized-only)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import http_400, http_404
from app.models.document import Document
from app.services.anonymization_service import anonymize_text, classify_document_type
from app.services.ollama_service import generate_summary_with_ollama
from app.services.structured_dataset_service import build_structured_dataset
from app.api.v1.documents import _get_original_text

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

    original_text = await _get_original_text(db, document)
    if not original_text:
        raise http_400("Texte source introuvable pour ce document")

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

    return JSONResponse(
        {
            "document_id": str(document.id),
            "provider": "ollama",
            "model": llm.get("model"),
            "payload_policy": {
                "raw_text_sent": False,
                "anonymized_only": True,
                "non_placeholder_text_fields_redacted": True,
            },
            "summary_json_text": llm.get("raw_response", ""),
        }
    )

