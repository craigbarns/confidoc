"""ConfiDoc Backend — Document processing pipeline service (v5)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.text_sanitize import postgres_safe_text
from app.models.document import Document, DocumentStatus
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.models.entity_detection import EntityDetection
from app.services.anonymization.detector import deduplicate, detect_entities
from app.services.anonymization.pseudonymizer import apply_business_pseudonyms
from app.services.audit_trail_service import record_document_audit_event
from app.services.entity_registry import EntityRegistry
from app.services.extraction.service import extract_text_from_file_with_meta
from app.services.llm_anonymization_service import anonymize_with_llm

logger = get_logger(__name__)


async def build_extraction_ocr(
    db: AsyncSession,
    document: Document,
    file_content: bytes,
) -> tuple[str, dict[str, Any]]:
    """Étape 1: Extraction OCR (Mistral first, then local fallbacks)."""
    document.status = DocumentStatus.EXTRACTING
    await db.flush()

    try:
        # Unified extraction logic
        original_text, extraction_meta = await extract_text_from_file_with_meta(
            file_content, document.extension
        )

        if not original_text.strip():
            raise ValueError("Extraction produced empty text")

    except Exception as exc:
        logger.error("extraction_pipeline_failed", doc_id=str(document.id), error=str(exc))
        document.status = DocumentStatus.FAILED
        try:
            await record_document_audit_event(
                db,
                document=document,
                action="pipeline:extract_failed",
                status_code=500,
                details={"error_type": type(exc).__name__},
            )
        except Exception as audit_exc:
            logger.warning("audit_extract_failure_event_failed", error=str(audit_exc))
        await db.commit()
        raise ValueError(f"Échec de l'extraction : {str(exc)}") from exc

    # Sauvegarde le texte OCR brut
    await db.execute(
        delete(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.ORIGINAL_TEXT,
        )
    )

    original_version = DocumentVersion(
        document_id=document.id,
        version_type=DocumentVersionType.ORIGINAL_TEXT,
        content_text=postgres_safe_text(original_text),
    )
    db.add(original_version)
    document.status = DocumentStatus.EXTRACTED
    try:
        await record_document_audit_event(
            db,
            document=document,
            action="pipeline:extract",
            details={
                "method": extraction_meta.get("method"),
                "provider": extraction_meta.get("provider"),
                "pages": extraction_meta.get("pages"),
                "ocr_chars": len(original_text),
            },
        )
    except Exception as exc:
        logger.warning("audit_extract_event_failed", doc_id=str(document.id), error=str(exc))
    await db.flush()

    return original_text, extraction_meta


async def build_anonymization_llm(
    db: AsyncSession,
    document: Document,
    original_text: str,
    use_llm: bool = False,
    profile: str = "moderate",
    document_type: str = "auto",
) -> tuple[str, list[dict], dict[str, Any]]:
    """Étape 2: Anonymisation (V5 Unified).

    This version ensures EntityRegistry is ALWAYS used for stable placeholders,
    even when using the LLM for detection.
    """
    document.status = DocumentStatus.ANONYMIZING
    await db.flush()

    registry = EntityRegistry()

    effective_use_llm = use_llm or (profile == "strict")

    deterministic_detections = detect_entities(
        original_text,
        profile=profile,
        document_type=document_type,
    )

    if effective_use_llm:
        method = "llm+dictionary"
        # 1. Use LLM to detect entities
        llm_result = await anonymize_with_llm(original_text)
        detections = deduplicate([*deterministic_detections, *llm_result.get("entities", [])])

        # 2. Convert LLM generic tokens to stable placeholders via Registry
        detections = apply_business_pseudonyms(original_text, detections, registry)
    else:
        method = "dictionary"
        # 1. Use Regex patterns to detect entities
        detections = deterministic_detections

        # 2. Apply stable placeholders
        detections = apply_business_pseudonyms(original_text, detections, registry)

    # 3. Apply replacements to text
    preview_text = original_text
    for match in sorted(detections, key=lambda m: m["start_index"], reverse=True):
        preview_text = (
            preview_text[: match["start_index"]]
            + match["replacement"]
            + preview_text[match["end_index"] :]
        )

    # 4. Final Cleanup
    from app.services.anonymization.cleanup import clean_ocr_artifacts
    preview_text = clean_ocr_artifacts(preview_text)

    # 5. Persistence
    await db.execute(
        delete(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.PREVIEW_ANONYMIZED,
        )
    )

    preview_version = DocumentVersion(
        document_id=document.id,
        version_type=DocumentVersionType.PREVIEW_ANONYMIZED,
        content_text=postgres_safe_text(preview_text),
    )
    db.add(preview_version)

    await db.execute(delete(EntityDetection).where(EntityDetection.document_id == document.id))

    if detections:
        rows = [
            {
                "id": uuid4(),
                "document_id": document.id,
                "document_version_id": preview_version.id,
                "entity_type": str(item.get("entity_type", "unknown"))[:40],
                "start_index": int(item.get("start_index", 0)),
                "end_index": int(item.get("end_index", 0)),
                "value_excerpt": postgres_safe_text(str(item.get("value_excerpt", "")))[:1000],
                "replacement": postgres_safe_text(str(item.get("replacement", "[REDACTED]")))[:500],
            }
            for item in detections
        ]
        await db.execute(insert(EntityDetection), rows)

    document.status = DocumentStatus.READY
    try:
        await record_document_audit_event(
            db,
            document=document,
            action="pipeline:anonymize",
            details={
                "method": method,
                "profile": profile,
                "document_type": document_type,
                "detections_count": len(detections),
                "entity_summary": registry.export_entity_summary(),
            },
        )
    except Exception as exc:
        logger.warning("audit_anonymize_event_failed", doc_id=str(document.id), error=str(exc))
    await db.flush()

    # RAG embedding
    try:
        from app.services.rag_service import embed_document
        await embed_document(db, document.id, preview_text)
    except Exception:
        pass

    return preview_text, detections, {
        "method": method,
        "detections_count": len(detections),
        "entity_summary": registry.export_entity_summary(),
        "registry_raw_mapping": registry.export_raw_mapping(),
    }


async def build_anonymization_preview(
    db: AsyncSession,
    document: Document,
    file_content: bytes,
    profile: str = "moderate",
    document_type: str = "auto",
) -> tuple[str, list[dict], str, dict[str, Any]]:
    """Pipeline complet (legacy compat)."""
    original_text, extraction_meta = await build_extraction_ocr(db, document, file_content)
    preview_text, detections, anon_meta = await build_anonymization_llm(
        db, document, original_text, profile=profile, document_type=document_type
    )
    return preview_text, detections, "document", extraction_meta
