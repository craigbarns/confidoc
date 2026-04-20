"""ConfiDoc Backend — Celery background tasks for document processing."""

import asyncio
import contextlib
import time
import uuid
from typing import Any

from celery import shared_task
from sqlalchemy import select, update

from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.models.document import Document, DocumentStatus
from app.services.document_processing_service import (
    build_anonymization_llm,
    build_anonymization_preview,
    build_extraction_ocr,
)
from app.services.storage_service import read_document_bytes

logger = get_logger(__name__)


def _run_async(coro):
    """Run an async coroutine inside a Celery worker thread."""
    return asyncio.run(coro)


async def _set_document_status(doc_id: str, status: DocumentStatus) -> None:
    """Set document status after a background failure."""
    try:
        async with async_session_factory() as db:
            await db.execute(
                update(Document)
                .where(Document.id == uuid.UUID(doc_id))
                .values(status=status)
            )
            await db.commit()
    except Exception as exc:
        logger.error(
            "set_document_status_failed",
            doc_id=doc_id,
            status=status.value,
            error=str(exc),
        )


@shared_task(bind=True, max_retries=2, default_retry_delay=30, time_limit=1800, soft_time_limit=900)
def anonymize_document_task(
    self,
    doc_id: str,
    profile: str,
    document_type: str,
) -> None:
    """Background task: run OCR + anonymization preview after upload."""
    try:
        _run_async(_anonymize_document_async(doc_id, profile, document_type))
    except Exception as exc:
        logger.error("celery_anonymize_failed", doc_id=doc_id, error=str(exc))
        with contextlib.suppress(Exception):
            final_failure = getattr(self.request, "retries", 0) >= self.max_retries
            next_status = DocumentStatus.FAILED if final_failure else DocumentStatus.UPLOADED
            _run_async(_set_document_status(doc_id, next_status))
        raise self.retry(exc=exc) from exc


async def _anonymize_document_async(
    doc_id: str,
    profile: str,
    document_type: str,
) -> None:
    async with async_session_factory() as db:
        result = await db.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
        document = result.scalar_one_or_none()
        if not document:
            logger.warning("background_anon_doc_not_found", doc_id=doc_id)
            return
        content = read_document_bytes(document)
        await build_anonymization_preview(
            db=db,
            document=document,
            file_content=content,
            profile=profile,
            document_type=document_type,
        )
        await db.commit()
        logger.info("background_anonymization_complete", doc_id=doc_id)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    time_limit=1800,
    soft_time_limit=900,
)
def process_document_legacy_task(
    self,
    doc_id: str,
    profile: str,
    document_type: str,
) -> None:
    """Background task: legacy full pipeline (OCR + LLM anonymization)."""
    try:
        _run_async(_process_document_legacy_async(doc_id, profile, document_type))
    except Exception as exc:
        logger.error("celery_process_legacy_failed", doc_id=doc_id, error=str(exc))
        with contextlib.suppress(Exception):
            final_failure = getattr(self.request, "retries", 0) >= self.max_retries
            next_status = DocumentStatus.FAILED if final_failure else DocumentStatus.UPLOADED
            _run_async(_set_document_status(doc_id, next_status))
        raise self.retry(exc=exc) from exc


async def _process_document_legacy_async(
    doc_id: str,
    profile: str,
    document_type: str,
) -> None:
    async with async_session_factory() as db:
        result = await db.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
        document = result.scalar_one_or_none()
        if not document:
            return
        file_content = read_document_bytes(document)
        original_text, _ = await build_extraction_ocr(db, document, file_content)
        await build_anonymization_llm(db, document, original_text)
        await db.commit()
        logger.info("background_process_complete", doc_id=doc_id)


# ── Scheduled tasks (called by Celery Beat) ─────────────────────────────

@shared_task(bind=True, max_retries=1, default_retry_delay=60, time_limit=600)
def run_retention_purge_task(self) -> dict[str, Any]:
    """Purge RGPD planifiée — appelée par Celery Beat tous les jours à 2h.

    Remplace le _periodic_retention_purge() du lifespan de l'API
    pour une fiabilité supérieure (persistance indépendante du redémarrage).
    """
    from app.config import get_settings
    from app.services.retention_service import purge_expired_data

    settings = get_settings()
    logger.info("scheduled_retention_purge_start")

    async def _purge() -> dict[str, int]:
        async with async_session_factory() as db:
            return await purge_expired_data(
                db,
                retention_raw_days=settings.RETENTION_RAW_FILE_DAYS,
                retention_ocr_days=settings.RETENTION_OCR_TEXT_DAYS,
                retention_entities_days=settings.RETENTION_ENTITIES_DAYS,
                retention_audit_days=settings.RETENTION_AUDIT_LOGS_DAYS,
                retention_mapping_days=settings.RETENTION_MAPPING_DAYS,
            )

    try:
        counts = _run_async(_purge())
    except Exception as exc:
        logger.error("scheduled_retention_purge_failed", error=str(exc))
        raise self.retry(exc=exc) from exc

    # Met à jour le timestamp Redis pour le check de rattrapage au démarrage
    async def _update_redis_ts() -> None:
        try:
            import redis.asyncio as aioredis

            r = aioredis.from_url(
                settings.REDIS_URL, decode_responses=True, socket_connect_timeout=1
            )
            async with r:
                await r.set("confidoc:retention:last_purge_ts", str(int(time.time())))
        except Exception:
            pass  # Non bloquant

    with contextlib.suppress(Exception):
        _run_async(_update_redis_ts())

    logger.info("scheduled_retention_purge_complete", deleted=counts)
    return counts


@shared_task(time_limit=300)
def cleanup_stale_celery_results() -> int:
    """Nettoie les résultats Celery obsolètes dans Redis (évite la fuite mémoire).

    Celery avec backend Redis ne nettoie pas auto les résultats.
    Cette tâche supprime les clés celery-task-meta-* de plus de 7 jours.
    """
    from app.config import get_settings

    settings = get_settings()
    try:
        import redis.asyncio as aioredis

        async def _cleanup() -> int:
            r = aioredis.from_url(settings.CELERY_RESULT_BACKEND, decode_responses=True)
            async with r:
                # Pattern celery-task-meta-*
                # On utilise scan_iter pour éviter de bloquer Redis
                deleted = 0
                cursor = 0
                while True:
                    cursor, keys = await r.scan(cursor, match="celery-task-meta-*", count=500)
                    if keys:
                        # Vérifier le TTL — si pas de TTL ou TTL > 7j, on supprime
                        for key in keys:
                            ttl = await r.ttl(key)
                            if ttl < 0 or ttl > 60 * 60 * 24 * 7:
                                await r.delete(key)
                                deleted += 1
                    if cursor == 0:
                        break
                return deleted

        return _run_async(_cleanup())
    except Exception as exc:
        logger.warning("cleanup_stale_celery_results_failed", error=str(exc))
        return 0
