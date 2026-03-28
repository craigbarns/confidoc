"""ConfiDoc Backend — Documents endpoints."""

import asyncio
import uuid
import hashlib
import re
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace

from fastapi import APIRouter, BackgroundTasks, Body, Query, status
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from sqlalchemy import delete, desc, func, select, update

from app.api.deps import CurrentUser, DbSession
from app.core.database import async_session_factory
from app.core.exceptions import http_400, http_404, http_500
from app.core.logging import get_logger
from app.core.text_sanitize import postgres_safe_text
from app.models.document import Document, DocumentStatus
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.models.entity_detection import EntityDetection
from app.models.llm_request import LlmRequest
from app.schemas.document import (
    AnonymizeResponse,
    DetectionResponse,
    DocumentPreviewResponse,
    DocumentResponse,
    ValidateDocumentRequest,
)
from app.services.document_processing_service import (
    build_anonymization_preview,
    build_extraction_ocr,
    build_anonymization_llm,
)
from app.services.anonymization_service import (
    anonymize_text,
    classify_document_type,
    extract_text_from_file,
)
from app.config import get_settings
from app.services.webhook_notify import notify_document_validated
from app.services.pdf_redaction_service import redact_pdf_bytes
from app.services.storage_service import read_bytes

router = APIRouter()
logger = get_logger(__name__)
def _normalize_client_name(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return re.sub(r"\s+", " ", raw).lower()




# ──────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────


def _sha256_text(text: str | None) -> str | None:
    if not text:
        return None
    return hashlib.sha256(text.encode()).hexdigest()


def _detection_item_to_response(item: dict) -> DetectionResponse:
    return DetectionResponse(
        entity_type=item.get("entity_type", "UNKNOWN"),
        start_index=item.get("start_index", 0),
        end_index=item.get("end_index", 0),
        replacement=item.get("replacement", ""),
        confidence=item.get("confidence", 0.0),
        value_excerpt=item.get("value_excerpt", ""),
    )


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
            Document.is_deleted.is_(False),
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise http_404("Document introuvable")
    return document


def _read_file_or_404(document: Document) -> bytes:
    try:
        return read_bytes(document.storage_backend, document.storage_key)
    except Exception as exc:
        logger.warning("storage_read_fallback", doc_id=str(document.id), error=str(exc))

    if document.raw_content:
        return document.raw_content

    raise http_404(
        "Fichier source introuvable. Ré-uploadez le document."
    )


async def _get_or_create_final_version(
    db: DbSession, document: Document
) -> DocumentVersion:
    result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.FINAL_ANONYMIZED,
        )
    )
    final = result.scalar_one_or_none()
    if final:
        return final

    preview_result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.PREVIEW_ANONYMIZED,
        )
    )
    preview = preview_result.scalar_one_or_none()
    if not preview:
        raise http_404(
            "Aucune version anonymisée disponible. Lancez d'abord l'anonymisation."
        )

    final = DocumentVersion(
        document_id=document.id,
        version_type=DocumentVersionType.FINAL_ANONYMIZED,
        content_text=postgres_safe_text(preview.content_text),
    )
    db.add(final)
    await db.flush()
    return final


async def _get_original_text(db: DbSession, document: Document) -> str:
    result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.ORIGINAL_TEXT,
        )
    )
    version = result.scalar_one_or_none()
    if version and version.content_text:
        return version.content_text

    file_content = _read_file_or_404(document)
    return extract_text_from_file(file_content, document.extension) or ""


async def _get_anonymized_text(db: DbSession, document: Document) -> str:
    """Get best anonymized text (final > preview)."""
    for version_type in (
        DocumentVersionType.FINAL_ANONYMIZED,
        DocumentVersionType.PREVIEW_ANONYMIZED,
    ):
        result = await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.version_type == version_type,
            )
        )
        version = result.scalar_one_or_none()
        if version and version.content_text:
            return version.content_text
    return ""


