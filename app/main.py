"""ConfiDoc Backend — Application principale FastAPI."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.health import router as health_router
from app.api.ui import router as ui_router
from app.api.v1.router import router as v1_router
from app.audit import AuditLogMiddleware
from app.config import get_settings
from app.core.database import init_database
from app.core.logging import get_logger, setup_logging
from app.middleware import RequestIdMiddleware, SecurityHeadersMiddleware, TimingMiddleware
from app.rate_limit import limiter, rate_limit_exceeded_handler

_RETENTION_REDIS_KEY = "confidoc:retention:last_purge_ts"
_RETENTION_INTERVAL_SECONDS = 86400      # 24h normal interval
_RETENTION_MAX_GAP_SECONDS = 172800      # alerte si gap > 48h au démarrage


async def _run_retention_purge(logger: object) -> None:
    """Exécute une purge de rétention et met à jour le timestamp Redis."""
    import time

    from app.core.database import async_session_factory
    from app.services.retention_service import purge_expired_data

    try:
        async with async_session_factory() as db:
            deleted = await purge_expired_data(db)
            logger.info("retention_purge_complete", deleted_counts=deleted)  # type: ignore[attr-defined]
    except Exception as exc:
        logger.warning("retention_purge_failed", error=str(exc))  # type: ignore[attr-defined]
        return

    try:
        import redis.asyncio as aioredis
        settings = get_settings()
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=1)
        async with r:
            await r.set(_RETENTION_REDIS_KEY, str(int(time.time())))
    except Exception:
        pass  # Redis indisponible : la purge a quand même eu lieu


async def _periodic_retention_purge() -> None:
    """Background task: purge expired data every 24h (RGPD retention policy).

    - Au démarrage : vérifie via Redis si la dernière purge date de plus de 48h.
      Si oui, déclenche immédiatement une purge de rattrapage et logue un warning.
    - Toutes les 24h ensuite : purge normale.
    """
    import asyncio as _aio
    import time

    _logger = get_logger("retention")
    await _aio.sleep(60)  # attendre la fin du démarrage complet

    # ── Vérification de rattrapage au démarrage ──────────────────────
    last_purge_ts: float = 0.0
    try:
        import redis.asyncio as aioredis
        settings = get_settings()
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=1)
        async with r:
            raw = await r.get(_RETENTION_REDIS_KEY)
        if raw:
            last_purge_ts = float(raw)
    except Exception:
        pass  # Redis indisponible ou clé absente → on assume qu'une purge est nécessaire

    gap = time.time() - last_purge_ts
    if gap > _RETENTION_MAX_GAP_SECONDS:
        _logger.warning(
            "retention_purge_overdue",
            gap_hours=round(gap / 3600, 1),
            action="triggering_catchup_purge",
        )
        await _run_retention_purge(_logger)

    # ── Boucle normale 24h ───────────────────────────────────────────
    while True:
        await _aio.sleep(_RETENTION_INTERVAL_SECONDS)
        await _run_retention_purge(_logger)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifecycle de l'application : setup au démarrage, cleanup à l'arrêt."""
    settings = get_settings()
    setup_logging(
        log_level=settings.LOG_LEVEL,
        json_output=settings.is_production,
    )
    logger = get_logger(__name__)
    logger.info(
        "application_starting",
        app_name=settings.APP_NAME,
        environment=settings.APP_ENV,
        version="0.3.0",
    )
    await init_database()
    logger.info("database_initialized")

    import asyncio as _aio

    from app.services.demo_service import warm_demo_cache

    _aio.create_task(warm_demo_cache())
    _aio.create_task(_periodic_retention_purge())

    yield

    logger.info("application_shutting_down")


def create_app() -> FastAPI:
    """Factory pour créer l'application FastAPI."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        description=(
            "API backend de confidentialité documentaire "
            "pour professions réglementées."
        ),
        version="0.3.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ---- Rate limiting (slowapi) ----
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # ---- Fichiers statiques (UI : CSS / JS) ----
    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # ---- Middlewares (order: outermost first) ----
    app.add_middleware(AuditLogMiddleware)
    app.add_middleware(TimingMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
    )
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

    # ---- Routers ----
    app.include_router(ui_router)
    app.include_router(health_router)
    app.include_router(v1_router, prefix=settings.API_V1_PREFIX)

    return app


# Instance principale (uvicorn app.main:app)
app = create_app()
