"""ConfiDoc Backend — Documents endpoints (v2)."""

import uuid
import re
import hashlib
from io import BytesIO

from typing import Literal

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from sqlalchemy import delete, desc, func, select, update

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import http_400, http_404
from app.core.logging import get_logger
from app.models.document import Document, DocumentStatus
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.models.entity_detection import EntityDetection
from app.models.llm_request import LlmRequest
from app.models.llm_suggestion import LlmSuggestion
from app.schemas.document import (
    AnonymizeResponse,
    DetectionResponse,
    DocumentPreviewResponse,
    DocumentResponse,
)
from app.services.document_processing_service import build_anonymization_preview
from app.services.anonymization_service import (
    anonymize_text,
    classify_document_type,
    extract_text_from_file,
)
from app.services.pdf_redaction_service import redact_pdf_bytes
from app.services.storage_service import delete_bytes, read_bytes

router = APIRouter()
logger = get_logger(__name__)

def _sha256_text(text: str | None) -> str | None:
    """Compute sha256 of a text (used for audit/integrity only; never expose raw text)."""
    if text is None:
        return None
    if not isinstance(text, str):
        text = str(text)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ──────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────

async def _get_user_document_or_404(
    db: DbSession, document_id: str, user_id: uuid.UUID
) -> Document:
    try:
        document_uuid = uuid.UUID(document_id)
    except ValueError as exc:
        raise http_404("Document introuvable") from exc

    result = await db.execute(
        select(Document).where(
            Document.id == document_uuid,
            Document.uploaded_by_user_id == user_id,
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise http_404("Document introuvable")
    return document


def _read_file_or_404(document: Document) -> bytes:
    """Read file from storage, with fallback to raw_content in DB."""
    # Try external storage first
    try:
        return read_bytes(document.storage_backend, document.storage_key)
    except (FileNotFoundError, Exception) as exc:
        logger.warning("storage_read_fallback", doc_id=str(document.id), error=str(exc))

    # Fallback: raw bytes stored in PostgreSQL
    if document.raw_content:
        logger.info("using_db_raw_content", doc_id=str(document.id))
        return document.raw_content

    raise http_404(
        "Fichier source introuvable. Le fichier a été supprimé du stockage "
        "et aucune copie n'est disponible en base. Ré-uploadez le document."
    )


async def _get_or_create_final_version(
    db: DbSession, document: Document
) -> DocumentVersion:
    """Get the final anonymized version, auto-creating it from preview if needed."""
    # Try FINAL first
    result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.FINAL_ANONYMIZED,
        )
    )
    final = result.scalar_one_or_none()
    if final:
        return final

    # Fallback: auto-validate from preview
    preview_result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.PREVIEW_ANONYMIZED,
        )
    )
    preview = preview_result.scalar_one_or_none()
    if not preview:
        raise http_404(
            "Aucune version anonymisée disponible. Lancez d'abord l'anonymisation."
        )

    # Auto-create final from preview
    final = DocumentVersion(
        document_id=document.id,
        version_type=DocumentVersionType.FINAL_ANONYMIZED,
        content_text=preview.content_text,
    )
    db.add(final)
    await db.flush()
    logger.info("auto_validated_from_preview", doc_id=str(document.id))
    return final


async def _get_original_text(
    db: DbSession, document: Document
) -> str:
    """Get original text from DB version, or re-extract from file."""
    result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.ORIGINAL_TEXT,
        )
    )
    version = result.scalar_one_or_none()
    if version and version.content_text:
        return version.content_text

    # Re-extract from file
    file_content = _read_file_or_404(document)
    return extract_text_from_file(file_content, document.extension) or ""


# ──────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[DocumentResponse],
    status_code=status.HTTP_200_OK,
    summary="Lister les documents de l'utilisateur",
)
async def list_documents(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Document]:
    result = await db.execute(
        select(Document)
        .where(Document.uploaded_by_user_id == current_user.id)
        .order_by(desc(Document.created_at))
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Détail d'un document",
)
async def get_document(
    document_id: str, current_user: CurrentUser, db: DbSession
) -> Document:
    return await _get_user_document_or_404(db, document_id, current_user.id)


