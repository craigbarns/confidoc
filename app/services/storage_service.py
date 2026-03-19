"""ConfiDoc Backend — Storage service (local / MinIO)."""

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from minio import Minio

from app.config import get_settings

settings = get_settings()


def store_bytes(content: bytes, extension: str) -> tuple[str, str]:
    """Stocke un fichier et retourne (storage_backend, storage_key)."""
    extension = extension.lower()
    object_key = f"raw/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{uuid4()}.{extension}"

    if settings.STORAGE_BACKEND == "minio":
        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_USE_SSL,
        )
        if not client.bucket_exists(settings.MINIO_BUCKET):
            client.make_bucket(settings.MINIO_BUCKET)

        data = BytesIO(content)
        client.put_object(
            bucket_name=settings.MINIO_BUCKET,
            object_name=object_key,
            data=data,
            length=len(content),
        )
        return ("minio", object_key)

    local_dir = Path(settings.LOCAL_UPLOAD_DIR)
    local_dir.mkdir(parents=True, exist_ok=True)
    target = local_dir / f"{uuid4()}.{extension}"
    target.write_bytes(content)
    return ("local", str(target))


def read_bytes(storage_backend: str, storage_key: str) -> bytes:
    """Lit un fichier depuis le backend de stockage."""
    if storage_backend == "minio":
        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_USE_SSL,
        )
        response = client.get_object(settings.MINIO_BUCKET, storage_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    return Path(storage_key).read_bytes()
