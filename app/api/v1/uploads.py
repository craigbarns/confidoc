"""ConfiDoc Backend — Upload Endpoints."""

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, UploadFile, status

from app.api.deps import CurrentUser
from app.config import get_settings
from app.core.exceptions import http_400, http_413

router = APIRouter()
settings = get_settings()

UPLOAD_ROOT = Path("/tmp/confidoc_uploads")
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Uploader un document",
)
async def upload_document(
    current_user: CurrentUser,
    file: UploadFile = File(...),
) -> dict:
    """Upload un document et le stocke localement (V1 bootstrap)."""
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

    stored_name = f"{uuid4()}.{extension}"
    target_path = UPLOAD_ROOT / stored_name
    target_path.write_bytes(content)

    return {
        "status": "uploaded",
        "document_id": stored_name,
        "original_filename": filename,
        "content_type": file.content_type,
        "size_bytes": len(content),
        "uploaded_by": str(current_user.id),
    }