@router.post(
    "/{document_id}/anonymize",
    response_model=AnonymizeResponse,
    status_code=status.HTTP_200_OK,
    summary="Anonymiser un document (preview)",
)
async def anonymize_document(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
    profile: Literal["moderate", "strict", "dataset_strict", "dataset_accounting"] = Query(
        default="dataset_accounting"
    ),
    document_type: str = Query(default="auto"),
) -> AnonymizeResponse:
    document = await _get_user_document_or_404(db, document_id, current_user.id)
    file_content = _read_file_or_404(document)

    preview_text, detections, effective_type = await build_anonymization_preview(
        db=db,
        document=document,
        file_content=file_content,
        profile=profile,
        document_type=document_type,
    )
    await db.commit()

    return AnonymizeResponse(
        document_id=document.id,
        status=document.status.value,
        detections_count=len(detections),
        detections=[DetectionResponse(**item) for item in detections],
        preview_text=f"[type={effective_type}|profile={profile}]\n\n{preview_text}",
    )


@router.get(
    "/{document_id}/preview",
    response_model=DocumentPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Prévisualiser l'anonymisation",
)
async def preview_document(
    document_id: str, current_user: CurrentUser, db: DbSession
) -> DocumentPreviewResponse:
    document = await _get_user_document_or_404(db, document_id, current_user.id)

    preview_result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.PREVIEW_ANONYMIZED,
        )
    )
    preview_version = preview_result.scalar_one_or_none()
    if not preview_version:
        raise http_404("Aucune preview disponible. Lancez /anonymize d'abord.")

    count_result = await db.execute(
        select(func.count()).select_from(EntityDetection).where(
            EntityDetection.document_id == document.id
        )
    )
    detections_count = count_result.scalar() or 0

    return DocumentPreviewResponse(
        document_id=document.id,
        status=document.status.value,
        preview_text=preview_version.content_text,
        detections_count=detections_count,
    )


@router.get(
    "/{document_id}/original",
    response_class=PlainTextResponse,
    status_code=status.HTTP_200_OK,
    summary="Retourne le texte original (avec garde-fou RGPD)",
)
async def original_text_document(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
    allow_original: bool = Query(default=False, description="Doit etre a true pour autoriser l'affichage du texte original."),
    max_chars: int = Query(default=8000, ge=100, le=50000, description="Limite de caracteres pour eviter les charges trop lourdes."),
) -> PlainTextResponse:
    """Expose le texte original uniquement si allow_original=true.

    Utilite pour la vue 'avant/apres' en console UI (beta/demo). Le texte original contient des donnees sensibles.
    """
    if not allow_original:
        raise http_400("Acces au texte original desactive. Utilisez allow_original=true.")

    document = await _get_user_document_or_404(db, document_id, current_user.id)
    original_text = await _get_original_text(db, document)
    sliced = original_text[:max_chars] if original_text else ""
    return PlainTextResponse(sliced)


@router.post(
    "/{document_id}/validate",
    status_code=status.HTTP_200_OK,
    summary="Valider la preview et figer la version finale",
)
async def validate_document(
    document_id: str, current_user: CurrentUser, db: DbSession
) -> dict:
    document = await _get_user_document_or_404(db, document_id, current_user.id)

    preview_result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.PREVIEW_ANONYMIZED,
        )
    )
    preview_version = preview_result.scalar_one_or_none()
    if not preview_version:
        raise http_404("Aucune preview disponible")

    # Remove old final version
    await db.execute(
        delete(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.FINAL_ANONYMIZED,
        )
    )
    db.add(
        DocumentVersion(
            document_id=document.id,
            version_type=DocumentVersionType.FINAL_ANONYMIZED,
            content_text=preview_version.content_text,
        )
    )

    # Mark LLM suggestions as accepted
    await db.execute(
        update(LlmRequest)
        .where(
            LlmRequest.document_id == document.id,
            LlmRequest.preview_version_id == preview_version.id,
        )
        .values(human_status="accepted")
    )
    await db.commit()

    logger.info("document_validated", doc_id=str(document.id))
    return {"status": "validated", "document_id": str(document.id)}


