"""ConfiDoc — Documents processing endpoints.

Routes : /status, extract, extracted-text, anonymize, process (legacy),
         structured, status, preview, validate, approve-export.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, Query, status
from sqlalchemy import delete, func, select

from app.api.deps import CurrentUser, DbSession
from app.api.v1._doc_shared import (
    _get_anonymized_text,
    _get_user_document_or_404,
    _infer_semantic_type,
    _read_file_or_404,
)
from app.core.exceptions import http_400, http_404, http_500
from app.core.logging import get_logger
from app.core.text_sanitize import postgres_safe_text
from app.models.document import DocumentStatus
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.models.entity_detection import EntityDetection
from app.schemas.document import (
    DocumentPreviewResponse,
    EntityMappingItem,
    StructuredDocumentResponse,
    ValidateDocumentRequest,
)

router = APIRouter()
logger = get_logger(__name__)


@router.get(
    "/{document_id}/status",
    status_code=status.HTTP_200_OK,
    summary="Vérifier le statut OCR + Anonymisation",
)
async def document_status(
    document_id: str, current_user: CurrentUser, db: DbSession
) -> dict:
    document = await _get_user_document_or_404(db, document_id, current_user.id)

    result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.ORIGINAL_TEXT,
        )
    )
    original = result.scalar_one_or_none()

    result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.PREVIEW_ANONYMIZED,
        )
    )
    preview = result.scalar_one_or_none()

    count_result = await db.execute(
        select(func.count()).select_from(EntityDetection).where(
            EntityDetection.document_id == document.id
        )
    )
    detections_count = count_result.scalar() or 0

    return {
        "document_id": str(document.id),
        "status": document.status.value,
        "extraction": {
            "done": original is not None and bool(original.content_text),
            "text_length": len(original.content_text) if original and original.content_text else 0,
        },
        "anonymization": {
            "done": preview is not None and bool(preview.content_text),
            "preview_length": len(preview.content_text) if preview and preview.content_text else 0,
            "detections_count": detections_count,
        },
        "next_steps": [] if (preview and preview.content_text) else (
            ["anonymize"] if (original and original.content_text) else ["extract", "anonymize"]
        ),
    }


@router.post(
    "/{document_id}/extract",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Étape 1 : Extraire le texte via Mistral OCR (Async)",
)
async def extract_document(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    document = await _get_user_document_or_404(db, document_id, current_user.id)
    
    document.status = DocumentStatus.PROCESSING
    await db.commit()

    from app.workers.tasks import extract_document_task
    task = extract_document_task.delay(doc_id=str(document.id))

    return {
        "document_id": str(document.id),
        "job_id": task.id,
        "status": "processing",
    }


@router.get(
    "/{document_id}/extracted-text",
    status_code=status.HTTP_200_OK,
    summary="Récupérer le texte OCR extrait (sans le relancer)",
)
async def get_extracted_text(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    document = await _get_user_document_or_404(db, document_id, current_user.id)

    result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.ORIGINAL_TEXT,
        )
    )
    original_version = result.scalar_one_or_none()
    if not original_version or original_version.content_text is None:
        raise http_400("Texte non extrait. Lancez POST /extract d'abord.")

    return {
        "document_id": str(document.id),
        "text": original_version.content_text,
        "text_length": len(original_version.content_text),
        "extraction_date": original_version.created_at.isoformat() if original_version.created_at else None,
    }


@router.post(
    "/{document_id}/anonymize",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Étape 2 : Anonymiser le texte extrait (Async)",
)
async def anonymize_document(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
    auto_extract: bool = Query(default=True),
    use_llm: bool = Query(default=False),
    profile: str = Query(default="moderate", description="moderate | strict"),
    mode: str = Query(default="pseudonymization", description="pseudonymization | anonymization"),
) -> dict:
    document = await _get_user_document_or_404(db, document_id, current_user.id)
    
    document.status = DocumentStatus.PROCESSING
    await db.commit()

    from app.workers.tasks import anonymize_document_task
    task = anonymize_document_task.delay(
        doc_id=str(document.id),
        use_llm=use_llm,
        profile=profile,
        mode=mode,
    )

    return {
        "document_id": str(document.id),
        "job_id": task.id,
        "status": "processing",
    }


@router.post(
    "/{document_id}/process",
    status_code=status.HTTP_202_ACCEPTED,
    summary="[Legacy] Traitement complet OCR + Anonymisation en background",
)
async def process_document_legacy(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
    profile: str = Query(default="moderate"),
    document_type: str = Query(default="auto"),
) -> dict:
    document = await _get_user_document_or_404(db, document_id, current_user.id)
    document.status = DocumentStatus.PROCESSING
    await db.commit()
    from app.workers.tasks import process_document_legacy_task
    task = process_document_legacy_task.delay(
        doc_id=str(document.id),
        profile=profile,
        document_type=document_type,
    )
    return {"document_id": str(document.id), "job_id": task.id, "status": "processing"}


@router.get(
    "/{document_id}/preview",
    response_model=DocumentPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Prévisualiser le document anonymisé",
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

    det_result = await db.execute(
        select(EntityDetection).where(EntityDetection.document_id == document.id)
    )
    detections = list(det_result.scalars().all())
    entity_summary: dict[str, int] = {}
    for det in detections:
        etype = det.entity_type or "unknown"
        entity_summary[etype] = entity_summary.get(etype, 0) + 1

    return DocumentPreviewResponse(
        document_id=document.id,
        status=document.status.value,
        preview_text=preview_version.content_text or "",
        detections_count=len(detections),
        entity_summary=entity_summary,
    )


@router.get(
    "/{document_id}/structured",
    response_model=StructuredDocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Données structurées du document pour IA/RAG",
)
async def get_structured_document(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
    include_text: bool = Query(default=True),
) -> StructuredDocumentResponse:
    document = await _get_user_document_or_404(db, document_id, current_user.id)
    anonymized_text = await _get_anonymized_text(db, document)

    det_result = await db.execute(
        select(EntityDetection).where(EntityDetection.document_id == document.id)
    )
    detections = list(det_result.scalars().all())

    entity_summary: dict[str, int] = {}
    placeholder_counts: dict[str, int] = {}
    for det in detections:
        etype = det.entity_type or "unknown"
        entity_summary[etype] = entity_summary.get(etype, 0) + 1
        replacement = det.replacement or "[REDACTED]"
        placeholder_counts[replacement] = placeholder_counts.get(replacement, 0) + 1

    entity_tags = [
        EntityMappingItem(
            placeholder=placeholder,
            entity_type=_infer_semantic_type(placeholder),
            occurrences=count,
        )
        for placeholder, count in sorted(placeholder_counts.items())
    ]

    return StructuredDocumentResponse(
        document_id=document.id,
        doc_type=document.doc_type,
        status=document.status.value,
        original_filename=document.original_filename,
        entity_summary=entity_summary,
        entity_tags=entity_tags,
        anonymized_text=anonymized_text if include_text else None,
        text_length=len(anonymized_text) if anonymized_text else 0,
        detections_count=len(detections),
        anonymization_method=None,
        created_at=document.created_at,
    )


@router.post(
    "/{document_id}/validate",
    status_code=status.HTTP_200_OK,
    summary="Valider et figer la version anonymisée finale",
)
async def validate_document(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
    background_tasks: BackgroundTasks,
    args: ValidateDocumentRequest = Body(default_factory=ValidateDocumentRequest),
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

    final_text = args.final_text if args.final_text is not None else preview_version.content_text
    final_text = postgres_safe_text(final_text)

    await db.execute(
        delete(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.FINAL_ANONYMIZED,
        )
    )
    db.add(DocumentVersion(
        document_id=document.id,
        version_type=DocumentVersionType.FINAL_ANONYMIZED,
        content_text=final_text,
    ))
    await db.commit()

    # --- Auto-Golden Webhook ---
    if args.corrected_data and args.doc_type:
        try:
            import os
            import json
            from pathlib import Path
            from datetime import datetime, UTC
            
            root_dir = Path(os.getcwd())
            draft_dir = root_dir / "golden" / "cases" / "draft" / f"{args.doc_type}_auto_{document.id}"
            draft_dir.mkdir(parents=True, exist_ok=True)
            
            # Save input text
            (draft_dir / "input.txt").write_text(final_text, encoding="utf-8")
            
            # Save expected minimal JSON
            expected_data = {
                "doc_type": args.doc_type,
                "extractor_name": f"extractor_{args.doc_type}",
                "critical_fields": args.corrected_data,
                "quality": {
                    "critical_missing_fields": [],
                    "quality_flags_must_include": [],
                    "quality_flags_must_exclude": ["critical_fields_missing"],
                    "needs_review": False,
                    "ready_for_ai": True
                }
            }
            (draft_dir / "expected.min.json").write_text(json.dumps(expected_data, indent=2), encoding="utf-8")
            
            # Save meta.json
            meta_data = {
                "active": False,
                "description": "Auto-generated from user manual correction in UI",
                "source_filename": document.original_filename,
                "requested_doc_type": args.doc_type,
                "created_at": datetime.now(UTC).isoformat(),
                "created_by": str(current_user.id)
            }
            (draft_dir / "meta.json").write_text(json.dumps(meta_data, indent=2), encoding="utf-8")
            
            logger.info("auto_golden_draft_created", document_id=str(document.id), doc_type=args.doc_type)
        except Exception as exc:
            logger.error("auto_golden_draft_failed", error=str(exc))
    # ---------------------------

    from app.config import get_settings
    from app.services.webhook_notify import notify_document_validated
    settings = get_settings()
    wh_url = (settings.WEBHOOK_ON_VALIDATE_URL or "").strip()
    if wh_url:
        background_tasks.add_task(
            notify_document_validated,
            document_id=str(document.id),
            url=wh_url,
            secret=settings.WEBHOOK_ON_VALIDATE_SECRET or "",
        )

    return {"status": "validated", "document_id": str(document.id)}


@router.post(
    "/{document_id}/approve-export",
    status_code=status.HTTP_200_OK,
    summary="Validation humaine pour autoriser l'export (risque élevé)",
)
async def approve_export(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    document = await _get_user_document_or_404(db, document_id, current_user.id)

    try:
        from app.models.pseudonym_mapping import PseudonymMapping
        result = await db.execute(
            select(PseudonymMapping)
            .where(PseudonymMapping.document_id == document.id)
            .order_by(PseudonymMapping.created_at.desc())
        )
        mapping = result.scalar_one_or_none()
        if not mapping:
            raise http_404("Aucun mapping trouvé. Lancez /anonymize d'abord.")
        if mapping.risk_level == "critical":
            raise http_400("Impossible d'approuver : risque critique.")

        mapping.human_validated = True
        mapping.validated_by_user_id = current_user.id
        mapping.validated_at = datetime.now(UTC)
        await db.commit()
    except Exception as exc:
        if hasattr(exc, "status_code"):
            raise
        logger.warning("approve_export_failed", error=str(exc))
        await db.rollback()
        raise http_500("Impossible d'approuver l'export pour le moment.") from exc

    return {"status": "approved", "document_id": str(document.id)}
