"""ConfiDoc Backend — Celery background tasks for document processing."""

import asyncio
import uuid

from celery import shared_task
from sqlalchemy import select, update

from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.models.document import Document, DocumentStatus
from app.services.document_processing_service import (
    build_anonymization_preview,
    build_anonymization_llm,
    build_extraction_ocr,
)

logger = get_logger(__name__)


def _run_async(coro):
    """Run an async coroutine inside a Celery worker thread."""
    return asyncio.run(coro)


async def _reset_document_status(doc_id: str) -> None:
    """Reset document status to UPLOADED after a background failure."""
    try:
        async with async_session_factory() as db:
            await db.execute(
                update(Document)
                .where(Document.id == uuid.UUID(doc_id))
                .values(status=DocumentStatus.UPLOADED)
            )
            await db.commit()
    except Exception as exc:
        logger.error("reset_document_status_failed", doc_id=doc_id, error=str(exc))


@shared_task(bind=True, max_retries=2, default_retry_delay=30, time_limit=600, soft_time_limit=540)
def anonymize_document_task(
    self,
    doc_id: str,
    content: bytes,
    profile: str,
    document_type: str,
) -> None:
    """Background task: run OCR + anonymization preview after upload."""
    try:
        _run_async(_anonymize_document_async(doc_id, content, profile, document_type))
    except Exception as exc:
        logger.error("celery_anonymize_failed", doc_id=doc_id, error=str(exc))
        try:
            _run_async(_reset_document_status(doc_id))
        except Exception:
            pass
        raise self.retry(exc=exc) from exc


async def _anonymize_document_async(
    doc_id: str,
    content: bytes,
    profile: str,
    document_type: str,
) -> None:
    async with async_session_factory() as db:
        result = await db.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
        document = result.scalar_one_or_none()
        if not document:
            logger.warning("background_anon_doc_not_found", doc_id=doc_id)
            return
        await build_anonymization_preview(
            db=db,
            document=document,
            file_content=content,
            profile=profile,
            document_type=document_type,
        )
        await db.commit()
        logger.info("background_anonymization_complete", doc_id=doc_id)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def process_document_legacy_task(
    self,
    doc_id: str,
    file_content: bytes,
    profile: str,
    document_type: str,
) -> None:
    """Background task: legacy full pipeline (OCR + LLM anonymization)."""
    try:
        _run_async(_process_document_legacy_async(doc_id, file_content, profile, document_type))
    except Exception as exc:
        logger.error("celery_process_legacy_failed", doc_id=doc_id, error=str(exc))
        try:
            _run_async(_reset_document_status(doc_id))
        except Exception:
            pass
        raise self.retry(exc=exc) from exc


async def _process_document_legacy_async(
    doc_id: str,
    file_content: bytes,
    profile: str,
    document_type: str,
) -> None:
    async with async_session_factory() as db:
        result = await db.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
        document = result.scalar_one_or_none()
        if not document:
            return
        original_text, _ = await build_extraction_ocr(db, document, file_content)
        await build_anonymization_llm(db, document, original_text)
        await db.commit()
        logger.info("background_process_complete", doc_id=doc_id)
