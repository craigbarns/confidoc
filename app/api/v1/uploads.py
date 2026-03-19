"""ConfiDoc Backend — Upload Endpoints (v2)."""

import hashlib
from typing import Literal

from fastapi import APIRouter, File, Query, UploadFile, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.core.exceptions import http_400, http_413
from app.core.logging import get_logger
from app.models.document import Document, DocumentStatus
from app.models.membership import Membership
from app.services.document_processing_service import build_anonymization_preview
from app.services.storage_service import store_bytes

router = APIRouter()
settings = get_settings()
logger = get_logger(__name__)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Uploader un document",
)
async def upload_document(
    current_user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    auto_anonymize: bool = Query(default=True),
    profile: Literal["moderate", "strict", "dataset_strict", "dataset_accounting"] = Query(default="moderate"),
    document_type: str = Query(default="auto"),
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

    # Store to external storage (MinIO or local /tmp)
    try:
        storage_backend, storage_key = store_bytes(content=content, extension=extension)
    except Exception as exc:
        logger.warning("external_storage_failed", error=str(exc))
        storage_backend = "database"
        storage_key = f"db://{hashlib.sha256(content).hexdigest()}"

    sha256 = hashlib.sha256(content).hexdigest()

    membership_res = await db.execute(
        select(Membership).where(
            Membership.user_id == current_user.id,
            Membership.is_active.is_(True),
        )
    )
    membership = membership_res.scalar_one_or_none()
    org_id = membership.org_id if membership else None

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
        # Always store raw bytes in DB as fallback
        raw_content=content,
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
    }
    if auto_anonymize:
        try:
            preview_text, detections, effective_type = await build_anonymization_preview(
                db=db,
                document=document,
                file_content=content,
                profile=profile,
                document_type=document_type,
            )
            await db.commit()
            processing.update({
                "status": "ready",
                "effective_type": effective_type,
                "detections_count": len(detections),
                "preview_excerpt": preview_text[:300],
            })
        except Exception as exc:
            logger.error("auto_anonymize_failed", doc_id=str(document.id), error=str(exc))
            processing.update({"status": "error", "error": str(exc)[:200]})

    return {
        "status": document.status.value,
        "document_id": str(document.id),
        "storage_backend": document.storage_backend,
        "sha256": document.sha256,
        "original_filename": filename,
        "content_type": file.content_type,
        "size_bytes": len(content),
        "uploaded_by": str(current_user.id),
        "processing": processing,
    }
