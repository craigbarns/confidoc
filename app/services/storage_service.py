"""ConfiDoc Backend — Storage service (local / MinIO) — v2."""

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


def _get_minio_client():
    """Create a MinIO client instance."""
    from minio import Minio
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_USE_SSL,
    )


def store_bytes(content: bytes, extension: str) -> tuple[str, str]:
    """Store file bytes and return (storage_backend, storage_key)."""
    extension = extension.lower().strip(".")
    object_key = f"raw/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{uuid4()}.{extension}"

    if settings.STORAGE_BACKEND == "minio":
        client = _get_minio_client()
        if not client.bucket_exists(settings.MINIO_BUCKET):
            client.make_bucket(settings.MINIO_BUCKET)

        data = BytesIO(content)
        client.put_object(
            bucket_name=settings.MINIO_BUCKET,
            object_name=object_key,
            data=data,
            length=len(content),
        )
        logger.info("file_stored_minio", key=object_key, size=len(content))
        return ("minio", object_key)

    if settings.STORAGE_BACKEND == "database":
        # Les octets sont persistés via Document.raw_content.
        # storage_key doit être UNIQUE par ligne : ajouter un suffixe (même fichier ré-uploadé).
        from hashlib import sha256

        db_key = f"db://{sha256(content).hexdigest()}.{uuid4().hex}.{extension}"
        logger.info("file_stored_database_marker", key=db_key, size=len(content))
        return ("database", db_key)

    # Local storage
    local_dir = Path(settings.LOCAL_UPLOAD_DIR)
    local_dir.mkdir(parents=True, exist_ok=True)
    target = local_dir / f"{uuid4()}.{extension}"
    target.write_bytes(content)
    logger.info("file_stored_local", path=str(target), size=len(content))
    return ("local", str(target))


def read_bytes(storage_backend: str, storage_key: str) -> bytes:
    """Read file bytes from storage backend.

    Raises:
        FileNotFoundError: if the file cannot be found.
    """
    if storage_backend == "database":
        # La lecture réelle se fait via Document.raw_content dans les endpoints/services.
        raise FileNotFoundError(f"Database-backed content must be read from raw_content: {storage_key}")

    if storage_backend == "minio":
        try:
            client = _get_minio_client()
            response = client.get_object(settings.MINIO_BUCKET, storage_key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except Exception as exc:
            error_str = str(exc).lower()
            if "nosuchkey" in error_str or "not found" in error_str or "does not exist" in error_str:
                raise FileNotFoundError(f"Object not found in MinIO: {storage_key}") from exc
            logger.error("minio_read_error", key=storage_key, error=str(exc))
            raise FileNotFoundError(f"Cannot read from MinIO: {storage_key}") from exc

    # Local storage
    path = Path(storage_key)
    if not path.exists():
        raise FileNotFoundError(f"Local file not found: {storage_key}")
    return path.read_bytes()


def delete_bytes(storage_backend: str, storage_key: str) -> None:
    """Delete file from storage backend (best effort, never raises)."""
    if storage_backend == "database":
        # Rien à supprimer côté objet externe.
        logger.info("file_deleted_database_marker", key=storage_key)
        return

    if storage_backend == "minio":
        try:
            client = _get_minio_client()
            client.remove_object(settings.MINIO_BUCKET, storage_key)
            logger.info("file_deleted_minio", key=storage_key)
        except Exception as exc:
            logger.warning("minio_delete_failed", key=storage_key, error=str(exc))
        return

    try:
        Path(storage_key).unlink(missing_ok=True)
        logger.info("file_deleted_local", path=storage_key)
    except Exception as exc:
        logger.warning("local_delete_failed", path=storage_key, error=str(exc))
