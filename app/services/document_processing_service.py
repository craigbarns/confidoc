"""ConfiDoc Backend — Document processing pipeline service (v2)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.logging import get_logger
from app.core.text_sanitize import postgres_safe_text
from app.models.document import Document, DocumentStatus
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.models.entity_detection import EntityDetection
from app.models.llm_request import LlmRequest
from app.services.anonymization_service import (
    extract_text_from_file_with_meta,
)
from app.services.llm_anonymization_service import anonymize_document_full

logger = get_logger(__name__)


def _overlaps(a: dict, b: dict) -> bool:
    """Check if two span dicts overlap."""
    return not (a["end_index"] <= b["start_index"] or a["start_index"] >= b["end_index"])


def _apply_replacements(text: str, detections: list[dict]) -> str:
    """Apply replacement tokens to text, processing from end to preserve indices."""
    out = text
    for match in sorted(detections, key=lambda m: m["start_index"], reverse=True):
        out = out[: match["start_index"]] + match["replacement"] + out[match["end_index"] :]
    return out





async def build_anonymization_preview(
    db: AsyncSession,
    document: Document,
    file_content: bytes,
    profile: str = "moderate",
    document_type: str = "auto",
) -> tuple[str, list[dict], str, dict[str, Any]]:
    """Compute anonymization preview and persist versions/detections.

    Returns:
        (preview_text, merged_detections, effective_document_type, extraction_meta)
    """
    settings = get_settings()

    # 1) Mark as processing
    document.status = DocumentStatus.PROCESSING
    await db.flush()

    # 2) Extract text from file (+ extraction metadata for observability)
    original_text, extraction_meta = extract_text_from_file_with_meta(
        file_content, document.extension
    )
    original_text = original_text or ""

    llm_detections: list[dict] = []
    llm_req_obj: LlmRequest | None = None
    merged: list[dict] = []
    preview_text = ""
    effective_type = "empty"

    if not original_text.strip():
        # Même sans texte (PNG vide, scan illisible…), on persiste les versions pour
        # GET /preview, export-structured, smoke e2e — sinon 404 + anonymize instable.
        logger.warning("empty_text_extraction", doc_id=str(document.id))
    else:
        # 3) Anonymisation 100% LLM (Mistral Large)
        # Pas de regex, pas de classification — tout passe par le LLM
        effective_type = document_type if document_type != "auto" else "document"
        
        preview_text, merged = await anonymize_document_full(original_text)
        
        # Log pour observabilité
        logger.info(
            "llm_anonymization_processed",
            doc_id=str(document.id),
            detections=len(merged),
        )

    # 7) Persist: clean old data, save new versions/detections
    await db.execute(
        delete(EntityDetection).where(EntityDetection.document_id == document.id)
    )
    await db.execute(
        delete(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type.in_([
                DocumentVersionType.ORIGINAL_TEXT,
                DocumentVersionType.PREVIEW_ANONYMIZED,
            ]),
        )
    )

    original_version = DocumentVersion(
        document_id=document.id,
        version_type=DocumentVersionType.ORIGINAL_TEXT,
        content_text=postgres_safe_text(original_text),
    )
    preview_version = DocumentVersion(
        document_id=document.id,
        version_type=DocumentVersionType.PREVIEW_ANONYMIZED,
        content_text=postgres_safe_text(preview_text),
    )
    db.add(original_version)
    db.add(preview_version)
    await db.flush()

    for item in merged:
        db.add(
            EntityDetection(
                document_id=document.id,
                document_version_id=preview_version.id,
                entity_type=str(item.get("entity_type", "unknown"))[:40],
                start_index=int(item.get("start_index", 0)),
                end_index=int(item.get("end_index", 0)),
                value_excerpt=postgres_safe_text(str(item.get("value_excerpt", "")))[:50_000],
                replacement=postgres_safe_text(str(item.get("replacement", "[REDACTED]")))[:10_000],
            )
        )

    if llm_req_obj is not None:
        llm_req_obj.preview_version_id = preview_version.id

    document.status = DocumentStatus.READY
    await db.flush()

    logger.info(
        "anonymization_complete",
        doc_id=str(document.id),
        doc_type=effective_type,
        profile=profile,
        detections=len(merged),
    )

    return preview_text, merged, effective_type, extraction_meta
