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
    build_extraction_ocr,
)
from app.services.storage_service import read_document_bytes

logger = get_logger(__name__)


def celery_workers_available(timeout: float = 1.0) -> bool:
    """Return True when at least one Celery worker responds to broker inspection."""
    try:
        from app.workers.celery_app import celery_app

        workers = celery_app.control.inspect(timeout=timeout).ping()
        return bool(workers)
    except Exception as exc:
        logger.warning("celery_worker_probe_failed", error=str(exc))
        return False


async def run_anonymize_document_inline(
    doc_id: str,
    use_llm: bool = False,
    profile: str = "moderate",
    mode: str = "pseudonymization",
    document_type: str = "auto",
) -> dict[str, Any]:
    """Run anonymization without Celery for single-service Railway deployments."""
    try:
        return await _anonymize_document_async_v2(doc_id, use_llm, profile, mode, document_type)
    except Exception as exc:
        logger.error("inline_anonymize_failed", doc_id=doc_id, error=str(exc))
        await _set_document_status(doc_id, DocumentStatus.FAILED)
        return {"error": str(exc)}


def _run_async(coro):
    """Run an async coroutine inside a Celery worker thread safely."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


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
    except __import__("sqlalchemy").exc.SQLAlchemyError as exc:
        logger.error(
            "set_document_status_failed",
            doc_id=doc_id,
            status=status.value,
            error=str(exc),
        )


@shared_task(bind=True, max_retries=3, default_retry_delay=60, acks_late=True)
def extract_document_task(self, doc_id: str) -> dict[str, Any]:
    """Background task: Step 1 - OCR Extraction."""
    from app.core.metrics import PIPELINE_LATENCY, PIPELINE_STEPS
    start_time = time.time()
    try:
        res = _run_async(_extract_document_async(doc_id))
        PIPELINE_STEPS.labels(step="extract", status="success").inc()
        return res
    except (FileNotFoundError, ValueError) as exc:
        PIPELINE_STEPS.labels(step="extract", status="error_unrecoverable").inc()
        logger.error("celery_extract_unrecoverable", doc_id=doc_id, error=str(exc))
        _run_async(_set_document_status(doc_id, DocumentStatus.FAILED))
        return {"error": str(exc)}
    except Exception as exc:
        PIPELINE_STEPS.labels(step="extract", status="error_retry").inc()
        logger.error("celery_extract_failed_retrying", doc_id=doc_id, error=str(exc))
        raise self.retry(exc=exc) from exc
    finally:
        PIPELINE_LATENCY.labels(step="extract").observe(time.time() - start_time)


async def _extract_document_async(doc_id: str) -> dict[str, Any]:
    async with async_session_factory() as db:
        result = await db.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
        document = result.scalar_one_or_none()
        if not document:
            return {"error": "document_not_found"}

        # Checkpoint: EXTRACTING
        document.status = DocumentStatus.EXTRACTING
        await db.commit()

        content = read_document_bytes(document)
        text, meta = await build_extraction_ocr(db, document, content)

        # Checkpoint: EXTRACTED
        document.status = DocumentStatus.EXTRACTED
        await db.commit()

        return {
            "document_id": doc_id,
            "status": "extracted",
            "text_length": len(text),
            "pages": meta.get("pages", 0),
        }


@shared_task(bind=True, max_retries=3, default_retry_delay=60, acks_late=True)
def anonymize_document_task(
    self,
    doc_id: str,
    use_llm: bool = False,
    profile: str = "moderate",
    mode: str = "pseudonymization",
    document_type: str = "auto",
) -> dict[str, Any]:
    """Background task: Step 2 - Anonymization/Pseudonymization."""
    from app.core.metrics import PIPELINE_LATENCY, PIPELINE_STEPS
    start_time = time.time()
    try:
        res = _run_async(
            _anonymize_document_async_v2(doc_id, use_llm, profile, mode, document_type)
        )
        PIPELINE_STEPS.labels(step="anonymize", status="success").inc()
        return res
    except Exception as exc:
        PIPELINE_STEPS.labels(step="anonymize", status="error").inc()
        logger.error("celery_anonymize_failed", doc_id=doc_id, error=str(exc))
        _run_async(_set_document_status(doc_id, DocumentStatus.FAILED))
        raise self.retry(exc=exc) from exc
    finally:
        PIPELINE_LATENCY.labels(step="anonymize").observe(time.time() - start_time)


async def _anonymize_document_async_v2(
    doc_id: str,
    use_llm: bool,
    profile: str,
    mode: str,
    document_type: str,
) -> dict[str, Any]:
    from app.models.document_version import DocumentVersion, DocumentVersionType
    from app.services.reidentification_risk_service import analyze_reidentification_risk

    async with async_session_factory() as db:
        result = await db.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
        document = result.scalar_one_or_none()
        if not document:
            return {"error": "document_not_found"}

        # Checkpoint: ANONYMIZING
        document.status = DocumentStatus.ANONYMIZING
        await db.commit()

        # Check if original text exists
        result = await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.version_type == DocumentVersionType.ORIGINAL_TEXT,
            )
        )
        original_version = result.scalar_one_or_none()
        if not original_version or not original_version.content_text:
            # Fallback: extract first
            document.status = DocumentStatus.EXTRACTING
            await db.commit()
            content = read_document_bytes(document)
            original_text, _ = await build_extraction_ocr(db, document, content)
            document.status = DocumentStatus.ANONYMIZING
            await db.commit()
        else:
            original_text = original_version.content_text

        effective_profile = "strict" if mode == "anonymization" else profile
        effective_use_llm = True if mode == "anonymization" else use_llm

        preview_text, detections, meta = await build_anonymization_llm(
            db,
            document,
            original_text,
            use_llm=effective_use_llm,
            profile=effective_profile,
            document_type=document_type,
        )

        # Risk analysis
        risk_report = analyze_reidentification_risk(preview_text, meta.get("entity_summary", {}))

        # Pseudonym mapping if needed
        if mode == "pseudonymization":
            try:
                from datetime import UTC, datetime, timedelta
                from app.config import get_settings
                from app.models.pseudonym_mapping import PseudonymMapping
                from app.services.crypto_service import encrypt_mapping

                settings = get_settings()
                raw_mapping = meta.get("registry_raw_mapping", {})
                if raw_mapping:
                    encrypted = encrypt_mapping(raw_mapping, settings.PSEUDO_MAPPING_KEY)
                    expiry = datetime.now(UTC) + timedelta(days=settings.RETENTION_MAPPING_DAYS)
                    db.add(PseudonymMapping(
                        document_id=document.id,
                        user_id=document.user_id,
                        encrypted_mapping=encrypted,
                        expires_at=expiry,
                        risk_score=risk_report.score,
                        risk_level=risk_report.level,
                    ))
            except Exception as exc:
                logger.warning("pseudo_mapping_save_failed_in_task", error=str(exc))

        # Checkpoint: READY. The UI and downstream export gates use "ready"
        # as the terminal state for documents with an available preview.
        document.status = DocumentStatus.READY
        await db.commit()

        return {
            "document_id": doc_id,
            "status": "ready",
            "detections_count": len(detections),
            "risk_score": risk_report.score,
        }


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    time_limit=1800,
    soft_time_limit=900,
    acks_late=True,
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

@shared_task(bind=True, max_retries=1, default_retry_delay=60, time_limit=600, acks_late=True)
def run_retention_purge_task(self) -> dict[str, Any]:
    """Purge RGPD planifiée — appelée par Celery Beat tous les jours à 2h."""
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

    async def _update_redis_ts() -> None:
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(
                settings.REDIS_URL, decode_responses=True, socket_connect_timeout=1
            )
            async with r:
                await r.set("confidoc:retention:last_purge_ts", str(int(time.time())))
        except Exception:
            pass

    with contextlib.suppress(Exception):
        _run_async(_update_redis_ts())

    logger.info("scheduled_retention_purge_complete", deleted=counts)
    return counts


@shared_task(time_limit=300, acks_late=True)
def cleanup_stale_celery_results() -> int:
    """Nettoie les résultats Celery obsolètes dans Redis."""
    from app.config import get_settings

    settings = get_settings()
    try:
        import redis.asyncio as aioredis

        async def _cleanup() -> int:
            r = aioredis.from_url(settings.CELERY_RESULT_BACKEND, decode_responses=True)
            async with r:
                deleted = 0
                cursor = 0
                while True:
                    cursor, keys = await r.scan(cursor, match="celery-task-meta-*", count=500)
                    if keys:
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
