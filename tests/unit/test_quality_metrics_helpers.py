"""Structural tests for the SQL helpers in ``quality_metrics_service``.

We do not run the queries against a real DB: instead we capture the statements
and assert that each one includes a ``WHERE … org_id = :org_id`` clause. This
is the core multi-tenancy invariant.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql


def _compiled(stmt: Any) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


class _CapturingResult:
    def __init__(self, scalar=None, all_rows=None, one=None):
        self._scalar = scalar
        self._all = all_rows or []
        self._one = one

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def one_or_none(self):
        return self._one

    def all(self):
        return list(self._all)


class _CapturingSession:
    def __init__(self, *, scalar=0, all_rows=None, one=None):
        self.statements: list[Any] = []
        self._scalar = scalar
        self._all = all_rows or []
        self._one = one

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _CapturingResult(
            scalar=self._scalar,
            all_rows=self._all,
            one=self._one,
        )


@pytest.mark.asyncio
async def test_count_documents_filters_on_org_id():
    from app.services.quality_metrics_service import _count_documents

    org_id = uuid.uuid4()
    db = _CapturingSession(all_rows=[])
    total, by_status = await _count_documents(db, org_id)  # type: ignore[arg-type]
    assert total == 0
    assert by_status == {}
    sql = _compiled(db.statements[0])
    assert "documents.org_id" in sql
    assert str(org_id) in sql
    assert "is_deleted" in sql.lower() or "is_deleted = false" in sql.lower()


@pytest.mark.asyncio
async def test_processed_validated_filters_on_org_id():
    from app.services.quality_metrics_service import (
        _count_processed_and_validated,
    )

    org_id = uuid.uuid4()
    db = _CapturingSession(one=(0, 0))
    processed, validated = await _count_processed_and_validated(db, org_id)  # type: ignore[arg-type]
    assert processed == 0
    assert validated == 0
    sql = _compiled(db.statements[0])
    assert "documents.org_id" in sql
    assert str(org_id) in sql


@pytest.mark.asyncio
async def test_avg_durations_filters_on_org_id_and_version_type():
    from app.models.document_version import DocumentVersionType
    from app.services.quality_metrics_service import _avg_durations_seconds

    org_id = uuid.uuid4()
    db = _CapturingSession(all_rows=[])
    res = await _avg_durations_seconds(
        db,  # type: ignore[arg-type]
        org_id,
        DocumentVersionType.PREVIEW_ANONYMIZED,
    )
    assert res is None
    sql = _compiled(db.statements[0])
    assert "documents.org_id" in sql
    assert str(org_id) in sql
    assert "PREVIEW_ANONYMIZED" in sql or "preview_anonymized" in sql


@pytest.mark.asyncio
async def test_avg_durations_seconds_python_average():
    """The function averages per-document deltas in Python — verify."""
    from datetime import UTC, datetime, timedelta

    from app.models.document_version import DocumentVersionType
    from app.services.quality_metrics_service import _avg_durations_seconds

    org_id = uuid.uuid4()
    base = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        (base, base + timedelta(seconds=10)),
        (base, base + timedelta(seconds=20)),
        (base, base + timedelta(seconds=30)),
        (base, None),
        (None, base + timedelta(seconds=999)),
    ]
    db = _CapturingSession(all_rows=rows)
    avg = await _avg_durations_seconds(
        db,  # type: ignore[arg-type]
        org_id,
        DocumentVersionType.FINAL_ANONYMIZED,
    )
    assert avg == 20.0


@pytest.mark.asyncio
async def test_draft_aggregates_filters_on_org_id():
    from app.services.quality_metrics_service import _draft_aggregates

    org_id = uuid.uuid4()
    db = _CapturingSession(scalar=0, all_rows=[])
    total, accepted, by_field, by_err = await _draft_aggregates(db, org_id)  # type: ignore[arg-type]
    assert total == 0
    assert accepted == 0
    assert by_field == {}
    assert by_err == {}
    # 4 statements: total, accepted, by_field, by_error.
    assert len(db.statements) == 4
    for stmt in db.statements:
        sql = _compiled(stmt)
        assert "golden_case_drafts.org_id" in sql
        assert str(org_id) in sql


@pytest.mark.asyncio
async def test_count_validated_with_drafts_filters_both_org_columns():
    from app.services.quality_metrics_service import (
        _count_validated_documents_with_drafts,
    )

    org_id = uuid.uuid4()
    db = _CapturingSession(scalar=0)
    res = await _count_validated_documents_with_drafts(db, org_id)  # type: ignore[arg-type]
    assert res == 0
    sql = _compiled(db.statements[0])
    # Must filter both joined tables on org_id to prevent cross-tenant joins.
    assert "documents.org_id" in sql
    assert "golden_case_drafts.org_id" in sql
    assert sql.count(str(org_id)) >= 2
