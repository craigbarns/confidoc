"""ConfiDoc Backend — Upload Endpoints (v2)."""

import hashlib
from typing import Literal

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.core.exceptions import http_400, http_413
from app.core.logging import get_logger
from app.models.document import Document, DocumentStatus
from app.models.membership import Membership
from app.rate_limit import limiter
from app.services.anonymization_service import HAS_OCR
from app.services.document_processing_service import build_anonymization_preview
from app.services.storage_service import store_bytes

router = APIRouter()
settings = get_settings()
logger = get_logger(__name__)

# Maximum number of files in a single batch upload
MAX_BATCH_SIZE = 20


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Uploader un document",
)
@limiter.limit(settings.RATE_LIMIT_UPLOAD)
async def upload_document(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    auto_anonymize: bool = Query(default=True),
    profile: Literal["moderate", "strict", "dataset_strict", "dataset_accounting", "dataset_accounting_pseudo"] = Query(default="dataset_accounting_pseudo"),
    document_type: str = Query(default="auto"),
    client_name: str = Query(default=""),
) -> dict:
    """Upload un document, le stocke et persiste son enregistrement en base."""
    filename = file.filename or ""
    if "." not in filename:
        raise http_400("Nom de fichier invalide")

    extension = filename.rsplit(".", 1)[1].lower()
    if extension not in settings.ALLOWED_EXTENSIONS:
        raise http_400(
            f"Extension non autorisée. Autorisées: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )

    content = await file.read()
    if not content:
        raise http_400("Fichier vide")

    if len(content) > settings.max_upload_size_bytes:
        raise http_413(
            f"Fichier trop volumineux. Maximum: {settings.MAX_UPLOAD_SIZE_MB} MB"
        )

    try:
        return await _upload_document_body(
            db=db,
            current_user=current_user,
            file=file,
            content=content,
            filename=filename,
            extension=extension,
            auto_anonymize=auto_anonymize,
            profile=profile,
            document_type=document_type,
            client_name=client_name,
        )
    except HTTPException:
        raise
    except Exception as exc:
        try:
            await db.rollback()
        except Exception:
            pass
        logger.exception("upload_document_failed", filename=filename)
        # JSON explicite pour curl / smoke (sinon « Internal Server Error » vide)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors du traitement du document. Veuillez réessayer.",
        ) from exc


