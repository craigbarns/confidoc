"""Unit tests for ``app.services.golden_draft_service``."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest


class _CapturingDb:
    """A minimal stand-in for AsyncSession that captures added objects."""

    def __init__(self) -> None:
        self.added: list[Any] = []
        self.committed = False
        self._bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    def get_bind(self):
        return self._bind

    def add(self, obj: Any) -> None:
        if obj.id is None:
            obj.id = uuid.uuid4()
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True

    async def flush(self) -> None:
        return None

    async def refresh(self, obj: Any) -> None:
        return None


@pytest.mark.asyncio
async def test_create_golden_draft_truncates_oversized_payloads():
    from app.models.golden_case_draft import (
        CORRECTED_VALUE_MAX_CHARS,
        SOURCE_SNIPPET_MAX_CHARS,
    )
    from app.services.golden_draft_service import create_golden_draft

    db = _CapturingDb()
    org_id = uuid.uuid4()
    document_id = uuid.uuid4()
    user_id = uuid.uuid4()

    long_value = "x" * (CORRECTED_VALUE_MAX_CHARS + 200)
    long_snippet = "s" * (SOURCE_SNIPPET_MAX_CHARS + 200)

    draft = await create_golden_draft(
        db,  # type: ignore[arg-type]
        org_id=org_id,
        document_id=document_id,
        created_by_user_id=user_id,
        field_name="total_ttc",
        predicted_value="1200",
        corrected_value=long_value,
        source_snippet=long_snippet,
        error_type="manual_correction",
        confidence_before=None,
        document_type="invoice",
    )

    assert len(draft.corrected_value) == CORRECTED_VALUE_MAX_CHARS
    assert len(draft.source_snippet or "") == SOURCE_SNIPPET_MAX_CHARS
    assert draft.org_id == org_id
    assert draft.document_id == document_id


@pytest.mark.asyncio
async def test_create_drafts_from_corrections_skips_none_values():
    from app.services.golden_draft_service import create_drafts_from_corrections

    db = _CapturingDb()
    org_id = uuid.uuid4()
    document_id = uuid.uuid4()

    drafts = await create_drafts_from_corrections(
        db,  # type: ignore[arg-type]
        org_id=org_id,
        document_id=document_id,
        created_by_user_id=None,
        document_type="invoice",
        corrected_data={"total_ttc": 1234.5, "tva": None, "siret": "123"},
        predicted_data={"total_ttc": 1200.0, "siret": None},
        source_snippet="anonymized excerpt",
    )

    assert len(drafts) == 2
    by_field = {d.field_name: d for d in drafts}
    assert "total_ttc" in by_field
    assert "siret" in by_field
    assert "tva" not in by_field
    assert by_field["total_ttc"].predicted_value == "1200.0"
    assert by_field["total_ttc"].corrected_value == "1234.5"
    assert by_field["siret"].predicted_value is None


@pytest.mark.asyncio
async def test_create_drafts_from_corrections_no_data_no_commit():
    from app.services.golden_draft_service import create_drafts_from_corrections

    db = _CapturingDb()
    drafts = await create_drafts_from_corrections(
        db,  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        created_by_user_id=None,
        document_type="invoice",
        corrected_data={},
    )
    assert drafts == []
    assert db.committed is False
