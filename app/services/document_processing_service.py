"""ConfiDoc Backend — Document processing pipeline service."""

from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
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
from app.services.llm_assist_service import build_snippets, propose_spans_mistral


async def build_anonymization_preview(
    db: AsyncSession,
    document: Document,
    file_content: bytes,
    profile: str = "moderate",
    document_type: str = "auto",
) -> tuple[str, list[dict], str]:
    """Compute anonymization preview and persist versions/detections."""
    settings = get_settings()

    def overlaps(a: dict, b: dict) -> bool:
        return not (a["end_index"] <= b["start_index"] or a["start_index"] >= b["end_index"])

    def apply_replacements(text: str, dets: list[dict]) -> str:
        out = text
        for match in sorted(dets, key=lambda m: m["start_index"], reverse=True):
            out = (
                out[: match["start_index"]]
                + match["replacement"]
                + out[match["end_index"] :]
            )
        return out

    document.status = DocumentStatus.PROCESSING
    await db.flush()

    original_text = extract_text_from_file(file_content, document.extension) or ""
    effective_type = (
        classify_document_type(original_text, document.original_filename)
        if document_type == "auto"
        else document_type
    )

    preview_text, detections = anonymize_text(
        original_text, profile=profile, document_type=effective_type
    )

    llm_detections: list[dict] = []
    llm_req_obj: LlmRequest | None = None

    should_call_llm = (
        settings.LLM_ASSISTIVE_ENABLED
        and profile in {"moderate", "strict", "dataset_accounting"}
        and len(detections) < settings.LLM_MIN_DETECTIONS
        and original_text
    )

    if should_call_llm:
        snippets = build_snippets(
            original_text,
            max_snippets=settings.LLM_MAX_SNIPPETS,
            snippet_chars=settings.LLM_SNIPPET_CHARS,
        )
        snippets_meta = [
            {"start": s["start"], "end": s["end"], "sha256": s["sha256"]} for s in snippets
        ]

        llm_req_obj = LlmRequest(
            document_id=document.id,
            created_by_user_id=document.uploaded_by_user_id,
            preview_version_id=None,
            provider=settings.LLM_PROVIDER,
            model=settings.MISTRAL_MODEL,
            profile=profile,
            snippets_meta={"snippets": snippets_meta},
            status="completed",
            human_status="pending",
            error_message=None,
        )
        db.add(llm_req_obj)
        await db.flush()

        try:
            for s in snippets:
                spans = await propose_spans_mistral(s["text"])
                for span in spans:
                    conf = float(span.get("confidence", 0.0))
                    if conf < settings.LLM_CONFIDENCE_THRESHOLD:
                        continue

                    start_global = int(s["start"]) + int(span["start"])
                    end_global = int(s["start"]) + int(span["end"])
                    if end_global <= start_global:
                        continue

                    value_excerpt = original_text[start_global:end_global]
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

                    # Profil dataset comptable: ne pas proposer/ajouter de remplacements de montants.
                    if profile == "dataset_accounting" and cand.get("replacement") == "[AMOUNT]":
                        continue

                    if any(overlaps(cand, existing) for existing in detections):
                        continue

                    llm_detections.append(cand)
                    db.add(
                        LlmSuggestion(
                            llm_request_id=llm_req_obj.id,
                            entity_type=cand["entity_type"],
                            start_index=cand["start_index"],
                            end_index=cand["end_index"],
                            replacement_token=cand["replacement"],
                            confidence=conf,
                        )
                    )
        except Exception as exc:
            llm_req_obj.status = "failed"
            llm_req_obj.error_message = str(exc)

    merged = list(detections)
    if llm_detections:
        for cand in llm_detections:
            if any(overlaps(cand, existing) for existing in merged):
                continue
            merged.append(cand)
        preview_text = apply_replacements(original_text, merged)

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

    for item in merged:
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

    if llm_req_obj is not None:
        llm_req_obj.preview_version_id = preview_version.id

    document.status = DocumentStatus.READY
    await db.flush()
    return preview_text, merged, effective_type
