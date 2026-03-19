"""ConfiDoc Backend — Database setup (SQLAlchemy 2 async)."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.models import Base

settings = get_settings()

engine = create_async_engine(
    settings.async_database_url,
    echo=settings.DEBUG and not settings.is_production,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_database() -> None:
    """Initialise le schéma minimal si les tables n'existent pas."""
    from sqlalchemy import text
    async with engine.begin() as conn:
        # Création des tables si inexistantes
        await conn.run_sync(Base.metadata.create_all)
        # Ajout manuel des colonnes manquantes (Base.metadata.create_all ne le fait pas)
        await conn.execute(
            text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS raw_content bytea;")
        )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection pour obtenir une session BDD.

    Usage dans un router FastAPI :
        async def my_endpoint(db: AsyncSession = Depends(get_db)):
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