@router.get(
    "/{document_id}/export",
    response_class=PlainTextResponse,
    status_code=status.HTTP_200_OK,
    summary="Exporter la version anonymisée (texte)",
)
async def export_document(
    document_id: str, current_user: CurrentUser, db: DbSession
) -> PlainTextResponse:
    document = await _get_user_document_or_404(db, document_id, current_user.id)
    # Auto-validates from preview if no explicit validation
    final = await _get_or_create_final_version(db, document)
    await db.commit()
    return PlainTextResponse(final.content_text)


@router.get(
    "/{document_id}/export-pdf",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
    summary="Exporter un PDF visuellement redacted",
)
async def export_redacted_pdf(
    document_id: str, current_user: CurrentUser, db: DbSession
) -> StreamingResponse:
    document = await _get_user_document_or_404(db, document_id, current_user.id)

    if document.extension.lower() != "pdf":
        raise http_400("Export PDF redacted disponible uniquement pour les fichiers PDF")

    # Get detections
    detections_result = await db.execute(
        select(EntityDetection).where(EntityDetection.document_id == document.id)
    )
    detections = list(detections_result.scalars().all())
    if not detections:
        raise http_404("Aucune détection disponible. Lancez /anonymize d'abord.")

    # Read original PDF
    original_bytes = _read_file_or_404(document)

    # Collect sensitive values and apply redaction
    sensitive_values = [item.value_excerpt for item in detections if item.value_excerpt]
    try:
        redacted_bytes = redact_pdf_bytes(original_bytes, sensitive_values)
    except Exception as exc:
        logger.error("pdf_redaction_failed", doc_id=str(document.id), error=str(exc))
        raise http_400(
            "Impossible de générer le PDF redacté. Le fichier PDF est peut-être corrompu."
        )

    download_name = f"redacted_{document.original_filename}"
    headers = {"Content-Disposition": f'attachment; filename="{download_name}"'}
    return StreamingResponse(
        BytesIO(redacted_bytes), media_type="application/pdf", headers=headers
    )


