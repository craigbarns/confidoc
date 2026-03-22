"""ConfiDoc Backend — Document processing pipeline service (v2)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.logging import get_logger
from app.models.document import Document, DocumentStatus
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.models.entity_detection import EntityDetection
from app.models.llm_request import LlmRequest
from app.models.llm_suggestion import LlmSuggestion
from app.services.anonymization_service import (
    anonymize_text,
    classify_document_type,
    extract_text_from_file,
)

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


async def _call_llm_provider(
    settings: Any, snippets: list[dict], document: Document,
    profile: str, db: AsyncSession,
) -> tuple[list[dict], LlmRequest | None]:
    """Call external NER/LLM provider (Mistral, HuggingFace, or Presidio)."""
    from app.services.llm_assist_service import build_snippets, propose_spans_mistral

    llm_detections: list[dict] = []

    snippets_meta = [
        {"start": s["start"], "end": s["end"], "sha256": s["sha256"]} for s in snippets
    ]

    llm_model = settings.MISTRAL_MODEL
    propose_fn = propose_spans_mistral

    if settings.LLM_PROVIDER == "huggingface":
        from app.services.hf_ner_assist_service import propose_spans_huggingface_ner
        llm_model = settings.HF_MODEL
        propose_fn = propose_spans_huggingface_ner
    elif settings.LLM_PROVIDER == "presidio":
        from app.services.presidio_ner_assist_service import propose_spans_presidio
        llm_model = "presidio-local"
        propose_fn = propose_spans_presidio

    llm_req = LlmRequest(
        document_id=document.id,
        created_by_user_id=document.uploaded_by_user_id,
        preview_version_id=None,
        provider=settings.LLM_PROVIDER,
        model=llm_model,
        profile=profile,
        snippets_meta={"snippets": snippets_meta},
        status="completed",
        human_status="pending",
        error_message=None,
    )
    db.add(llm_req)
    await db.flush()

    try:
        for s in snippets:
            spans = await propose_fn(s["text"])
            for span in spans:
                conf = float(span.get("confidence", 0.0))
                if conf < settings.LLM_CONFIDENCE_THRESHOLD:
                    continue

                start_global = int(s["start"]) + int(span["start"])
                end_global = int(s["start"]) + int(span["end"])
                if end_global <= start_global:
                    continue

                # Safely extract value excerpt
                value_excerpt = ""
                try:
                    value_excerpt = s["text"][int(span["start"]):int(span["end"])]
                except (IndexError, KeyError):
                    continue
                if not value_excerpt.strip():
                    continue

                cand = {
                    "entity_type": span["entity_type"],
                    "start_index": start_global,
                    "end_index": end_global,
                    "value_excerpt": value_excerpt,
                    "replacement": span["replacement_token"],
                    "confidence": conf,
                }

                # Dataset accounting: skip amount replacements
                if profile in {"dataset_accounting", "dataset_accounting_pseudo"} and cand.get("replacement") == "[AMOUNT]":
                    continue

                llm_detections.append(cand)
                db.add(
                    LlmSuggestion(
                        llm_request_id=llm_req.id,
                        entity_type=cand["entity_type"],
                        start_index=cand["start_index"],
                        end_index=cand["end_index"],
                        replacement_token=cand["replacement"],
                        confidence=conf,
                    )
                )
    except Exception as exc:
        logger.error("llm_provider_failed", error=str(exc), provider=settings.LLM_PROVIDER)
        llm_req.status = "failed"
        llm_req.error_message = str(exc)[:500]

    return llm_detections, llm_req


async def build_anonymization_preview(
    db: AsyncSession,
    document: Document,
    file_content: bytes,
    profile: str = "moderate",
    document_type: str = "auto",
) -> tuple[str, list[dict], str]:
    """Compute anonymization preview and persist versions/detections.

    Returns:
        (preview_text, merged_detections, effective_document_type)
    """
    settings = get_settings()

    # 1) Mark as processing
    document.status = DocumentStatus.PROCESSING
    await db.flush()

    # 2) Extract text from file
    original_text = extract_text_from_file(file_content, document.extension) or ""

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
        # 3) Classify document type
        effective_type = (
            classify_document_type(original_text, document.original_filename)
            if document_type == "auto"
            else document_type
        )

        # 4) Run regex anonymization
        preview_text, detections = anonymize_text(
            original_text, profile=profile, document_type=effective_type
        )

        # 5) Optionally call LLM/NER provider for additional spans
        should_call_llm = (
            settings.LLM_ASSISTIVE_ENABLED
            and profile in {"moderate", "strict", "dataset_accounting", "dataset_accounting_pseudo"}
            and len(detections) < settings.LLM_MIN_DETECTIONS
            and original_text
        )

        if should_call_llm:
            from app.services.llm_assist_service import build_snippets

            snippets = build_snippets(
                original_text,
                max_snippets=settings.LLM_MAX_SNIPPETS,
                snippet_chars=settings.LLM_SNIPPET_CHARS,
            )
            llm_detections, llm_req_obj = await _call_llm_provider(
                settings, snippets, document, profile, db
            )

        # 6) Merge detections (regex + LLM), removing overlaps
        merged = list(detections)
        for cand in llm_detections:
            if not any(_overlaps(cand, existing) for existing in merged):
                merged.append(cand)

        # Re-apply if LLM added detections
        if llm_detections:
            preview_text = _apply_replacements(original_text, merged)

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

    for item in merged:
        db.add(
            EntityDetection(
                document_id=document.id,
                document_version_id=preview_version.id,
                entity_type=str(item.get("entity_type", "unknown"))[:40],
                start_index=int(item.get("start_index", 0)),
                end_index=int(item.get("end_index", 0)),
                value_excerpt=str(item.get("value_excerpt", ""))[:50_000],
                replacement=str(item.get("replacement", "[REDACTED]"))[:10_000],
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

    return preview_text, merged, effective_type
