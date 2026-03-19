"""ConfiDoc Backend — Document processing pipeline service."""

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.models.entity_detection import EntityDetection
from app.services.anonymization_service import (
    anonymize_text,
    classify_document_type,
    extract_text_from_file,
)


async def build_anonymization_preview(
    db: AsyncSession,
    document: Document,
    file_content: bytes,
    profile: str = "moderate",
    document_type: str = "auto",
) -> tuple[str, list[dict], str]:
    """Compute anonymization preview and persist versions/detections."""
    document.status = DocumentStatus.PROCESSING
    await db.flush()

    original_text = extract_text_from_file(file_content, document.extension) or ""
    effective_type = (
        classify_document_type(original_text, document.original_filename)
        if document_type == "auto"
        else document_type
    )
    preview_text, detections = anonymize_text(
        original_text,
        profile=profile,
        document_type=effective_type,
    )

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
    await db.flush()
    return preview_text, detections, effective_type