@router.get(
    "/{document_id}/export-dataset",
    response_class=JSONResponse,
    status_code=status.HTTP_200_OK,
    summary="Exporter un enregistrement dataset (texte anonymisé + spans)",
)
async def export_dataset(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> JSONResponse:
    """Export RGPD-friendly pour dataset:
    - applies 'dataset_accounting' profile (keeps amounts)
    - never sends original values (no value_excerpt)
    - returns spans consistent with the anonymized text.
    """
    document = await _get_user_document_or_404(db, document_id, current_user.id)

    # Get original text (from DB, or re-extract)
    original_text = await _get_original_text(db, document)
    if not original_text:
        raise http_404("Texte original introuvable. Ré-uploadez et anonymisez le document.")

    effective_type = classify_document_type(original_text, document.original_filename)
    _, detections = anonymize_text(
        original_text, profile="dataset_accounting", document_type=effective_type,
    )

    # Merge accepted LLM suggestions
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
            "value_excerpt": "",
        }
        if not any(
            not (cand["end_index"] <= ex["start_index"] or cand["start_index"] >= ex["end_index"])
            for ex in merged
        ):
            merged.append(cand)

    # Apply all replacements
    dataset_text = original_text
    for match in sorted(merged, key=lambda m: m["start_index"], reverse=True):
        dataset_text = (
            dataset_text[: match["start_index"]]
            + match["replacement"]
            + dataset_text[match["end_index"] :]
        )

    entities = [
        {
            "entity_type": item["entity_type"],
            "start": item["start_index"],
            "end": item["end_index"],
            "replacement_token": item["replacement"],
        }
        for item in merged
    ]

    # ── Quality gate ──
    quality_flags: list[str] = []
    critical_patterns: dict[str, str] = {
        "emails_found": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "iban_found": r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b",
        "siret_found": r"\b\d{3}[ .-]?\d{3}[ .-]?\d{3}[ .-]?\d{5}\b",
        "siren_found": r"\b\d{3}[ .-]?\d{3}[ .-]?\d{3}\b",
        "uppercase_person_leftovers": r"\b[A-ZÀ-ÖØ-Ý]{2,}(?:\s+[A-ZÀ-ÖØ-Ý]{2,}){1,4}\b",
    }
    for flag, pat in critical_patterns.items():
        if re.search(pat, dataset_text):
            quality_flags.append(flag)

    needs_review = len(quality_flags) > 0 or len(entities) == 0

    # ── Accounting records extraction ──
    accounting_records = _extract_accounting_records(dataset_text)

    payload = {
        "document_id": str(document.id),
        "doc_type": effective_type,
        "profile": "dataset_accounting",
        "anonymized_text": dataset_text,
        "entities": entities,
        "quality": {
            "detections_count": len(entities),
            "needs_review": needs_review,
            "quality_flags": quality_flags,
        },
        "accounting_records": accounting_records,
    }
    return JSONResponse(payload)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un document (et son fichier)",
)
async def delete_document(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    document = await _get_user_document_or_404(db, document_id, current_user.id)

    # 1) Delete file from storage (best effort)
    try:
        delete_bytes(document.storage_backend, document.storage_key)
    except Exception as exc:
        logger.warning("storage_delete_failed", doc_id=str(document.id), error=str(exc))

    # 2) Delete from database (cascades to versions/detections)
    await db.execute(delete(Document).where(Document.id == document.id))
    await db.commit()
    logger.info("document_deleted", doc_id=str(document.id))


@router.get(
    "/{document_id}/proof",
    response_class=JSONResponse,
    status_code=status.HTTP_200_OK,
    summary="Preuve d'integrite RGPD (hashes + compteurs)",
)
async def document_proof(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> JSONResponse:
    document = await _get_user_document_or_404(db, document_id, current_user.id)

    preview_version_obj = (
        await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.version_type == DocumentVersionType.PREVIEW_ANONYMIZED,
            )
        )
    ).scalar_one_or_none()
    final_version_obj = (
        await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.version_type == DocumentVersionType.FINAL_ANONYMIZED,
            )
        )
    ).scalar_one_or_none()

    detections_n = (
        await db.execute(
            select(func.count()).select_from(EntityDetection).where(
                EntityDetection.document_id == document.id
            )
        )
    ).scalar() or 0

    llm_req_n = (
        await db.execute(
            select(func.count()).select_from(LlmRequest).where(
                LlmRequest.document_id == document.id
            )
        )
    ).scalar() or 0

    entity_type_rows = (
        await db.execute(
            select(EntityDetection.entity_type, func.count()).where(
                EntityDetection.document_id == document.id
            ).group_by(EntityDetection.entity_type)
        )
    ).all()
    detections_entity_types_count = {
        str(entity_type): int(cnt) for entity_type, cnt in entity_type_rows
    }

    return JSONResponse(
        {
            "document_id": str(document.id),
            "document_sha256": document.sha256,
            "preview_version_present": preview_version_obj is not None,
            "preview_version_sha256": _sha256_text(
                preview_version_obj.content_text if preview_version_obj else None
            ),
            "final_version_present": final_version_obj is not None,
            "final_version_sha256": _sha256_text(
                final_version_obj.content_text if final_version_obj else None
            ),
            "detections_count": int(detections_n),
            "llm_requests_count": int(llm_req_n),
            "detections_entity_types_count": detections_entity_types_count,
        }
    )


