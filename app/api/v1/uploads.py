"""ConfiDoc Backend — Upload Endpoints (v2)."""

import hashlib
import re
from typing import Literal
from uuid import UUID

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
from app.services.storage_service import store_bytes
from app.workers.tasks import anonymize_document_task

router = APIRouter()
settings = get_settings()
logger = get_logger(__name__)

# Maximum number of files in a single batch upload
MAX_BATCH_SIZE = 20


def _normalize_client_name(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return re.sub(r"\s+", " ", raw)


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
    profile: Literal["moderate", "strict"] = Query(default="moderate"),
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
    normalized_client_name = _normalize_client_name(client_name)
    if not normalized_client_name:
        raise http_400("Le champ client_name est obligatoire")

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
        tags=[normalized_client_name],
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
        # Run OCR + anonymization in background via Celery to survive Railway restarts
        anonymize_document_task.delay(
            doc_id=str(document.id),
            content=content,
            profile=profile,
            document_type=document_type,
        )
        processing.update({"status": "processing"})

    return {
        "status": document.status.value,
        "document_id": str(document.id),
        "storage_backend": document.storage_backend,
        "sha256": document.sha256,
        "original_filename": filename,
        "content_type": file.content_type,
        "size_bytes": len(content),
        "uploaded_by": uploaded_by_snapshot,
        "client_name": normalized_client_name,
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
    profile: Literal["moderate", "strict"] = Query(default="moderate"),
    document_type: str = Query(default="auto"),
    client_name: str = Query(default=""),
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
                client_name=client_name,
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

