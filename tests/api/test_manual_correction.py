"""Tests for manual anonymized-text correction workflow."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from app.api.v1 import _doc_processing
from app.models.document import DocumentStatus
from app.schemas.document import ManualCorrectionRequest


class _Result:
    def __init__(self, value: Any = None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value


class _CorrectionDb:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.commits = 0
        self.flushes = 0

    async def execute(self, _stmt: Any) -> _Result:
        return _Result(None)

    def add(self, obj: Any) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushes += 1

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_manual_correction_creates_new_preview_and_audit(monkeypatch) -> None:
    document_id = uuid.uuid4()
    user_id = uuid.uuid4()
    document = SimpleNamespace(
        id=document_id,
        org_id=None,
        uploaded_by_user_id=user_id,
        doc_type="auto",
        status=DocumentStatus.READY,
    )
    user = SimpleNamespace(id=user_id)
    db = _CorrectionDb()
    calls: dict[str, Any] = {}

    async def fake_get_document(
        _db: Any,
        requested_id: str,
        requested_user: uuid.UUID,
        permission: str,
    ):
        calls["requested_id"] = requested_id
        calls["requested_user"] = requested_user
        calls["permission"] = permission
        return document

    monkeypatch.setattr(_doc_processing, "_get_user_document_or_404", fake_get_document)

    response = await _doc_processing.correct_anonymized_document(
        str(document_id),
        user,
        db,
        ManualCorrectionRequest(
            final_text="Contact: secret@example.fr",
            masked_value="secret@example.fr",
            replacement="[EMAIL]",
            entity_type="email",
        ),
    )

    assert calls["permission"] == "documents.validate"
    assert response["status"] == "corrected"
    assert response["preview_text"] == "Contact: [EMAIL]"
    assert document.status == DocumentStatus.READY
    assert db.commits == 1
    assert any(obj.__class__.__name__ == "DocumentVersion" for obj in db.added)
    assert any(obj.__class__.__name__ == "AuditLog" for obj in db.added)


def test_viewer_role_cannot_validate_or_correct() -> None:
    from app.services.rbac_service import role_has_permission

    assert role_has_permission("viewer", None, "documents.validate") is False
    assert role_has_permission("admin", None, "documents.validate") is True
    assert role_has_permission("owner", None, "documents.validate") is True