@router.get(
    "/{document_id}/deletion-preview",
    response_class=JSONResponse,
    status_code=status.HTTP_200_OK,
    summary="Apercu de l'effacement RGPD (compteurs, sans donnees)",
)
async def document_deletion_preview(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> JSONResponse:
    document = await _get_user_document_or_404(db, document_id, current_user.id)

    versions_n = (
        await db.execute(
            select(func.count()).select_from(DocumentVersion).where(
                DocumentVersion.document_id == document.id
            )
        )
    ).scalar() or 0

    detections_n = (
        await db.execute(
            select(func.count()).select_from(EntityDetection).where(
                EntityDetection.document_id == document.id
            )
        )
    ).scalar() or 0

    llm_req_n = (
        await db.execute(
            select(func.count()).select_from(LlmRequest).where(
                LlmRequest.document_id == document.id
            )
        )
    ).scalar() or 0

    llm_suggestions_n = (
        await db.execute(
            select(func.count()).select_from(LlmSuggestion).join(
                LlmRequest,
                LlmRequest.id == LlmSuggestion.llm_request_id,
            ).where(LlmRequest.document_id == document.id)
        )
    ).scalar() or 0

    return JSONResponse(
        {
            "document_id": str(document.id),
            # On ne renvoie pas storage_key (chemin interne) : RGPD-friendly (meta seulement).
            "storage": {"backend": document.storage_backend},
            "will_delete": {
                "document": True,
                "document_versions_count": int(versions_n),
                "entity_detections_count": int(detections_n),
                "llm_requests_count": int(llm_req_n),
                "llm_suggestions_count": int(llm_suggestions_n),
            },
        }
    )


@router.get(
    "/{document_id}/audit-export",
    response_class=JSONResponse,
    status_code=status.HTTP_200_OK,
    summary="Export audit RGPD (hashes + resume, sans donnees brutes)",
)
async def document_audit_export(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> JSONResponse:
    document = await _get_user_document_or_404(db, document_id, current_user.id)

    original_version_obj = (
        await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.version_type == DocumentVersionType.ORIGINAL_TEXT,
            )
        )
    ).scalar_one_or_none()
    preview_version_obj = (
        await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.version_type == DocumentVersionType.PREVIEW_ANONYMIZED,
            )
        )
    ).scalar_one_or_none()
    final_version_obj = (
        await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.version_type == DocumentVersionType.FINAL_ANONYMIZED,
            )
        )
    ).scalar_one_or_none()

    entity_type_rows = (
        await db.execute(
            select(EntityDetection.entity_type, func.count()).where(
                EntityDetection.document_id == document.id
            ).group_by(EntityDetection.entity_type)
        )
    ).all()
    entity_types_count = {
        str(entity_type): int(cnt) for entity_type, cnt in entity_type_rows
    }

    llm_request_rows = (
        await db.execute(
            select(
                LlmRequest.id,
                LlmRequest.provider,
                LlmRequest.model,
                LlmRequest.profile,
                LlmRequest.status,
                LlmRequest.human_status,
                LlmRequest.snippets_meta,
            ).where(LlmRequest.document_id == document.id)
        )
    ).all()

    llm_requests: dict[str, dict] = {}
    llm_request_ids: list[uuid.UUID] = []
    for (
        req_id,
        provider,
        model,
        profile,
        status_str,
        human_status,
        snippets_meta,
    ) in llm_request_rows:
        llm_request_ids.append(req_id)
        req_key = str(req_id)
        snippets = []
        try:
            if (
                isinstance(snippets_meta, dict)
                and isinstance(snippets_meta.get("snippets"), list)
            ):
                snippets = snippets_meta.get("snippets", [])
        except Exception:
            snippets = []

        snippet_count = len(snippets)
        snippet_hashes = [
            s.get("sha256")
            for s in snippets
            if isinstance(s, dict) and s.get("sha256")
        ][:10]

        llm_requests[req_key] = {
            "llm_request_id": req_key,
            "provider": provider,
            "model": model,
            "profile": profile,
            "status": status_str,
            "human_status": human_status,
            "snippets_count": int(snippet_count),
            "snippets_hashes_sample": snippet_hashes,
            "suggestions": {},
        }

    suggestions_rows = []
    if llm_request_ids:
        suggestions_rows = (
            await db.execute(
                select(
                    LlmSuggestion.llm_request_id,
                    LlmSuggestion.entity_type,
                    LlmSuggestion.replacement_token,
                    func.count(),
                    func.avg(LlmSuggestion.confidence),
                )
                .where(LlmSuggestion.llm_request_id.in_(llm_request_ids))
                .group_by(
                    LlmSuggestion.llm_request_id,
                    LlmSuggestion.entity_type,
                    LlmSuggestion.replacement_token,
                )
            )
        ).all()

    for req_id, entity_type, replacement_token, cnt, avg_conf in suggestions_rows:
        req_key = str(req_id)
        req_obj = llm_requests.get(req_key)
        if not req_obj:
            continue
        et_key = f"{entity_type}::{replacement_token}"
        req_obj["suggestions"][et_key] = {
            "count": int(cnt),
            "avg_confidence": float(avg_conf or 0.0),
        }

    return JSONResponse(
        {
            "document_id": str(document.id),
            "document_sha256": document.sha256,
            "versions_sha256": {
                "original": _sha256_text(
                    original_version_obj.content_text if original_version_obj else None
                ),
                "preview_anonymized": _sha256_text(
                    preview_version_obj.content_text if preview_version_obj else None
                ),
                "final_anonymized": _sha256_text(
                    final_version_obj.content_text if final_version_obj else None
                ),
            },
            "detections_entity_types_count": entity_types_count,
            "llm_requests": list(llm_requests.values()),
        }
    )


