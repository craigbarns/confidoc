"""ConfiDoc — RGPD retention and purge service.

Configurable per-layer retention with automatic cleanup.
Follows CNIL data minimization principles.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.models.entity_detection import EntityDetection

logger = get_logger(__name__)


async def purge_expired_data(
    db: AsyncSession,
    *,
    retention_raw_days: int = 90,
    retention_ocr_days: int = 180,
    retention_entities_days: int = 365,
    retention_audit_days: int = 1095,
    retention_mapping_days: int = 90,
    dry_run: bool = False,
) -> dict[str, int]:
    """Purge data that has exceeded its retention period.

    Returns counts of deleted rows per category.
    """
    now = datetime.now(timezone.utc)
    counts: dict[str, int] = {}

    # 1) Raw file content (raw_content column on documents)
    if retention_raw_days > 0:
        cutoff = now - timedelta(days=retention_raw_days)
        stmt = (
            select(Document)
            .where(Document.created_at < cutoff)
            .where(Document.raw_content.isnot(None))
        )
        result = await db.execute(stmt)
        docs = list(result.scalars().all())
        if not dry_run:
            for doc in docs:
                doc.raw_content = None
        counts["raw_content_cleared"] = len(docs)

    # 2) OCR text versions
    if retention_ocr_days > 0:
        cutoff = now - timedelta(days=retention_ocr_days)
        stmt = delete(DocumentVersion).where(
            DocumentVersion.created_at < cutoff,
            DocumentVersion.version_type == DocumentVersionType.ORIGINAL_TEXT,
        )
        if not dry_run:
            result = await db.execute(stmt)
            counts["ocr_text_deleted"] = result.rowcount
        else:
            counts["ocr_text_deleted"] = 0

    # 3) Entity detections
    if retention_entities_days > 0:
        cutoff = now - timedelta(days=retention_entities_days)
        stmt = delete(EntityDetection).where(EntityDetection.created_at < cutoff)
        if not dry_run:
            result = await db.execute(stmt)
            counts["entities_deleted"] = result.rowcount
        else:
            counts["entities_deleted"] = 0

    # 4) Audit logs
    if retention_audit_days > 0:
        cutoff = now - timedelta(days=retention_audit_days)
        stmt = delete(AuditLog).where(AuditLog.created_at < cutoff)
        if not dry_run:
            result = await db.execute(stmt)
            counts["audit_logs_deleted"] = result.rowcount
        else:
            counts["audit_logs_deleted"] = 0

    # 5) Pseudonym mappings (expired)
    try:
        from app.models.pseudonym_mapping import PseudonymMapping
        if retention_mapping_days > 0:
            cutoff = now - timedelta(days=retention_mapping_days)
            stmt = delete(PseudonymMapping).where(PseudonymMapping.created_at < cutoff)
            if not dry_run:
                result = await db.execute(stmt)
                counts["mappings_deleted"] = result.rowcount
            else:
                counts["mappings_deleted"] = 0
    except Exception:
        counts["mappings_deleted"] = 0

    if not dry_run:
        await db.commit()

    logger.info("rgpd_purge_complete", counts=counts, dry_run=dry_run)
    return counts
