"""ConfiDoc Backend — Health check & readiness endpoints."""

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings
from app.core.database import async_session_factory
from app.core.logging import get_logger

router = APIRouter(tags=["health"])
logger = get_logger(__name__)

_CELERY_PROBE_CACHE_TTL_SECONDS = 30.0
_CELERY_PROBE_TIMEOUT_SECONDS = 0.7
_celery_probe_cache: dict[str, Any] = {
    "checked_at": 0.0,
    "payload": None,
}


def _inspect_celery_workers() -> dict[str, Any]:
    """Run the blocking Celery inspect call with a short broker-side timeout."""
    from app.workers.celery_app import celery_app

    inspect = celery_app.control.inspect(timeout=0.45)
    workers = inspect.ping()
    if workers:
        return {"status": "ok", "workers_online": len(workers)}
    return {"status": "warning", "detail": "No workers responding"}


async def _check_celery_workers() -> dict[str, Any]:
    """Return a cached, non-critical Celery readiness result.

    Celery inspect is blocking and can take ~2s on Railway. Keep readiness fast:
    DB/Redis remain critical, while worker state is informational and cached.
    """
    now = time.monotonic()
    cached = _celery_probe_cache.get("payload")
    checked_at = float(_celery_probe_cache.get("checked_at") or 0.0)
    if isinstance(cached, dict) and now - checked_at < _CELERY_PROBE_CACHE_TTL_SECONDS:
        payload = dict(cached)
        payload["cached"] = True
        return payload

    try:
        payload = await asyncio.wait_for(
            asyncio.to_thread(_inspect_celery_workers),
            timeout=_CELERY_PROBE_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        payload = {"status": "warning", "detail": str(exc)}

    _celery_probe_cache["checked_at"] = now
    _celery_probe_cache["payload"] = payload
    return payload


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
        "release": "v8.2-mistral-ocr",
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
        "release": "v8.2-mistral-ocr",
    }


@router.get(
    "/readiness",
    summary="Readiness check",
    description="Vérifie que l'application et ses dépendances sont prêtes.",
)
async def readiness_check() -> JSONResponse:
    """Readiness probe — toutes les dépendances critiques sont accessibles.

    Retourne HTTP 200 si tout est OK, 503 si une dépendance critique est KO.
    Railway utilise ce code pour redémarrer automatiquement le service.
    """
    t0 = time.perf_counter()
    checks: dict[str, dict] = {}
    settings = get_settings()

    # ── PostgreSQL (critique) ──
    try:
        pg_t0 = time.perf_counter()
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - pg_t0) * 1000, 2),
        }
    except Exception as e:
        logger.error("database_readiness_failed", error=str(e))
        checks["database"] = {"status": "error", "detail": str(e)}

    # ── Redis (critique) ──
    try:
        redis_t0 = time.perf_counter()
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        await r.ping()
        await r.close()
        checks["redis"] = {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - redis_t0) * 1000, 2),
        }
    except Exception as e:
        logger.error("redis_readiness_failed", error=str(e))
        checks["redis"] = {"status": "error", "detail": str(e)}

    # ── Celery workers (informationnel, non bloquant) ──
    checks["celery"] = await _check_celery_workers()

    # ── Object storage (optionnel selon config) ──
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
            checks["storage"] = {"status": "ok"}
        except Exception as e:
            logger.error("minio_readiness_failed", error=str(e))
            checks["storage"] = {"status": "error", "detail": str(e)}
    else:
        checks["storage"] = {"status": "skipped", "detail": f"backend={settings.STORAGE_BACKEND}"}

    # ── Déterminer le statut global ──
    critical_services = ["database", "redis"]
    critical_ok = all(checks.get(s, {}).get("status") == "ok" for s in critical_services)
    storage_ok = checks.get("storage", {}).get("status") in ("ok", "skipped")
    all_ok = critical_ok and storage_ok

    status_code = status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE

    body = {
        "status": "ready" if all_ok else "degraded",
        "service": "confidoc-backend",
        "timestamp": datetime.now(UTC).isoformat(),
        "total_latency_ms": round((time.perf_counter() - t0) * 1000, 2),
        "checks": checks,
    }

    return JSONResponse(status_code=status_code, content=body)
