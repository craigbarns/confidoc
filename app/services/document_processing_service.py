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
from app.services.llm_anonymization_service import anonymize_document_full
from app.services.dictionary_anonymization_service import anonymize_document_dictionary

logger = get_logger(__name__)


async def build_extraction_ocr(
    db: AsyncSession,
    document: Document,
    file_content: bytes,
) -> tuple[str, dict[str, Any]]:
    """Étape 1: Extraction OCR via Mistral.
    
    Returns:
        (texte_extrait, metadata)
    """
    document.status = DocumentStatus.PROCESSING
    await db.flush()
    
    # Extraction: Mistral OCR (premium) -> Fast PyMuPDF fallback -> Docling fallback
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
            logger.warning("mistral_ocr_failed_fallback_to_pymupdf", error=str(exc)[:200])
            original_text = ""

    if not original_text.strip():
        try:
            from app.services.fast_extraction_service import extract_text_sync
            import asyncio
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
            else:
                raise ValueError(f"fast extraction returned empty text: {fast_result.get('error')}")
        except Exception as exc:
            logger.warning("fast_extraction_failed_using_docling", error=str(exc)[:200])
            try:
                from app.services.docling_service import extract_text_from_file_docling
                original_text, extraction_meta = await extract_text_from_file_docling(
                    file_content, document.extension
                )
            except Exception as exc2:
                logger.error("docling_failed_no_more_fallbacks", error=str(exc2)[:200])
                raise
    
    if not original_text.strip():
        logger.warning("empty_text_extraction", doc_id=str(document.id))
        original_text = ""
    
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
    
    logger.info(
        "ocr_extraction_complete",
        doc_id=str(document.id),
        chars=len(original_text),
        pages=extraction_meta.get("pages", 0),
    )
    
    return original_text, extraction_meta


async def build_anonymization_llm(
    db: AsyncSession,
    document: Document,
    original_text: str,
    use_llm: bool = False,  # Par défaut: dictionnaire (plus fiable)
    profile: str = "moderate",  # "moderate" = dictionnaire, "strict" = LLM
) -> tuple[str, list[dict], dict[str, Any]]:
    """Étape 2: Anonymisation via dictionnaire ou LLM.

    Args:
        use_llm: Si True, utilise Mistral LLM. Sinon, dictionnaire (défaut).
        profile: "moderate" (dictionnaire rapide) ou "strict" (LLM, plus exhaustif).

    Returns:
        (texte_anonymise, detections, metadata)
    """
    entity_summary: dict[str, int] = {}

    # ALWAYS run dictionary first (deterministic, reliable, fast)
    preview_text, detections, registry = await anonymize_document_dictionary(original_text)
    method = "dictionary"
    entity_summary = registry.export_entity_summary()

    effective_use_llm = use_llm or (profile == "strict")
    if effective_use_llm:
        try:
            llm_text, llm_detections = await anonymize_document_full(preview_text)
            if llm_detections:
                preview_text = llm_text
                detections.extend(llm_detections)
                method = "dictionary+llm"
        except Exception as exc:
            logger.warning("llm_second_pass_skipped", error=str(exc))
    
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
    
    # Sauvegarde les détections (bulk insert for performance)
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
                "value_excerpt": postgres_safe_text(str(item.get("value_excerpt", "")))[:50_000],
                "replacement": postgres_safe_text(str(item.get("replacement", "[REDACTED]")))[:10_000],
            }
            for item in detections
        ]
        await db.execute(insert(EntityDetection), rows)
    
    document.status = DocumentStatus.READY
    await db.flush()
    
    logger.info(
        "llm_anonymization_complete",
        doc_id=str(document.id),
        detections=len(detections),
        method=method,
    )
    
    registry_raw_mapping = {}
    if registry:
        registry_raw_mapping = registry.export_raw_mapping()

    meta = {
        "method": method,
        "detections_count": len(detections),
        "entity_summary": entity_summary,
        "registry_raw_mapping": registry_raw_mapping,
    }
    
    return preview_text, detections, meta


# Fonction legacy pour compatibilité (OCR + Anonymisation en une fois)
async def build_anonymization_preview(
    db: AsyncSession,
    document: Document,
    file_content: bytes,
    profile: str = "moderate",
    document_type: str = "auto",
) -> tuple[str, list[dict], str, dict[str, Any]]:
    """Pipeline complet: OCR + Anonymisation (legacy)."""
    # Étape 1: OCR
    original_text, extraction_meta = await build_extraction_ocr(
        db, document, file_content
    )
    
    # Étape 2: Anonymisation
    preview_text, detections, anon_meta = await build_anonymization_llm(
        db, document, original_text
    )
    
    return preview_text, detections, "document", extraction_meta
