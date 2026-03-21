"""ConfiDoc Backend — Health check & readiness endpoints."""

from fastapi import APIRouter, status
from sqlalchemy import text

from app.config import get_settings
from app.core.database import async_session_factory
from app.core.logging import get_logger

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get(
    "/",
    status_code=status.HTTP_200_OK,
    summary="Root endpoint",
    description="Point d'entrée HTTP public de l'API.",
)
async def root() -> dict:
    """Endpoint racine pour éviter le 404 sur le domaine principal."""
    return {
        "service": "confidoc-backend",
        "status": "ok",
        "health": "/health",
        "ui": "/ui",
        "release": "v3-force-2026-03-19",
    }


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health check",
    description="Vérifie que l'application est en vie.",
)
async def health_check() -> dict:
    """Liveness probe — l'application répond."""
    return {
        "status": "healthy",
        "service": "confidoc-backend",
        "release": "v3-force-2026-03-19",
    }


@router.get(
    "/readiness",
    status_code=status.HTTP_200_OK,
    summary="Readiness check",
    description="Vérifie que l'application et ses dépendances sont prêtes.",
)
async def readiness_check() -> dict:
    """Readiness probe — toutes les dépendances sont accessibles."""
    checks: dict[str, str] = {}
    settings = get_settings()

    # Check PostgreSQL
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        logger.error("database_readiness_failed", error=str(e))
        checks["database"] = f"error: {str(e)}"

    # Check Redis
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as e:
        logger.error("redis_readiness_failed", error=str(e))
        checks["redis"] = f"error: {str(e)}"

    # Check object storage only when MinIO/S3 backend is configured.
    if settings.STORAGE_BACKEND == "minio":
        try:
            from minio import Minio

            client = Minio(
                settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_USE_SSL,
            )
            client.bucket_exists(settings.MINIO_BUCKET)
            checks["storage"] = "ok"
        except Exception as e:
            logger.error("minio_readiness_failed", error=str(e))
            checks["storage"] = f"error: {str(e)}"
    else:
        checks["storage"] = f"skipped: storage_backend={settings.STORAGE_BACKEND}"

    all_ok = all(v == "ok" or v.startswith("skipped:") for v in checks.values())

    return {
        "status": "ready" if all_ok else "degraded",
        "service": "confidoc-backend",
        "checks": checks,
    }
