"""Tests for organization-scoped audit trail access."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from app.api.v1 import compliance


class _ScalarRows:
    def scalars(self) -> _ScalarRows:
        return self

    def all(self) -> list[Any]:
        return []


class _CaptureDb:
    def __init__(self) -> None:
        self.statement: Any = None

    async def execute(self, statement: Any) -> _ScalarRows:
        self.statement = statement
        return _ScalarRows()


@pytest.mark.asyncio
async def test_audit_logs_are_scoped_to_current_org(monkeypatch) -> None:
    org_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), org_id=org_id)
    db = _CaptureDb()
    calls: dict[str, Any] = {}

    async def fake_require_org_permission(
        _db: Any,
        *,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        permission: str,
    ) -> None:
        calls["user_id"] = user_id
        calls["org_id"] = org_id
        calls["permission"] = permission

    monkeypatch.setattr(
        "app.services.rbac_service.require_org_permission",
        fake_require_org_permission,
    )

    logs = await compliance.get_audit_logs(user, db, limit=25)

    assert logs == []
    assert calls == {
        "user_id": user.id,
        "org_id": org_id,
        "permission": "audit.read",
    }
    compiled = str(db.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "audit_logs.org_id" in compiled
    assert org_id.hex in compiled
