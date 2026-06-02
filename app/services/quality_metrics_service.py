"""ConfiDoc Backend — Quality / business metrics service.

This module derives investor-grade metrics from data already present in the
codebase:

- ``Document.created_at`` — upload timestamp.
- ``DocumentVersion.created_at`` — when each pipeline stage emitted output.
- ``Document.status`` — current pipeline state.
- ``GoldenCaseDraft`` — structured signal of human corrections (Data Flywheel).

Honest defaults: any metric that cannot yet be computed reliably (no validated
document, no draft, etc.) is returned as ``None`` rather than a misleading
zero.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.models.golden_case_draft import GoldenCaseDraft, GoldenDraftStatus


@dataclass
class QualityMetrics:
    """Plain-data container so we can keep the service pure-Python testable."""

    org_id: uuid.UUID | None
    as_of: datetime
    total_documents: int = 0
    processed_documents: int = 0
    validated_documents: int = 0
    avg_processing_seconds: float | None = None
    avg_time_to_validation_seconds: float | None = None
    one_shot_full_ready_rate: float | None = None
    avg_human_overrides_per_document: float | None = None
    total_golden_case_drafts: int = 0
    accepted_golden_case_drafts: int = 0
    corrections_by_field: dict[str, int] = field(default_factory=dict)
    corrections_by_error_type: dict[str, int] = field(default_factory=dict)
    documents_by_status: dict[str, int] = field(default_factory=dict)
    ai_readiness_score: int | None = None
    ai_readiness_level: str | None = None


def _empty(org_id: uuid.UUID | None) -> QualityMetrics:
    return QualityMetrics(org_id=org_id, as_of=datetime.now(UTC))


async def _count_documents(db: AsyncSession, org_id: uuid.UUID) -> tuple[int, dict[str, int]]:
    """Return (total_documents, documents_by_status)."""
    result = await db.execute(
        select(Document.status, func.count())
        .where(Document.org_id == org_id, Document.is_deleted.is_(False))
        .group_by(Document.status)
    )
    by_status: dict[str, int] = {}
    total = 0
    for row in result.all():
        st = row[0]
        key = st.value if hasattr(st, "value") else str(st)
        count = int(row[1] or 0)
        by_status[key] = count
        total += count
    return total, by_status


async def _count_processed_and_validated(db: AsyncSession, org_id: uuid.UUID) -> tuple[int, int]:
    """Count distinct documents that reached preview / final anonymization."""
    stmt = (
        select(
            func.count(
                distinct(
                    case(
                        (
                            DocumentVersion.version_type == DocumentVersionType.PREVIEW_ANONYMIZED,
                            DocumentVersion.document_id,
                        ),
                        else_=None,
                    )
                )
            ),
            func.count(
                distinct(
                    case(
                        (
                            DocumentVersion.version_type == DocumentVersionType.FINAL_ANONYMIZED,
                            DocumentVersion.document_id,
                        ),
                        else_=None,
                    )
                )
            ),
        )
        .select_from(DocumentVersion)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(Document.org_id == org_id, Document.is_deleted.is_(False))
    )
    result = await db.execute(stmt)
    row = result.one_or_none()
    if row is None:
        return 0, 0
    return int(row[0] or 0), int(row[1] or 0)


async def _avg_durations_seconds(
    db: AsyncSession,
    org_id: uuid.UUID,
    version_type: DocumentVersionType,
) -> float | None:
    """Average seconds between Document.created_at and the first version of
    a given type, computed in Python to stay portable across DB dialects."""
    stmt = (
        select(
            Document.created_at,
            func.min(DocumentVersion.created_at),
        )
        .select_from(Document)
        .join(DocumentVersion, DocumentVersion.document_id == Document.id)
        .where(
            Document.org_id == org_id,
            Document.is_deleted.is_(False),
            DocumentVersion.version_type == version_type,
        )
        .group_by(Document.id, Document.created_at)
    )
    result = await db.execute(stmt)
    durations: list[float] = []
    for upload_at, version_at in result.all():
        if upload_at is None or version_at is None:
            continue
        delta = (version_at - upload_at).total_seconds()
        if delta < 0:
            continue
        durations.append(delta)
    if not durations:
        return None
    return round(sum(durations) / len(durations), 3)


async def _draft_aggregates(
    db: AsyncSession, org_id: uuid.UUID
) -> tuple[int, int, dict[str, int], dict[str, int]]:
    """Return (total, accepted, by_field, by_error_type) for golden drafts."""
    total_stmt = (
        select(func.count()).select_from(GoldenCaseDraft).where(GoldenCaseDraft.org_id == org_id)
    )
    accepted_stmt = (
        select(func.count())
        .select_from(GoldenCaseDraft)
        .where(
            GoldenCaseDraft.org_id == org_id,
            GoldenCaseDraft.status == GoldenDraftStatus.ACCEPTED,
        )
    )
    by_field_stmt = (
        select(GoldenCaseDraft.field_name, func.count())
        .where(GoldenCaseDraft.org_id == org_id)
        .group_by(GoldenCaseDraft.field_name)
    )
    by_err_stmt = (
        select(GoldenCaseDraft.error_type, func.count())
        .where(GoldenCaseDraft.org_id == org_id)
        .group_by(GoldenCaseDraft.error_type)
    )

    total = int((await db.execute(total_stmt)).scalar() or 0)
    accepted = int((await db.execute(accepted_stmt)).scalar() or 0)
    by_field: dict[str, int] = {}
    for row in (await db.execute(by_field_stmt)).all():
        by_field[str(row[0])] = int(row[1] or 0)
    by_err: dict[str, int] = {}
    for row in (await db.execute(by_err_stmt)).all():
        by_err[str(row[0])] = int(row[1] or 0)
    return total, accepted, by_field, by_err


async def _count_validated_documents_with_drafts(db: AsyncSession, org_id: uuid.UUID) -> int:
    """Number of distinct validated documents that received at least one draft."""
    stmt = (
        select(func.count(distinct(GoldenCaseDraft.document_id)))
        .select_from(GoldenCaseDraft)
        .join(Document, Document.id == GoldenCaseDraft.document_id)
        .join(
            DocumentVersion,
            DocumentVersion.document_id == Document.id,
        )
        .where(
            GoldenCaseDraft.org_id == org_id,
            Document.org_id == org_id,
            Document.is_deleted.is_(False),
            DocumentVersion.version_type == DocumentVersionType.FINAL_ANONYMIZED,
        )
    )
    result = await db.execute(stmt)
    return int(result.scalar() or 0)


async def compute_quality_metrics(db: AsyncSession, org_id: uuid.UUID | None) -> QualityMetrics:
    """Compute the org-scoped quality dashboard.

    When ``org_id`` is None (e.g. a platform admin without an active
    membership), an empty snapshot is returned. We never aggregate cross-org.
    """
    if org_id is None:
        return _empty(None)

    total_documents, by_status = await _count_documents(db, org_id)
    processed, validated = await _count_processed_and_validated(db, org_id)
    avg_processing = await _avg_durations_seconds(
        db, org_id, DocumentVersionType.PREVIEW_ANONYMIZED
    )
    avg_validation = await _avg_durations_seconds(db, org_id, DocumentVersionType.FINAL_ANONYMIZED)
    total_drafts, accepted_drafts, by_field, by_err = await _draft_aggregates(db, org_id)
    validated_with_drafts = (
        await _count_validated_documents_with_drafts(db, org_id)
        if validated and total_drafts
        else 0
    )

    avg_overrides = round(total_drafts / validated, 3) if validated > 0 else None
    one_shot_rate: float | None
    if validated > 0:
        one_shot_rate = round(max(0, (validated - validated_with_drafts)) / validated, 4)
    else:
        one_shot_rate = None

    ai_readiness_score: int | None = None
    ai_readiness_level: str | None = None
    if total_documents > 0:
        processed_rate = processed / total_documents
        validation_rate = validated / total_documents
        one_shot_component = one_shot_rate if one_shot_rate is not None else 0.0
        failed = by_status.get("failed", 0)
        failure_penalty = (failed / total_documents) * 25
        ai_readiness_score = int(
            max(
                0,
                min(
                    100,
                    round(
                        processed_rate * 45
                        + validation_rate * 30
                        + one_shot_component * 20
                        + (5 if accepted_drafts > 0 else 0)
                        - failure_penalty
                    ),
                ),
            )
        )
        if ai_readiness_score >= 80:
            ai_readiness_level = "ready_for_ai"
        elif ai_readiness_score >= 60:
            ai_readiness_level = "internal_review"
        elif ai_readiness_score >= 35:
            ai_readiness_level = "needs_review"
        else:
            ai_readiness_level = "not_ready"

    return QualityMetrics(
        org_id=org_id,
        as_of=datetime.now(UTC),
        total_documents=total_documents,
        processed_documents=processed,
        validated_documents=validated,
        avg_processing_seconds=avg_processing,
        avg_time_to_validation_seconds=avg_validation,
        one_shot_full_ready_rate=one_shot_rate,
        avg_human_overrides_per_document=avg_overrides,
        total_golden_case_drafts=total_drafts,
        accepted_golden_case_drafts=accepted_drafts,
        corrections_by_field=by_field,
        corrections_by_error_type=by_err,
        documents_by_status=by_status,
        ai_readiness_score=ai_readiness_score,
        ai_readiness_level=ai_readiness_level,
    )