# ──────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ──────────────────────────────────────────────────────────────────────


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
    offset: int = Query(default=0, ge=0),
    include_deleted: bool = Query(default=False, description="Inclure les documents supprimés"),
    client_name: str = Query(default="", description="Filtrer par nom client (tag)"),
    q: str = Query(default="", description="Recherche texte sur le nom du document"),
    status_filter: str = Query(default="", description="Filtrer par statut (uploaded|processing|ready|failed|deleted)"),
) -> list[Document]:
    """Liste les documents de l'utilisateur connecté."""
    logger.info(
        "list_documents",
        user_id=str(current_user.id),
        limit=limit,
        offset=offset,
        include_deleted=include_deleted,
        client_name=client_name,
        q=q,
        status_filter=status_filter,
    )
    
    client_norm = _normalize_client_name(client_name)
    q_norm = _normalize_client_name(q)
    status_norm = _normalize_client_name(status_filter)

    # Requête de base
    query = select(Document).where(Document.uploaded_by_user_id == current_user.id)
    
    # Filtrer les supprimés sauf si demandé
    if not include_deleted:
        query = query.where(Document.is_deleted.is_(False))
    # Récupération complète utilisateur, puis filtre client robuste (insensible casse/espaces)
    # et pagination applicative pour fiabilité métier.
    result = await db.execute(query.order_by(desc(Document.created_at)))
    documents_all = list(result.scalars().all())
    if client_norm:
        filtered: list[Document] = []
        for d in documents_all:
            tags = list(getattr(d, "tags", []) or [])
            if not tags:
                continue
            tag_norm = _normalize_client_name(tags[0])
            if client_norm in tag_norm:
                filtered.append(d)
        documents_all = filtered
    if q_norm:
        documents_all = [
            d for d in documents_all
            if q_norm in _normalize_client_name(getattr(d, "original_filename", ""))
        ]
    if status_norm:
        if status_norm == "deleted":
            documents_all = [d for d in documents_all if bool(getattr(d, "is_deleted", False))]
        else:
            documents_all = [
                d for d in documents_all
                if _normalize_client_name(getattr(d, "status", "").value if hasattr(getattr(d, "status", ""), "value") else str(getattr(d, "status", ""))) == status_norm
            ]

    documents = documents_all[offset : offset + limit]
    logger.info("list_documents_result", user_id=str(current_user.id), count=len(documents))
    return documents


@router.get(
    "/clients",
    response_model=list[str],
    status_code=status.HTTP_200_OK,
    summary="Lister les clients connus (tags documents)",
)
async def list_clients(
    current_user: CurrentUser,
    db: DbSession,
    include_deleted: bool = Query(default=False, description="Inclure les documents supprimés"),
) -> list[str]:
    query = select(Document).where(Document.uploaded_by_user_id == current_user.id)
    if not include_deleted:
        query = query.where(Document.is_deleted.is_(False))
    result = await db.execute(query.order_by(desc(Document.created_at)))
    docs = list(result.scalars().all())
    seen: set[str] = set()
    out: list[str] = []
    for d in docs:
        tags = list(getattr(d, "tags", []) or [])
        if not tags:
            continue
        label = re.sub(r"\s+", " ", str(tags[0]).strip())
        key = _normalize_client_name(label)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(label)
    return sorted(out, key=lambda x: x.lower())


# ═══════════════════════════════════════════════════════════════════════════════
# CORBEILLE (TRASH) - Gestion des documents supprimés
# ⚠ IMPORTANT: ces routes statiques DOIVENT être déclarées AVANT /{document_id}
# sinon FastAPI traite "trash" comme un document_id → 404
# ═══════════════════════════════════════════════════════════════════════════════


