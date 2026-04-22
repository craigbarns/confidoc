"""ConfiDoc Backend — Document processing pipeline service (v3)."""

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
from app.services.dictionary_anonymization_service import anonymize_document_dictionary
from app.services.llm_anonymization_service import anonymize_document_full

logger = get_logger(__name__)


async def build_extraction_ocr(
    db: AsyncSession,
    document: Document,
    file_content: bytes,
) -> tuple[str, dict[str, Any]]:
    """Étape 1: Extraction OCR via Mistral."""
    document.status = DocumentStatus.PROCESSING
    await db.flush()

    settings = get_settings()
    original_text = ""
    extraction_meta: dict[str, Any] = {}

    if settings.MISTRAL_ENABLED and settings.MISTRAL_API_KEY:
        try:
            from app.services.mistral_ocr_service import extract_text_from_file
            original_text, extraction_meta = await extract_text_from_file(
                file_content, document.extension
            )
            if not original_text.strip():
                raise ValueError("mistral_ocr_empty_text")
        except Exception as exc:
            logger.warning("mistral_ocr_failed_fallback_to_local", error=str(exc)[:200])
            original_text = ""

    if not original_text.strip():
        try:
            import asyncio
            from app.services.fast_extraction_service import extract_text_sync
            loop = asyncio.get_running_loop()
            fast_result = await loop.run_in_executor(
                None, extract_text_sync, file_content, document.extension
            )
            if fast_result["text"].strip():
                original_text = fast_result["text"]
                extraction_meta = {
                    "method": fast_result["method"],
                    "pages": fast_result["pages"],
                }
        except Exception as exc:
            logger.error("local_extraction_failed", error=str(exc)[:200])

    if not original_text.strip():
        raise ValueError("Impossible d'extraire du texte du document.")

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
    await db.flush()

    return original_text, extraction_meta


async def build_anonymization_llm(
    db: AsyncSession,
    document: Document,
    original_text: str,
    use_llm: bool = False,
    profile: str = "moderate",
) -> tuple[str, list[dict], dict[str, Any]]:
    """Étape 2: Anonymisation. 
    
    V3 Fix: Separated Dictionary and LLM paths to avoid index corruption.
    """
    entity_summary: dict[str, int] = {}
    registry_raw_mapping = {}
    
    effective_use_llm = use_llm or (profile == "strict")

    if effective_use_llm:
        # LLM Path: Works on original text
        method = "llm"
        preview_text, detections = await anonymize_document_full(original_text)
        # In LLM path, registry is usually empty unless we implement a parser
        from app.services.entity_registry import EntityRegistry
        registry = EntityRegistry()
    else:
        # Dictionary Path (Default): Deterministic and stable
        method = "dictionary"
        preview_text, detections, registry = await anonymize_document_dictionary(original_text)
        entity_summary = registry.export_entity_summary()
        registry_raw_mapping = registry.export_raw_mapping()

    # Sauvegarde le texte anonymisé
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
    await db.flush()

    # Sauvegarde les détections
    await db.execute(
        delete(EntityDetection).where(EntityDetection.document_id == document.id)
    )

    if detections:
        from uuid import uuid4
        from sqlalchemy import insert
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
    await db.flush()

    # RAG embedding (async background)
    try:
        from app.services.rag_service import embed_document
        await embed_document(db, document.id, preview_text)
    except Exception:
        pass

    meta = {
        "method": method,
        "detections_count": len(detections),
        "entity_summary": entity_summary,
        "registry_raw_mapping": registry_raw_mapping,
    }

    return preview_text, detections, meta


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
        db, document, original_text, profile=profile
    )
    return preview_text, detections, "document", extraction_meta
