"""Database context loader for the DPO Privacy Gate agent."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.models.entity_detection import EntityDetection
from app.models.pseudonym_mapping import PseudonymMapping
from app.services.agents.privacy_gate.service import run_privacy_gate


async def _has_anonymized_text(db: AsyncSession, document: Document) -> bool:
    for version_type in (
        DocumentVersionType.FINAL_ANONYMIZED,
        DocumentVersionType.PREVIEW_ANONYMIZED,
    ):
        result = await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.version_type == version_type,
            )
        )
        version = result.scalar_one_or_none()
        if version and getattr(version, "content_text", None):
            return True
    return False


async def load_document_privacy_gate_context(
    db: AsyncSession,
    document: Document,
    *,
    anonymized_text: str | None = None,
) -> dict:
    """Load non-sensitive decision context for the Privacy Gate agent."""
    mapping_result = await db.execute(
        select(PseudonymMapping)
        .where(PseudonymMapping.document_id == document.id)
        .order_by(PseudonymMapping.created_at.desc())
    )
    mapping = mapping_result.scalar_one_or_none()

    entity_result = await db.execute(
        select(EntityDetection.entity_type, func.count())
        .where(EntityDetection.document_id == document.id)
        .group_by(EntityDetection.entity_type)
    )
    entity_rows = entity_result.all()
    entity_types = [str(row[0] or "unknown").upper() for row in entity_rows]
    detections_count = sum(int(row[1] or 0) for row in entity_rows)

    audit_count_result = await db.execute(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.resource_id == str(document.id)
        )
    )
    audit_events_count = int(audit_count_result.scalar() or 0)

    has_text = (
        bool(anonymized_text.strip())
        if anonymized_text is not None
        else await _has_anonymized_text(db, document)
    )
    status_value = (
        document.status.value if hasattr(document.status, "value") else str(document.status)
    )
    return {
        "document_id": str(document.id),
        "status": status_value,
        "risk_score": getattr(mapping, "risk_score", None),
        "risk_level": getattr(mapping, "risk_level", None) or "low",
        "human_validated": bool(getattr(mapping, "human_validated", False)),
        "anonymized_text_available": has_text,
        "detections_count": detections_count,
        "entity_types": entity_types,
        "audit_events_count": audit_events_count,
    }


async def evaluate_document_privacy_gate(
    db: AsyncSession,
    document: Document,
    *,
    requested_action: str,
    anonymized_text: str | None = None,
) -> dict:
    context = await load_document_privacy_gate_context(
        db,
        document,
        anonymized_text=anonymized_text,
    )
    return await run_privacy_gate(**context, requested_action=requested_action)