async def _upload_document_body(
    *,
    db: DbSession,
    current_user: CurrentUser,
    file: UploadFile,
    content: bytes,
    filename: str,
    extension: str,
    auto_anonymize: bool,
    profile: str,
    document_type: str,
    client_name: str = "",
) -> dict:
    """Corps métier upload (isolé pour try/except global)."""
    # Store to external storage (MinIO or local /tmp)
    try:
        storage_backend, storage_key = store_bytes(content=content, extension=extension)
    except Exception as exc:
        logger.warning("external_storage_failed", error=str(exc))
        storage_backend = "database"
        from uuid import uuid4

        storage_key = f"db://{hashlib.sha256(content).hexdigest()}.{uuid4().hex}.{extension}"

    sha256 = hashlib.sha256(content).hexdigest()

    membership_res = await db.execute(
        select(Membership).where(
            Membership.user_id == current_user.id,
            Membership.is_active.is_(True),
        )
    )
    membership = membership_res.scalar_one_or_none()
    org_id = membership.org_id if membership else None

    # Capturer avant tout commit : après commit, User peut être expiré (expire_on_commit)
    # et accéder à current_user.id déclenche un lazy-load → MissingGreenlet en async.
    uploaded_by_snapshot = str(current_user.id)

    document = Document(
        org_id=org_id,
        uploaded_by_user_id=current_user.id,
        original_filename=filename,
        content_type=file.content_type or "application/octet-stream",
        extension=extension,
        size_bytes=len(content),
        sha256=sha256,
        storage_backend=storage_backend,
        storage_key=storage_key,
        status=DocumentStatus.UPLOADED,
        raw_content=content,
        tags=[client_name.strip()] if client_name.strip() else [],
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    logger.info(
        "document_uploaded",
        doc_id=str(document.id),
        filename=filename,
        size=len(content),
        backend=storage_backend,
    )

    processing: dict = {
        "auto_anonymize": auto_anonymize,
        "profile": profile,
        "document_type": document_type,
        "ocr_available": HAS_OCR,
    }

    if auto_anonymize:
        try:
            preview_text, detections, effective_type, extraction_meta = (
                await build_anonymization_preview(
                db=db,
                document=document,
                file_content=content,
                profile=profile,
                document_type=document_type,
            )
            )
            await db.commit()
            # Après commit, Document peut être expiré : recharger avant lecture des attributs.
            await db.refresh(document)
            excerpt = (preview_text if isinstance(preview_text, str) else "")[:300]
            processing.update({
                "status": "ready",
                "effective_type": effective_type,
                "detections_count": len(detections or []),
                "preview_excerpt": excerpt,
                "extraction_meta": extraction_meta,
            })
        except Exception as exc:
            await db.rollback()
            try:
                await db.refresh(document)
            except Exception:
                pass
            logger.error("auto_anonymize_failed", doc_id=str(document.id), error=str(exc))
            processing.update({"status": "error", "error": str(exc)[:500]})

    return {
        "status": document.status.value,
        "document_id": str(document.id),
        "storage_backend": document.storage_backend,
        "sha256": document.sha256,
        "original_filename": filename,
        "content_type": file.content_type,
        "size_bytes": len(content),
        "uploaded_by": uploaded_by_snapshot,
        "client_name": client_name.strip() or None,
        "processing": processing,
    }


@router.post(
    "/batch",
    status_code=status.HTTP_200_OK,
    summary="Upload et traiter plusieurs documents en batch",
)
@limiter.limit("10/minute")
async def upload_batch(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
    files: list[UploadFile] = File(...),
    auto_anonymize: bool = Query(default=True),
    profile: Literal[
        "moderate", "strict", "dataset_strict",
        "dataset_accounting", "dataset_accounting_pseudo",
    ] = Query(default="dataset_accounting_pseudo"),
    document_type: str = Query(default="auto"),
) -> dict:
    """Upload multiple documents at once (up to 20).

    Each file is validated and processed individually. Failed files do not
    block successful ones — the response includes per-file status.
    """
    if len(files) > MAX_BATCH_SIZE:
        raise http_400(
            f"Maximum {MAX_BATCH_SIZE} fichiers par batch. "
            f"Reçu: {len(files)}."
        )
    if not files:
        raise http_400("Aucun fichier fourni.")

    results: list[dict] = []
    succeeded = 0
    failed = 0

    for file in files:
        filename = file.filename or ""
        try:
            if "." not in filename:
                raise ValueError("Nom de fichier invalide (pas d'extension)")

            extension = filename.rsplit(".", 1)[1].lower()
            if extension not in settings.ALLOWED_EXTENSIONS:
                raise ValueError(
                    f"Extension .{extension} non autorisée"
                )

            content = await file.read()
            if not content:
                raise ValueError("Fichier vide")

            if len(content) > settings.max_upload_size_bytes:
                raise ValueError(
                    f"Fichier trop volumineux ({len(content)} bytes > {settings.max_upload_size_bytes})"
                )

            result = await _upload_document_body(
                db=db,
                current_user=current_user,
                file=file,
                content=content,
                filename=filename,
                extension=extension,
                auto_anonymize=auto_anonymize,
                profile=profile,
                document_type=document_type,
            )
            results.append(result)
            succeeded += 1

        except Exception as exc:
            try:
                await db.rollback()
            except Exception:
                pass
            logger.warning(
                "batch_upload_file_failed",
                filename=filename,
                error=str(exc),
            )
            results.append({
                "status": "error",
                "original_filename": filename,
                "error": str(exc)[:500],
            })
            failed += 1

    logger.info(
        "batch_upload_complete",
        user_id=str(current_user.id),
        total=len(files),
        succeeded=succeeded,
        failed=failed,
    )

    return {
        "batch_size": len(files),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }

