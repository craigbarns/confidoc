"""ConfiDoc Backend — AI endpoints (sur texte anonymisé uniquement)."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import http_400, http_404
from app.core.logging import get_logger
from app.models.document import Document
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.services.ollama_service import generate_summary_with_ollama
from app.services.mistral_service import generate_summary_with_mistral, stream_mistral_response
from app.services.kimi_service import generate_summary_with_kimi, stream_kimi_response
from app.services.llm_extraction_service import extract_with_llm
from app.config import get_settings

router = APIRouter()
logger = get_logger(__name__)


def _select_llm_provider(requested: str) -> str:
    """Sélectionne le meilleur provider disponible. Priorité: Mistral → Kimi → Ollama."""
    s = get_settings()
    mistral_ok = bool(getattr(s, "MISTRAL_ENABLED", False) and getattr(s, "MISTRAL_API_KEY", ""))
    kimi_ok = bool(getattr(s, "KIMI_ENABLED", False) and getattr(s, "KIMI_API_KEY", ""))
    ollama_ok = bool(getattr(s, "OLLAMA_ENABLED", True))

    if requested == "mistral" and mistral_ok:
        return "mistral"
    if requested == "kimi" and kimi_ok:
        return "kimi"
    if requested == "ollama" and ollama_ok:
        return "ollama"
    if mistral_ok:
        return "mistral"
    if kimi_ok:
        return "kimi"
    if ollama_ok:
        return "ollama"
    return "mistral"


async def _get_document_or_404(db: DbSession, document_id: str, user_id: uuid.UUID) -> Document:
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError as exc:
        raise http_404("Document introuvable") from exc

    result = await db.execute(
        select(Document).where(
            Document.id == doc_uuid,
            Document.uploaded_by_user_id == user_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise http_404("Document introuvable")
    return doc


async def _get_anonymized_text(db: DbSession, document: Document) -> str:
    """Récupère le texte anonymisé (final > preview)."""
    for version_type in (
        DocumentVersionType.FINAL_ANONYMIZED,
        DocumentVersionType.PREVIEW_ANONYMIZED,
    ):
        result = await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.version_type == version_type,
            )
        )
        version = result.scalar_one_or_none()
        if version and version.content_text:
            return version.content_text
    return ""


# ──────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/providers",
    response_class=JSONResponse,
    status_code=status.HTTP_200_OK,
    summary="Statut des providers LLM configurés",
)
async def ai_providers(current_user: CurrentUser) -> JSONResponse:
    s = get_settings()
    selected = _select_llm_provider("auto")
    return JSONResponse({
        "selected_provider": selected,
        "mistral": {
            "enabled": bool(getattr(s, "MISTRAL_ENABLED", False)),
            "key_set": bool(getattr(s, "MISTRAL_API_KEY", "")),
            "model": getattr(s, "MISTRAL_MODEL", ""),
        },
        "kimi": {
            "enabled": bool(getattr(s, "KIMI_ENABLED", False)),
            "key_set": bool(getattr(s, "KIMI_API_KEY", "")),
        },
        "ollama": {"enabled": bool(getattr(s, "OLLAMA_ENABLED", True))},
    })


@router.post(
    "/summary/{document_id}",
    response_class=JSONResponse,
    status_code=status.HTTP_200_OK,
    summary="Synthèse / Q&A sur le document anonymisé",
)
async def ai_summary(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
    question: str = Query(default=""),
    llm_provider: str = Query(default="auto"),
    mode: str = Query(default="summary"),
) -> JSONResponse:
    document = await _get_document_or_404(db, document_id, current_user.id)
    anonymized_text = await _get_anonymized_text(db, document)

    if not anonymized_text:
        raise http_400("Aucun texte anonymisé disponible. Lancez d'abord l'anonymisation.")

    if mode not in {"summary", "review", "draft", "question"}:
        raise http_400("Paramètre mode invalide. Valeurs: summary|review|draft|question.")
    if mode == "question" and not question.strip():
        raise http_400("Paramètre question requis quand mode=question.")

    ai_payload = {
        "document_id": str(document.id),
        "anonymized_text": anonymized_text[:8000],
        "user_question": question.strip() or None,
    }

    selected_provider = _select_llm_provider(llm_provider)

    try:
        if selected_provider == "mistral":
            llm = await generate_summary_with_mistral(ai_payload, prudent_mode=False, mode=mode)
            provider_name = "mistral"
        elif selected_provider == "kimi":
            llm = await generate_summary_with_kimi(ai_payload, prudent_mode=False, mode=mode)
            provider_name = "kimi"
        else:
            llm = await generate_summary_with_ollama(ai_payload)
            provider_name = "ollama"
    except Exception as exc:
        raise http_400(f"Erreur IA ({selected_provider}): {exc}") from exc

    parsed = llm.get("validated") or {}
    summary_text = json.dumps(parsed, ensure_ascii=False) if parsed else llm.get("raw_text", "")

    return JSONResponse({
        "document_id": str(document.id),
        "provider": provider_name,
        "model": llm.get("model"),
        "mode": mode,
        "summary": summary_text,
        "payload_policy": {
            "raw_text_sent": False,
            "anonymized_only": True,
        },
    })


@router.post(
    "/stream/{document_id}",
    response_class=StreamingResponse,
    summary="Réponse IA en streaming (SSE) sur le document anonymisé",
)
async def ai_stream(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
    question: str = Query(default=""),
    llm_provider: str = Query(default="auto"),
):
    document = await _get_document_or_404(db, document_id, current_user.id)
    anonymized_text = await _get_anonymized_text(db, document)

    if not anonymized_text:
        async def _blocked():
            yield "data: " + json.dumps({"error": "Aucun texte anonymisé. Lancez d'abord l'anonymisation."}) + "\n\n"
        return StreamingResponse(_blocked(), media_type="text/event-stream")

    prompt_question = question.strip() or "Fais une synthèse courte et claire de ce document."
    user_content = (
        f"Voici le texte anonymisé d'un document confidentiel:\n\n"
        f"{anonymized_text[:6000]}\n\n"
        f"Question: {prompt_question}"
    )

    stream_provider = _select_llm_provider(llm_provider)

    async def _event_stream():
        try:
            if stream_provider == "mistral":
                gen = stream_mistral_response(user_content, temperature=0.3)
            else:
                gen = stream_kimi_response(user_content, temperature=0.3)
            async for chunk in gen:
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


@router.post(
    "/extract/{document_id}",
    response_class=JSONResponse,
    status_code=status.HTTP_200_OK,
    summary="Extraction structurée 100% LLM (Mistral Large)",
)
async def ai_extract(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> JSONResponse:
    """Extrait les données structurées (type, montants, totaux) via Mistral Large.
    
    Pas de regex, pas de règles métier — uniquement un LLM sur le texte anonymisé.
    """
    document = await _get_document_or_404(db, document_id, current_user.id)
    anonymized_text = await _get_anonymized_text(db, document)

    if not anonymized_text:
        raise http_400("Aucun texte anonymisé disponible. Lancez d'abord l'anonymisation.")

    extraction = await extract_with_llm(anonymized_text)

    return JSONResponse({
        "document_id": str(document.id),
        "extraction": extraction,
        "payload_policy": {
            "method": "llm:mistral-large",
            "anonymized_only": True,
        },
    })
