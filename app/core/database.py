"""ConfiDoc Backend — Database setup (SQLAlchemy 2 async)."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.core.logging import get_logger
from app.models import Base

logger = get_logger(__name__)
settings = get_settings()

DOCUMENT_STATUS_ENUM_VALUES = (
    "UPLOADED",
    "PROCESSING",
    "EXTRACTING",
    "EXTRACTED",
    "ANONYMIZING",
    "ANONYMIZED",
    "REVIEWING",
    "READY",
    "FAILED",
)

engine = create_async_engine(
    settings.async_database_url,
    echo=settings.DEBUG and not settings.is_production,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
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
        try:
            # 1. Création des tables manquantes hors PGvector optionnel.
            core_tables = [
                table for name, table in Base.metadata.tables.items() if name != "document_chunks"
            ]
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    sync_conn,
                    tables=core_tables,
                )
            )
            logger.info("db_metadata_create_all_success")
        except Exception as e:
            logger.warning("db_metadata_create_all_failed_continuing", error=str(e))

        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            document_chunks = Base.metadata.tables.get("document_chunks")
            if document_chunks is not None:
                await conn.run_sync(
                    lambda sync_conn: document_chunks.create(
                        sync_conn,
                        checkfirst=True,
                    )
                )
                logger.info("db_document_chunks_ready")
        except Exception as e:
            logger.warning("db_document_chunks_skipped", error=str(e))

        # 2. Ajout manuel des colonnes manquantes
        manual_migrations = [
            *[
                f"ALTER TYPE documentstatus ADD VALUE IF NOT EXISTS '{status}';"
                for status in DOCUMENT_STATUS_ENUM_VALUES
            ],
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS raw_content bytea;",
            (
                "ALTER TABLE documents ADD COLUMN IF NOT EXISTS "
                "is_deleted boolean NOT NULL DEFAULT false;"
            ),
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS deleted_at timestamp with time zone;",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS tags text[];",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS doc_type varchar(40);",
            "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS siret varchar(200);",
            (
                "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS "
                "actor_type varchar(20) NOT NULL DEFAULT 'user';"
            ),
            "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS request_id varchar(64);",
            "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS event_hash varchar(64);",
            "ALTER TABLE pseudonym_mappings ADD COLUMN IF NOT EXISTS autopilot_validated boolean NOT NULL DEFAULT false;",
        ]

        for sql in manual_migrations:
            try:
                await conn.execute(text(sql))
            except Exception as e:
                logger.debug("db_manual_migration_skipped", sql=sql, error=str(e))

        # 3. Composite indexes (idempotent)
        indexes = [
            "CREATE EXTENSION IF NOT EXISTS pg_trgm;",
            "CREATE INDEX IF NOT EXISTS ix_documents_is_deleted ON documents (is_deleted);",
            (
                "CREATE INDEX IF NOT EXISTS ix_documents_user_created "
                "ON documents (uploaded_by_user_id, created_at);"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_documents_org_created "
                "ON documents (org_id, created_at);"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_documents_user_active "
                "ON documents (uploaded_by_user_id, is_deleted);"
            ),
            "CREATE INDEX IF NOT EXISTS ix_documents_org_status ON documents (org_id, status);",
            "CREATE INDEX IF NOT EXISTS ix_documents_doc_type ON documents (doc_type);",
            "CREATE INDEX IF NOT EXISTS ix_documents_tags ON documents USING GIN (tags);",
            "CREATE INDEX IF NOT EXISTS ix_audit_logs_actor_type ON audit_logs (actor_type);",
            "CREATE INDEX IF NOT EXISTS ix_audit_logs_request_id ON audit_logs (request_id);",
            "CREATE INDEX IF NOT EXISTS ix_audit_logs_event_hash ON audit_logs (event_hash);",
            # FTS index on document content (using gin and to_tsvector)
            (
                "CREATE INDEX IF NOT EXISTS ix_document_versions_content_fts "
                "ON document_versions USING GIN (to_tsvector('french', content_text));"
            ),
            # Fuzzy search on filename
            (
                "CREATE INDEX IF NOT EXISTS ix_documents_filename_trgm "
                "ON documents USING GIN (original_filename gin_trgm_ops);"
            ),
        ]

        for idx_sql in indexes:
            try:
                await conn.execute(text(idx_sql))
            except Exception as e:
                logger.debug("db_index_creation_skipped", sql=idx_sql, error=str(e))


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection pour obtenir une session BDD."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
