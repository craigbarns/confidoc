"""ConfiDoc — RGPD retention and purge service.

Configurable per-layer retention with automatic cleanup.
Follows CNIL data minimization principles.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.rls import rls_bypass
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.models.entity_detection import EntityDetection
from app.services.storage_service import delete_bytes

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
    now = datetime.now(UTC)
    counts: dict[str, int] = {}

    async with rls_bypass(db):
        # 1) Raw source files (external object/local file + raw_content fallback)
        if retention_raw_days > 0:
            cutoff = now - timedelta(days=retention_raw_days)
            raw_stmt = (
                select(Document)
                .where(Document.created_at < cutoff)
                .where(
                    (Document.raw_content.isnot(None))
                    | (Document.storage_backend.in_(("local", "minio")))
                )
            )
            result = await db.execute(raw_stmt)
            docs = list(result.scalars().all())
            if not dry_run:
                for doc in docs:
                    if doc.storage_backend in {"local", "minio"}:
                        delete_bytes(doc.storage_backend, doc.storage_key)
                        doc.storage_backend = "purged"
                        doc.storage_key = f"purged://{doc.id}"
                    doc.raw_content = None
            counts["raw_sources_purged"] = len(docs)

        # 2) OCR text versions
        if retention_ocr_days > 0:
            cutoff = now - timedelta(days=retention_ocr_days)
            delete_stmt = delete(DocumentVersion).where(
                DocumentVersion.created_at < cutoff,
                DocumentVersion.version_type == DocumentVersionType.ORIGINAL_TEXT,
            )
            if not dry_run:
                delete_result = await db.execute(delete_stmt)
                counts["ocr_text_deleted"] = int(getattr(delete_result, "rowcount", 0) or 0)
            else:
                counts["ocr_text_deleted"] = 0

        # 3) Entity detections
        if retention_entities_days > 0:
            cutoff = now - timedelta(days=retention_entities_days)
            delete_stmt = delete(EntityDetection).where(EntityDetection.created_at < cutoff)
            if not dry_run:
                delete_result = await db.execute(delete_stmt)
                counts["entities_deleted"] = int(getattr(delete_result, "rowcount", 0) or 0)
            else:
                counts["entities_deleted"] = 0

        # 4) Audit logs
        if retention_audit_days > 0:
            cutoff = now - timedelta(days=retention_audit_days)
            delete_stmt = delete(AuditLog).where(AuditLog.created_at < cutoff)
            if not dry_run:
                delete_result = await db.execute(delete_stmt)
                counts["audit_logs_deleted"] = int(getattr(delete_result, "rowcount", 0) or 0)
            else:
                counts["audit_logs_deleted"] = 0

        # 5) Pseudonym mappings (expired)
        try:
            from app.models.pseudonym_mapping import PseudonymMapping

            if retention_mapping_days > 0:
                cutoff = now - timedelta(days=retention_mapping_days)
                delete_stmt = delete(PseudonymMapping).where(PseudonymMapping.created_at < cutoff)
                if not dry_run:
                    delete_result = await db.execute(delete_stmt)
                    counts["mappings_deleted"] = int(getattr(delete_result, "rowcount", 0) or 0)
                else:
                    counts["mappings_deleted"] = 0
        except Exception:
            counts["mappings_deleted"] = 0

        if not dry_run:
            await db.commit()

    logger.info("rgpd_purge_complete", counts=counts, dry_run=dry_run)
    return counts
