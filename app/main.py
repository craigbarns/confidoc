"""ConfiDoc Backend — Application principale FastAPI."""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.core.database import init_database
from app.core.logging import get_logger, setup_logging
from app.middleware import RequestIdMiddleware, SecurityHeadersMiddleware, TimingMiddleware
from app.audit import AuditLogMiddleware
from app.rate_limit import limiter, rate_limit_exceeded_handler
from app.api.health import router as health_router
from app.api.ui import router as ui_router
from app.api.v1.router import router as v1_router


async def _purge_old_deleted_documents() -> None:
    """Désactivé: Les documents supprimés restent dans la corbeille indéfiniment.
    
    Pour vider la corbeille, utilisez l'endpoint DELETE /documents/{id}/permanent
    ou contactez un administrateur.
    """
    # NOTE: La suppression automatique est désactivée.
    # Les documents en corbeille sont conservés jusqu'à suppression manuelle.
    pass


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

    # Pas de purge automatique - les documents restent en corbeille indéfiniment
    # await _purge_old_deleted_documents()

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
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
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

    # ---- Routers ----
    app.include_router(health_router)
    app.include_router(ui_router)
    app.include_router(v1_router, prefix=settings.API_V1_PREFIX)

    return app


# Instance principale (uvicorn app.main:app)
app = create_app()