@router.get(
    "/trash/list",
    status_code=status.HTTP_200_OK,
    summary="Liste des documents supprimés (corbeille)",
)
async def list_trash(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Liste les documents mis à la corbeille par l'utilisateur."""
    result = await db.execute(
        select(Document)
        .where(
            Document.uploaded_by_user_id == current_user.id,
            Document.is_deleted.is_(True),
        )
        .order_by(desc(Document.deleted_at))
        .offset(offset)
        .limit(limit)
    )
    docs = result.scalars().all()
    
    # Compter le total
    count_result = await db.execute(
        select(func.count()).select_from(Document).where(
            Document.uploaded_by_user_id == current_user.id,
            Document.is_deleted.is_(True),
        )
    )
    total = count_result.scalar()
    
    return {
        "documents": [
            {
                "id": str(d.id),
                "original_filename": d.original_filename,
                "size_bytes": d.size_bytes,
                "content_type": d.content_type,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "deleted_at": d.deleted_at.isoformat() if d.deleted_at else None,
                "doc_type": d.doc_type,
                "status": d.status.value if d.status else None,
            }
            for d in docs
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ──────────────────────────────────────────────────────────────────────
# ROUTES PARAMÉTRÉES /{document_id} — TOUJOURS EN DERNIER
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Récupérer un document",
)
async def get_document(
    document_id: str, current_user: CurrentUser, db: DbSession
) -> Document:
    return await _get_user_document_or_404(db, document_id, current_user.id)


async def _run_anonymize_background(doc_id: str, file_content: bytes, profile: str, document_type: str) -> None:
    """Run OCR + LLM anonymization in background with its own DB session."""
    try:
        async with async_session_factory() as db:
            result = await db.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
            document = result.scalar_one_or_none()
            if not document:
                return
            # Étape 1: OCR
            original_text, _ = await build_extraction_ocr(db, document, file_content)
            # Étape 2: Anonymisation
            await build_anonymization_llm(db, document, original_text)
            await db.commit()
            logger.info("background_process_complete", doc_id=doc_id)
    except Exception as exc:
        logger.error("background_process_failed", doc_id=doc_id, error=str(exc))
        try:
            async with async_session_factory() as db:
                await db.execute(
                    update(Document)
                    .where(Document.id == uuid.UUID(doc_id))
                    .values(status=DocumentStatus.UPLOADED)
                )
                await db.commit()
        except Exception:
            pass


@router.post(
    "/{document_id}/extract",
    status_code=status.HTTP_200_OK,
    summary="Étape 1: Extraire le texte via Mistral OCR",
)
async def extract_document(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Extraction OCR du document. Retourne le texte brut COMPLET."""
    document = await _get_user_document_or_404(db, document_id, current_user.id)
    file_content = _read_file_or_404(document)
    
    # Extraction OCR synchrone (peut prendre 10-30s)
    original_text, meta = await build_extraction_ocr(db, document, file_content)
    await db.commit()
    
    return {
        "document_id": str(document.id),
        "status": "extracted",
        "text": original_text,  # ← TOUT le texte, pas tronqué
        "text_length": len(original_text),
        "pages": meta.get("pages", 0),
        "model": meta.get("model", "unknown"),
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
    """Retourne le texte OCR déjà extrait."""
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
        "text": original_version.content_text,  # ← TOUT le texte
        "text_length": len(original_version.content_text),
        "extraction_date": original_version.created_at.isoformat() if original_version.created_at else None,
    }


@router.post(
    "/{document_id}/anonymize",
    status_code=status.HTTP_200_OK,
    summary="Étape 2: Anonymiser le texte extrait",
)
async def anonymize_document(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
    auto_extract: bool = Query(default=True, description="Lance l'OCR automatiquement si texte non extrait"),
    use_llm: bool = Query(default=False, description="Utilise Mistral LLM (sinon dictionnaire)"),
    profile: str = Query(default="moderate", description="Profil d'anonymisation: 'moderate' (dictionnaire) ou 'strict' (LLM)"),
) -> dict:
    """Anonymisation du texte par dictionnaire (défaut) ou LLM."""
    document = await _get_user_document_or_404(db, document_id, current_user.id)
    
    # Récupère le texte OCR précédemment extrait
    result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.ORIGINAL_TEXT,
        )
    )
    original_version = result.scalar_one_or_none()
    
    original_text = None
    extracted_on_demand = False
    
    if original_version and original_version.content_text is not None:
        original_text = original_version.content_text
    elif auto_extract:
        # 🔥 AUTO-EXTRACT: Pas de texte ? On lance l'OCR automatiquement !
        logger.info("auto_extract_triggered", doc_id=document_id)
        file_content = _read_file_or_404(document)
        original_text, _ = await build_extraction_ocr(db, document, file_content)
        extracted_on_demand = True
        await db.commit()  # Commit important ici
    
    if original_text is None:
        raise http_400("Texte non extrait. Lancez /extract d'abord ou utilisez auto_extract=true.")
    
    if len(original_text.strip()) == 0:
        raise http_400("Document vide ou illisible. Vérifiez que le fichier contient du texte extractible.")
    
    # Anonymisation (dictionnaire par défaut, LLM si demandé ou profil strict)
    preview_text, detections, meta = await build_anonymization_llm(
        db, document, original_text, use_llm=use_llm, profile=profile
    )
    await db.commit()
    
    return {
        "document_id": str(document.id),
        "status": "anonymized",
        "preview_text": preview_text,  # ← TOUT le texte anonymisé
        "detections_count": len(detections),
        "method": meta.get("method", "llm"),
        "auto_extracted": extracted_on_demand,
    }


# Endpoint legacy pour traitement complet en background
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
    """Pipeline complet en background (pour compatibilité)."""
    document = await _get_user_document_or_404(db, document_id, current_user.id)
    file_content = _read_file_or_404(document)
    document.status = DocumentStatus.PROCESSING
    await db.commit()
    asyncio.create_task(
        _run_anonymize_background(str(document.id), file_content, profile, document_type)
    )
    return {"document_id": str(document.id), "status": "processing"}


@router.get(
    "/{document_id}/status",
    status_code=status.HTTP_200_OK,
    summary="Vérifier le statut OCR + Anonymisation",
)
async def document_status(
    document_id: str, current_user: CurrentUser, db: DbSession
) -> dict:
    """Retourne l'état complet: uploadé, extrait, anonymisé."""
    document = await _get_user_document_or_404(db, document_id, current_user.id)
    
    # Check extraction
    result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.ORIGINAL_TEXT,
        )
    )
    original = result.scalar_one_or_none()
    
    # Check anonymisation
    result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_type == DocumentVersionType.PREVIEW_ANONYMIZED,
        )
    )
    preview = result.scalar_one_or_none()
    
    # Count detections
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

    count_result = await db.execute(
        select(func.count()).select_from(EntityDetection).where(
            EntityDetection.document_id == document.id
        )
    )
    detections_count = count_result.scalar() or 0

    return DocumentPreviewResponse(
        document_id=document.id,
        status=document.status.value,
        preview_text=preview_version.content_text,
        detections_count=detections_count,
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
    db.add(
        DocumentVersion(
            document_id=document.id,
            version_type=DocumentVersionType.FINAL_ANONYMIZED,
            content_text=final_text,
        )
    )
    await db.commit()

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


@router.get(
    "/{document_id}/export",
    response_class=PlainTextResponse,
    status_code=status.HTTP_200_OK,
    summary="Exporter le texte anonymisé",
)
async def export_document(
    document_id: str, current_user: CurrentUser, db: DbSession
) -> PlainTextResponse:
    document = await _get_user_document_or_404(db, document_id, current_user.id)
    final = await _get_or_create_final_version(db, document)
    await db.commit()
    return PlainTextResponse(final.content_text)


@router.get(
    "/{document_id}/export-pdf",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
    summary="Exporter le PDF avec données visuellement masquées",
)
async def export_redacted_pdf(
    document_id: str, current_user: CurrentUser, db: DbSession
) -> StreamingResponse:
    document = await _get_user_document_or_404(db, document_id, current_user.id)

    if document.extension.lower() != "pdf":
        raise http_400("Export PDF redacté disponible uniquement pour les fichiers PDF")

    detections_result = await db.execute(
        select(EntityDetection).where(EntityDetection.document_id == document.id)
    )
    detections = list(detections_result.scalars().all())

    if not detections:
        source_text = await _get_anonymized_text(db, document)
        if source_text:
            effective_type = classify_document_type(source_text, document.original_filename)
            _anon_text, regenerated = anonymize_text(
                source_text, profile="strict", document_type=effective_type
            )
            detections = [
                SimpleNamespace(value_excerpt=item.get("value_excerpt", ""))
                for item in regenerated
                if item.get("value_excerpt")
            ]
        if not detections:
            raise http_404("Aucune détection disponible. Lancez /anonymize d'abord.")

    original_bytes = _read_file_or_404(document)
    sensitive_values = [item.value_excerpt for item in detections if item.value_excerpt]

    try:
        loop = asyncio.get_running_loop()
        redacted_bytes = await loop.run_in_executor(
            None, redact_pdf_bytes, original_bytes, sensitive_values
        )
    except Exception as exc:
        logger.error("pdf_redaction_failed", doc_id=str(document.id), error=str(exc))
        raise http_400("Impossible de générer le PDF redacté.")

    headers = {"Content-Disposition": f'attachment; filename="redacted_{document.original_filename}"'}
    return StreamingResponse(BytesIO(redacted_bytes), media_type="application/pdf", headers=headers)


@router.delete(
    "/all",
    status_code=status.HTTP_200_OK,
    summary="Supprimer tous mes documents",
)
async def delete_all_my_documents(
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    result = await db.execute(
        select(Document).where(
            Document.uploaded_by_user_id == current_user.id,
            Document.is_deleted.is_(False),
        )
    )
    docs = list(result.scalars().all())
    now = datetime.now(timezone.utc)
    for doc in docs:
        doc.is_deleted = True
        doc.deleted_at = now
    await db.commit()
    return {"deleted_count": len(docs)}


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un document (soft delete - met à la corbeille)",
)
async def delete_document(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    document = await _get_user_document_or_404(db, document_id, current_user.id)
    document.is_deleted = True
    document.deleted_at = datetime.now(timezone.utc)
    await db.commit()


@router.post(
    "/{document_id}/restore",
    status_code=status.HTTP_200_OK,
    summary="Restaurer un document de la corbeille",
)
async def restore_document(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Restaure un document supprimé (le sort de la corbeille)."""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError as exc:
        raise http_404("Document introuvable") from exc
    
    result = await db.execute(
        select(Document).where(
            Document.id == doc_uuid,
            Document.uploaded_by_user_id == current_user.id,
            Document.is_deleted.is_(True),
        )
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise http_404("Document non trouvé dans la corbeille")
    
    document.is_deleted = False
    document.deleted_at = None
    await db.commit()
    
    return {
        "message": "Document restauré avec succès",
        "document_id": str(document.id),
        "original_filename": document.original_filename,
    }


@router.delete(
    "/{document_id}/permanent",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Suppression définitive d'un document",
)
async def permanent_delete_document(
    document_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Supprime définitivement un document (ne peut pas être annulé)."""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError as exc:
        raise http_404("Document introuvable") from exc
    
    result = await db.execute(
        select(Document).where(
            Document.id == doc_uuid,
            Document.uploaded_by_user_id == current_user.id,
        )
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise http_404("Document introuvable")
    
    # Suppression définitive (hard delete)
    await db.execute(
        delete(Document).where(Document.id == doc_uuid)
    )
    await db.commit()
