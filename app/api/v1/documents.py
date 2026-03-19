"""ConfiDoc Backend — Documents endpoints."""

import uuid
from io import BytesIO

from fastapi import APIRouter, Query, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy import delete, desc, select

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import http_400, http_404
from app.models.document import Document, DocumentStatus
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.models.entity_detection import EntityDetection
from app.schemas.document import (
    AnonymizeResponse,
    DetectionResponse,
    DocumentPreviewResponse,
    DocumentResponse,
)
from app.services.anonymization_service import anonymize_text, extract_text_from_file
from app.services.pdf_redaction_service import redact_pdf_bytes
from app.services.storage_service import read_bytes

router = APIRouter()


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
) -> list[Document]:
    result = await db.execute(
        select(Document)
        .where(Document.uploaded_by_user_id == current_user.id)
        .order_by(desc(Document.created_at))
        .limit(limit)
    )
    return list(result.scalars().all())


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Détail d'un document",
)
async def get_document(document_id: str, current_user: CurrentUser, db: DbSession) -> Document:
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
) -> AnonymizeResponse:
    document = await _get_user_document_or_404(db, document_id, current_user.id)
    document.status = DocumentStatus.PROCESSING
    await db.flush()

    file_content = read_bytes(document.storage_backend, document.storage_key)
    original_text = extract_text_from_file(file_content, document.extension)
    if not original_text:
        original_text = ""

    preview_text, detections = anonymize_text(original_text)

    # Replace prior computed preview data for idempotence
    await db.execute(delete(EntityDetection).where(EntityDetection.document_id == document.id))
    await db.execute(
        delete(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type.in_(
                [DocumentVersionType.ORIGINAL_TEXT, DocumentVersionType.PREVIEW_ANONYMIZED]
            ),
        )
    )

    original_version = DocumentVersion(
        document_id=document.id,
        version_type=DocumentVersionType.ORIGINAL_TEXT,
        content_text=original_text,
    )
    preview_version = DocumentVersion(
        document_id=document.id,
        version_type=DocumentVersionType.PREVIEW_ANONYMIZED,
        content_text=preview_text,
    )
    db.add(original_version)
    db.add(preview_version)
    await db.flush()

    for item in detections:
        db.add(
            EntityDetection(
                document_id=document.id,
                document_version_id=preview_version.id,
                entity_type=item["entity_type"],
                start_index=item["start_index"],
                end_index=item["end_index"],
                value_excerpt=item["value_excerpt"],
                replacement=item["replacement"],
            )
        )

    document.status = DocumentStatus.READY
    await db.commit()

    return AnonymizeResponse(
        document_id=document.id,
        status=document.status.value,
        detections_count=len(detections),
        detections=[DetectionResponse(**item) for item in detections],
        preview_text=preview_text,
    )


@router.get(
    "/{document_id}/preview",
    response_model=DocumentPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Prévisualiser l'anonymisation",
)
async def preview_document(document_id: str, current_user: CurrentUser, db: DbSession) -> DocumentPreviewResponse:
    document = await _get_user_document_or_404(db, document_id, current_user.id)

    preview_result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.PREVIEW_ANONYMIZED,
        )
    )
    preview_version = preview_result.scalar_one_or_none()
    if not preview_version:
        raise http_404("Aucune preview disponible. Lance /anonymize d'abord")

    count_result = await db.execute(
        select(EntityDetection).where(EntityDetection.document_id == document.id)
    )
    detections_count = len(list(count_result.scalars().all()))

    return DocumentPreviewResponse(
        document_id=document.id,
        status=document.status.value,
        preview_text=preview_version.content_text,
        detections_count=detections_count,
    )


@router.post(
    "/{document_id}/validate",
    status_code=status.HTTP_200_OK,
    summary="Valider la preview et figer la version finale",
)
async def validate_document(document_id: str, current_user: CurrentUser, db: DbSession) -> dict:
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
    await db.commit()
    return {"status": "validated", "document_id": str(document.id)}


@router.get(
    "/{document_id}/export",
    response_class=PlainTextResponse,
    status_code=status.HTTP_200_OK,
    summary="Exporter la version finale anonymisée (texte)",
)
async def export_document(document_id: str, current_user: CurrentUser, db: DbSession) -> PlainTextResponse:
    document = await _get_user_document_or_404(db, document_id, current_user.id)
    final_result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.FINAL_ANONYMIZED,
        )
    )
    final_version = final_result.scalar_one_or_none()
    if not final_version:
        raise http_404("Aucune version finale disponible. Lance /validate d'abord")

    return PlainTextResponse(final_version.content_text)


@router.get(
    "/{document_id}/export-pdf",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
    summary="Exporter un PDF visuellement redacted",
)
async def export_redacted_pdf(document_id: str, current_user: CurrentUser, db: DbSession) -> StreamingResponse:
    document = await _get_user_document_or_404(db, document_id, current_user.id)
    if document.extension.lower() != "pdf":
        raise http_400("Export PDF redacted disponible uniquement pour les PDF")

    detections_result = await db.execute(
        select(EntityDetection).where(EntityDetection.document_id == document.id)
    )
    detections = list(detections_result.scalars().all())
    if not detections:
        raise http_404("Aucune détection disponible. Lance /anonymize d'abord")

    original_bytes = read_bytes(document.storage_backend, document.storage_key)
    sensitive_values = [item.value_excerpt for item in detections]
    redacted_bytes = redact_pdf_bytes(original_bytes, sensitive_values)

    download_name = f"redacted_{document.original_filename}"
    headers = {"Content-Disposition": f'attachment; filename="{download_name}"'}
    return StreamingResponse(BytesIO(redacted_bytes), media_type="application/pdf", headers=headers)
