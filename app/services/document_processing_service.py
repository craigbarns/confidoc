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
from app.services.mistral_ocr_service import extract_text_from_file
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
    
    # Extraction OCR Mistral
    original_text, extraction_meta = await extract_text_from_file(
        file_content, document.extension
    )
    
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
    # Le profil "strict" force l'utilisation du LLM pour une anonymisation plus complète
    effective_use_llm = use_llm or (profile == "strict")

    entity_summary: dict[str, int] = {}

    if effective_use_llm:
        # Anonymisation LLM (Mistral) — plus exhaustive
        preview_text, detections = await anonymize_document_full(original_text)
        method = "llm:mistral-large"
    else:
        # Anonymisation par dictionnaire (déterministe, fiable, rapide)
        preview_text, detections, registry = await anonymize_document_dictionary(original_text)
        method = "dictionary"
        entity_summary = registry.export_entity_summary()
    
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
    
    for item in detections:
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
    
    document.status = DocumentStatus.READY
    await db.flush()
    
    logger.info(
        "llm_anonymization_complete",
        doc_id=str(document.id),
        detections=len(detections),
        method=method,
    )
    
    meta = {
        "method": method,
        "detections_count": len(detections),
        "entity_summary": entity_summary,
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
