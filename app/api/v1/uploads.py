"""ConfiDoc Backend — Upload Endpoints (v2) with Streaming."""

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.core.exceptions import http_400, http_413
from app.core.logging import get_logger
from app.core.sandbox import SandboxError, scan_file_for_malware
from app.models.document import Document, DocumentStatus
from app.models.membership import Membership
from app.rate_limit import limiter
from app.services.anonymization_service import HAS_OCR
from app.services.storage_service import store_file
from app.workers.tasks import (
    anonymize_document_task,
    celery_workers_available,
    run_anonymize_document_inline,
)

router = APIRouter()
settings = get_settings()
logger = get_logger(__name__)

# Maximum number of files in a single batch upload
MAX_BATCH_SIZE = 20
CHUNK_SIZE = 8192  # 8KB
AnonymizationProfile = Literal[
    "moderate",
    "strict",
    "dataset_strict",
    "dataset_accounting",
    "dataset_accounting_pseudo",
]


def _normalize_client_name(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return re.sub(r"\s+", " ", raw)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Uploader un document (Streaming)",
)
@limiter.limit(settings.RATE_LIMIT_UPLOAD)
async def upload_document(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    auto_anonymize: bool = Query(default=True),
    profile: AnonymizationProfile = Query(default="moderate"),
    document_type: str = Query(default="auto"),
    client_name: str = Query(default=""),
) -> dict:
    """Upload un document via streaming vers un fichier temporaire pour éviter l'OOM."""
    filename = file.filename or ""
    if "." not in filename:
        raise http_400("Nom de fichier invalide")

    extension = filename.rsplit(".", 1)[1].lower()
    if extension not in settings.ALLOWED_EXTENSIONS:
        raise http_400(
            f"Extension non autorisée. Autorisées: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )

    # SEC-014 Sandbox/Antivirus could be triggered here

    # Streaming save to temp file
    temp_fd, temp_path = tempfile.mkstemp(suffix=f".{extension}")
    sha256_hash = hashlib.sha256()
    size = 0

    try:
        with os.fdopen(temp_fd, "wb") as tmp:
            while chunk := await file.read(CHUNK_SIZE):
                size += len(chunk)
                if size > settings.max_upload_size_bytes:
                    raise http_413(
                        f"Fichier trop volumineux. Maximum: {settings.MAX_UPLOAD_SIZE_MB} MB"
                    )
                tmp.write(chunk)
                sha256_hash.update(chunk)

        if size == 0:
            raise http_400("Fichier vide")

        # SEC-014: Sandbox antivirus / MIME verification
        try:
            scan_file_for_malware(temp_path, extension)
        except SandboxError as scan_err:
            raise http_400(f"Fichier rejeté : {str(scan_err)}")

        return await _upload_document_body(
            db=db,
            current_user=current_user,
            file=file,
            file_path=Path(temp_path),
            filename=filename,
            extension=extension,
            size=size,
            sha256=sha256_hash.hexdigest(),
            auto_anonymize=auto_anonymize,
            profile=profile,
            document_type=document_type,
            client_name=client_name,
            background_tasks=background_tasks,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("upload_document_failed", filename=filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors du traitement du document. Veuillez réessayer.",
        ) from exc
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


async def _upload_document_body(
    *,
    db: DbSession,
    current_user: CurrentUser,
    file: UploadFile,
    file_path: Path,
    filename: str,
    extension: str,
    size: int,
    sha256: str,
    auto_anonymize: bool,
    profile: str,
    document_type: str,
    client_name: str = "",
    background_tasks: BackgroundTasks | None = None,
) -> dict:
    """Corps métier upload (utilisant le fichier temporaire)."""
    normalized_client_name = _normalize_client_name(client_name)
    if not normalized_client_name:
        raise http_400("Le champ client_name est obligatoire")

    # Store to external storage
    try:
        storage_backend, storage_key = store_file(file_path=file_path, extension=extension)
    except Exception as exc:
        logger.warning("external_storage_failed", error=str(exc))
        storage_backend = "database"
        from uuid import uuid4
        storage_key = f"db://{sha256}.{uuid4().hex}.{extension}"

    membership_res = await db.execute(
        select(Membership).where(
            Membership.user_id == current_user.id,
            Membership.is_active.is_(True),
        )
    )
    membership = membership_res.scalar_one_or_none()
    org_id = membership.org_id if membership else None
    uploaded_by_snapshot = str(current_user.id)

    document = Document(
        org_id=org_id,
        uploaded_by_user_id=current_user.id,
        original_filename=filename,
        content_type=file.content_type or "application/octet-stream",
        extension=extension,
        size_bytes=size,
        sha256=sha256,
        storage_backend=storage_backend,
        storage_key=storage_key,
        status=DocumentStatus.UPLOADED,
        raw_content=file_path.read_bytes() if storage_backend == "database" else None,
        tags=[normalized_client_name],
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    logger.info(
        "document_uploaded",
        doc_id=str(document.id),
        filename=filename,
        size=size,
        backend=storage_backend,
    )

    processing: dict = {
        "auto_anonymize": auto_anonymize,
        "profile": profile,
        "document_type": document_type,
        "ocr_available": HAS_OCR,
    }

    if auto_anonymize:
        doc_id = str(document.id)
        if celery_workers_available(queue="nlp"):
            try:
                anonymize_document_task.delay(
                    doc_id=doc_id,
                    profile=profile,
                    document_type=document_type,
                )
                processing.update({"status": "processing", "background_processing": "celery"})
            except Exception as exc:
                logger.warning(
                    "celery_enqueue_failed_using_inline_background",
                    doc_id=doc_id,
                    error=str(exc),
                )
                if background_tasks is not None:
                    background_tasks.add_task(
                        run_anonymize_document_inline,
                        doc_id=doc_id,
                        profile=profile,
                        document_type=document_type,
                    )
                    processing.update({"status": "processing", "background_processing": "api"})
                else:
                    processing.update({"status": "uploaded", "background_processing": False})
        elif background_tasks is not None:
            logger.warning("celery_workers_unavailable_using_inline_background", doc_id=doc_id)
            background_tasks.add_task(
                run_anonymize_document_inline,
                doc_id=doc_id,
                profile=profile,
                document_type=document_type,
            )
            processing.update({"status": "processing", "background_processing": "api"})
        else:
            processing.update({"status": "uploaded", "background_processing": False})

    return {
        "status": document.status.value,
        "document_id": str(document.id),
        "storage_backend": document.storage_backend,
        "sha256": document.sha256,
        "original_filename": filename,
        "content_type": file.content_type,
        "size_bytes": size,
        "uploaded_by": uploaded_by_snapshot,
        "client_name": normalized_client_name,
        "processing": processing,
    }


@router.post(
    "/batch",
    status_code=status.HTTP_200_OK,
    summary="Upload et traiter plusieurs documents en batch (Streaming)",
)
@limiter.limit("10/minute")
async def upload_batch(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    auto_anonymize: bool = Query(default=True),
    profile: AnonymizationProfile = Query(default="moderate"),
    document_type: str = Query(default="auto"),
    client_name: str = Query(default=""),
) -> dict:
    """Upload multiple documents at once via streaming."""
    if len(files) > MAX_BATCH_SIZE:
        raise http_400(f"Maximum {MAX_BATCH_SIZE} fichiers par batch. Reçu: {len(files)}.")
    if not files:
        raise http_400("Aucun fichier fourni.")

    results: list[dict] = []
    succeeded = 0
    failed = 0

    for file in files:
        filename = file.filename or ""
        temp_path = None
        try:
            if "." not in filename:
                raise ValueError("Nom de fichier invalide (pas d'extension)")

            extension = filename.rsplit(".", 1)[1].lower()
            if extension not in settings.ALLOWED_EXTENSIONS:
                raise ValueError(f"Extension .{extension} non autorisée")

            # Stream to temp file
            temp_fd, temp_path = tempfile.mkstemp(suffix=f".{extension}")
            sha256_hash = hashlib.sha256()
            size = 0

            with os.fdopen(temp_fd, "wb") as tmp:
                while chunk := await file.read(CHUNK_SIZE):
                    size += len(chunk)
                    if size > settings.max_upload_size_bytes:
                        raise ValueError(
                            f"Fichier trop volumineux. Maximum: {settings.MAX_UPLOAD_SIZE_MB} MB"
                        )
                    tmp.write(chunk)
                    sha256_hash.update(chunk)

            if size == 0:
                raise ValueError("Fichier vide")

            # SEC-014: Sandbox antivirus / MIME verification
            try:
                scan_file_for_malware(temp_path, extension)
            except SandboxError as scan_err:
                raise ValueError(f"Fichier rejeté : {str(scan_err)}")

            result = await _upload_document_body(
                db=db,
                current_user=current_user,
                file=file,
                file_path=Path(temp_path),
                filename=filename,
                extension=extension,
                size=size,
                sha256=sha256_hash.hexdigest(),
                auto_anonymize=auto_anonymize,
                profile=profile,
                document_type=document_type,
                client_name=client_name,
                background_tasks=background_tasks,
            )
            results.append(result)
            succeeded += 1

        except Exception as exc:
            try:
                await db.rollback()
            except Exception:
                pass
            logger.warning("batch_upload_file_failed", filename=filename, error=str(exc))
            results.append({
                "status": "error",
                "original_filename": filename,
                "error": str(exc)[:500],
            })
            failed += 1
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

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
