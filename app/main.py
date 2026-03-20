"""ConfiDoc Backend — Application principale FastAPI."""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.database import init_database
from app.core.logging import get_logger, setup_logging
from app.api.health import router as health_router
from app.api.ui import router as ui_router
from app.api.v1.router import router as v1_router


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
    )
    await init_database()
    logger.info("database_initialized")

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
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ---- Middlewares ----
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    # ---- Routers ----
    app.include_router(health_router)
    app.include_router(ui_router)
    app.include_router(v1_router, prefix=settings.API_V1_PREFIX)

    return app


# Instance principale (uvicorn app.main:app)
app = create_app()