# ──────────────────────────────────────────────────────────────────────
# ACCOUNTING RECORDS HELPER
# ──────────────────────────────────────────────────────────────────────

_AMOUNT_PAT = re.compile(
    r"\b\d{1,3}(?:[\s\u00a0]?\d{3})*(?:[.,]\d{2})?\b\s*(?:€|EUR)?", re.IGNORECASE
)
_CODE_LINE_PAT = re.compile(r"^\s*(\d{3,6})\b")


def _pcg_category(code: str) -> str:
    """Map a PCG account code to a human-readable category."""
    if not code:
        return "inconnu"
    code = code.strip()
    mapping = [
        ("401", "fournisseur"), ("411", "client"), ("455", "associe_compte_courant"),
        ("467", "creance_diverse"), ("512", "banque_caisse"), ("53", "banque_caisse"),
        ("62", "honoraires"), ("63", "impots"), ("64", "personnel_charge"),
        ("66", "charges_financieres"), ("16", "emprunt"), ("26", "participation"),
        ("21", "immobilisation"),
    ]
    for prefix, category in mapping:
        if code.startswith(prefix):
            return category

    classes = {"1": "capitaux", "2": "immobilisation", "3": "stock", "4": "tiers",
               "5": "tresorerie", "6": "charge", "7": "produit", "8": "autre"}
    return classes.get(code[0], "autre") if code else "inconnu"


def _extract_accounting_records(text: str) -> list[dict]:
    """Extract structured accounting records from anonymized text."""
    records: list[dict] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m_code = _CODE_LINE_PAT.search(line)
        if not m_code:
            continue
        code = m_code.group(1)
        amounts = list(_AMOUNT_PAT.finditer(line))
        amount_raw = amounts[-1].group(0) if amounts else None
        records.append({
            "code_comptable": code,
            "categorie_pcg": _pcg_category(code),
            "montant_raw": amount_raw,
            "libelle": line,
        })
    return records
