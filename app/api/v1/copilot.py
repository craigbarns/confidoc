"""ConfiDoc Copilot endpoints."""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.api.v1._privacy_gate import privacy_gate_public_summary, require_privacy_gate
from app.config import get_settings
from app.core.exceptions import http_400, http_404
from app.models.document import Document
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.schemas.copilot import (
    DEFAULT_COMPARE_QUESTION,
    CopilotAskRequest,
    CopilotAskResponse,
    CopilotCompareRequest,
)
from app.services.copilot_service import (
    build_dual_corpus,
    confidence_bucket,
    generate_copilot_answer,
    retrieve_citations,
)

router = APIRouter()


def _copilot_privacy_action() -> str:
    settings = get_settings()
    external_mistral_possible = bool(
        not getattr(settings, "SENSITIVE_CLIENT_MODE", False)
        and getattr(settings, "MISTRAL_ENABLED", False)
        and getattr(settings, "MISTRAL_API_KEY", "")
    )
    return "external_ai" if external_mistral_possible else "internal_review"


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


@router.post(
    "/{document_id}/ask",
    response_model=CopilotAskResponse,
    status_code=status.HTTP_200_OK,
    summary="Question Copilot avec citations et confiance",
)
async def copilot_ask(
    document_id: str,
    body: CopilotAskRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> CopilotAskResponse:
    t0 = time.perf_counter()
    document = await _get_document_or_404(db, document_id, current_user.id)
    anonymized_text = await _get_anonymized_text(db, document)
    if not anonymized_text:
        raise http_400("Aucun texte anonymisé disponible. Lancez d'abord l'anonymisation.")

    privacy_gate = await require_privacy_gate(
        db,
        document,
        _copilot_privacy_action(),
        anonymized_text=anonymized_text,
    )
    top_k = 3 if body.mode != "quick" else 2
    citations = retrieve_citations(body.question, anonymized_text, top_k=top_k)
    answer = await generate_copilot_answer(body.question, citations)
    confidence = confidence_bucket(citations)
    warnings: list[str] = [
        *privacy_gate_public_summary(privacy_gate).get("warnings", []),
    ]
    if confidence != "high":
        warnings.append("Réponse à valider humainement avant décision.")
    latency_ms = int((time.perf_counter() - t0) * 1000)
    return CopilotAskResponse(
        answer=answer,
        citations=citations,
        confidence=confidence,
        warnings=warnings,
        latency_ms=latency_ms,
    )


@router.post(
    "/{document_id}/compare",
    response_model=CopilotAskResponse,
    status_code=status.HTTP_200_OK,
    summary="Comparer deux documents anonymisés (ex. N vs N-1)",
)
async def copilot_compare(
    document_id: str,
    body: CopilotCompareRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> CopilotAskResponse:
    t0 = time.perf_counter()
    if str(body.other_document_id) == document_id:
        raise http_400("Choisissez un document différent du document courant.")

    doc_a = await _get_document_or_404(db, document_id, current_user.id)
    doc_b = await _get_document_or_404(db, str(body.other_document_id), current_user.id)

    text_a = await _get_anonymized_text(db, doc_a)
    text_b = await _get_anonymized_text(db, doc_b)
    if not text_a or not text_b:
        raise http_400(
            "Les deux documents doivent avoir un texte anonymisé. "
            "Lancez l'anonymisation sur chacun."
        )

    privacy_gate_a = await require_privacy_gate(
        db,
        doc_a,
        _copilot_privacy_action(),
        anonymized_text=text_a,
    )
    privacy_gate_b = await require_privacy_gate(
        db,
        doc_b,
        _copilot_privacy_action(),
        anonymized_text=text_b,
    )
    question = (body.question or "").strip() or DEFAULT_COMPARE_QUESTION
    combined = build_dual_corpus(text_a, text_b)
    citations = retrieve_citations(question, combined, top_k=4)
    answer = await generate_copilot_answer(question, citations)
    confidence = confidence_bucket(citations)
    warnings: list[str] = [
        *privacy_gate_public_summary(privacy_gate_a).get("warnings", []),
        *privacy_gate_public_summary(privacy_gate_b).get("warnings", []),
        "Comparaison indicative — validation humaine obligatoire avant toute décision.",
    ]
    if confidence != "high":
        warnings.append("Couverture des sources limitée sur un ou deux documents.")
    # Same client tag hint (optional)
    tag_a = (doc_a.tags or [])[:1]
    tag_b = (doc_b.tags or [])[:1]
    if tag_a and tag_b and tag_a[0] != tag_b[0]:
        warnings.append(
            "Les tags client diffèrent entre les deux documents — vérifiez qu'il s'agit "
            "bien du même dossier."
        )

    latency_ms = int((time.perf_counter() - t0) * 1000)
    return CopilotAskResponse(
        answer=answer,
        citations=citations,
        confidence=confidence,
        warnings=warnings,
        latency_ms=latency_ms,
    )
