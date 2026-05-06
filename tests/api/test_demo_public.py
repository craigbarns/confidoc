"""Tests for the public demo endpoint."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException, status


class _ResultList:
    def __init__(self, rows: list[Any] | None = None) -> None:
        self._rows = rows or []

    def scalars(self) -> _ResultList:
        return self

    def first(self) -> Any | None:
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self) -> Any | None:
        return self.first()


class _DemoFakeSession:
    def __init__(self, memberships: list[Any] | None = None) -> None:
        self.memberships = memberships or []
        self.added: list[Any] = []
        self.commits = 0

    async def execute(self, _stmt: Any) -> _ResultList:
        return _ResultList(self.memberships)

    def add(self, obj: Any) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, _obj: Any) -> None:
        return None

    async def rollback(self) -> None:
        return None


@pytest.fixture
def demo_auth_overrides():
    from app.api.deps import get_current_user
    from app.core.database import get_db
    from app.main import app

    db = _DemoFakeSession()
    user = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=None,
        is_active=True,
        email="demo@confidoc.test",
    )

    async def _override_db():
        yield db

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    yield app, db, user

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_public_demo_requires_no_auth(client):
    payload = {
        "status": "ready",
        "original_excerpt": "Societe: DUPONT CONSEIL SAS",
        "anonymized_excerpt": "[SOCIETE_1]",
        "detections_count": 1,
        "entity_summary": {"SOCIETE": 1},
        "risk": {"score": 0.0, "level": "low"},
    }

    with patch("app.services.demo_service.get_demo_result", new_callable=AsyncMock) as get_demo:
        get_demo.return_value = payload
        resp = await client.get("/api/v1/demo/public")

    assert resp.status_code == 200
    assert resp.json()["anonymized_excerpt"] == "[SOCIETE_1]"


@pytest.mark.asyncio
async def test_public_demo_warming_up_returns_202(client):
    with patch("app.services.demo_service.get_demo_result", new_callable=AsyncMock) as get_demo:
        get_demo.return_value = None
        resp = await client.get("/api/v1/demo/public")

    assert resp.status_code == 202
    assert resp.json()["status"] == "warming_up"


@pytest.mark.asyncio
async def test_authenticated_demo_uses_database_fallback_when_storage_fails(
    client,
    demo_auth_overrides,
    monkeypatch,
    tmp_path,
):
    _, db, _user = demo_auth_overrides
    demo_pdf = tmp_path / "demo.pdf"
    demo_pdf.write_bytes(b"%PDF synthetic demo")

    import app.api.v1.demo as demo_mod

    monkeypatch.setattr(demo_mod, "DEMO_DOC_PATH", demo_pdf)
    monkeypatch.setattr(
        demo_mod,
        "store_bytes",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("object storage down")),
    )
    monkeypatch.setattr(demo_mod, "should_dispatch_document_task_to_celery", lambda **_: False)

    async def _noop_inline(**_kwargs):
        return {}

    monkeypatch.setattr(demo_mod, "run_anonymize_document_inline", _noop_inline)

    resp = await client.post("/api/v1/demo")

    assert resp.status_code == 201
    body = resp.json()
    assert body["demo_mode"] == "investor"
    document = next(obj for obj in db.added if obj.__class__.__name__ == "Document")
    assert document.storage_backend == "database"
    assert document.raw_content == b"%PDF synthetic demo"


@pytest.mark.asyncio
async def test_authenticated_demo_stays_personal_when_org_upload_forbidden(
    client,
    demo_auth_overrides,
    monkeypatch,
    tmp_path,
):
    _, db, user = demo_auth_overrides
    org_id = uuid.uuid4()
    user.org_id = org_id
    demo_pdf = tmp_path / "demo.pdf"
    demo_pdf.write_bytes(b"%PDF synthetic demo")

    import app.api.v1.demo as demo_mod

    monkeypatch.setattr(demo_mod, "DEMO_DOC_PATH", demo_pdf)
    monkeypatch.setattr(demo_mod, "store_bytes", lambda **_: ("database", "db://demo.pdf"))
    monkeypatch.setattr(demo_mod, "should_dispatch_document_task_to_celery", lambda **_: False)

    async def _deny_upload(*_args, **_kwargs):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    async def _noop_inline(**_kwargs):
        return {}

    monkeypatch.setattr(demo_mod, "require_org_permission", _deny_upload)
    monkeypatch.setattr(demo_mod, "run_anonymize_document_inline", _noop_inline)

    resp = await client.post("/api/v1/demo")

    assert resp.status_code == 201
    document = next(obj for obj in db.added if obj.__class__.__name__ == "Document")
    assert document.org_id is None


@pytest.mark.asyncio
async def test_public_demo_audit_report_pdf_requires_no_auth(client):
    payload = {
        "status": "ready",
        "filename": "demo.pdf",
        "anonymized_excerpt": "[SOCIETE_1]",
        "detections_count": 1,
        "entity_summary": {"SOCIETE": 1},
        "risk": {"score": 0.0, "level": "low"},
    }

    with (
        patch("app.services.demo_service.get_demo_result", new_callable=AsyncMock) as get_demo,
        patch(
            "app.services.demo_service.build_demo_audit_pdf",
            new=Mock(return_value=b"%PDF-1.3\n"),
        ),
    ):
        get_demo.return_value = payload
        resp = await client.get("/api/v1/demo/public/audit-report-pdf")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_public_demo_audit_report_pdf_warming_up_returns_202(client):
    with patch("app.services.demo_service.get_demo_result", new_callable=AsyncMock) as get_demo:
        get_demo.return_value = None
        resp = await client.get("/api/v1/demo/public/audit-report-pdf")

    assert resp.status_code == 202
    assert resp.json()["status"] == "warming_up"
