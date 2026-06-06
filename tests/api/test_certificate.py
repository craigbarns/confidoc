"""Tests for the compliance certificate endpoint."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from app.models.document import DocumentStatus


class _ResultList:
    def __init__(self, rows: list[Any] | None = None) -> None:
        self._rows = rows or []

    def scalars(self) -> _ResultList:
        return self

    def first(self) -> Any | None:
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self) -> Any | None:
        return self.first()

    def all(self) -> list[Any]:
        return self._rows


class _CertificateFakeSession:
    def __init__(
        self, document: Any, mapping: Any = None, detections: list[Any] | None = None
    ) -> None:
        self.document = document
        self.mapping = mapping
        self.detections = detections or []
        self.added: list[Any] = []
        self.commits = 0

    async def execute(self, stmt: Any) -> _ResultList:
        # Check if the query is for PseudonymMapping
        stmt_str = str(stmt).lower()
        if "pseudonym_mappings" in stmt_str or "pseudonymmapping" in stmt_str:
            return _ResultList([self.mapping] if self.mapping else [])
        elif "entity_detections" in stmt_str or "entitydetection" in stmt_str:
            if "count" in stmt_str:
                return _ResultList([len(self.detections)])
            return _ResultList(self.detections)
        elif "audit_logs" in stmt_str or "auditlog" in stmt_str:
            if "count" in stmt_str:
                return _ResultList([0])
            return _ResultList([])

        # Default fallback for Document query
        if "documents" in stmt_str or "document" in stmt_str:
            return _ResultList([self.document])
        return _ResultList([])

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
def cert_auth_overrides():
    from app.api.deps import get_current_user
    from app.core.database import get_db
    from app.main import app

    doc_id = uuid.uuid4()
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()

    document = SimpleNamespace(
        id=doc_id,
        org_id=None,
        uploaded_by_user_id=user_id,
        original_filename="releve_bancaire_secret.pdf",
        content_type="application/pdf",
        extension="pdf",
        size_bytes=1024,
        sha256="d666c04f9970868f0f08968f9bf9bf9bf9bf9bf9bf9bf9bf9bf9bf9bf9bf9",
        storage_backend="database",
        storage_key="db://releve_bancaire_secret.pdf",
        status=DocumentStatus.READY,
        created_at=SimpleNamespace(isoformat=lambda: "2026-05-21T07:51:47Z"),
    )

    mapping = SimpleNamespace(
        id=uuid.uuid4(),
        document_id=doc_id,
        risk_score=0.05,
        risk_level="low",
        human_validated=True,
        validated_at=SimpleNamespace(isoformat=lambda: "2026-05-21T07:52:00Z"),
        expires_at=SimpleNamespace(isoformat=lambda: "2026-06-21T07:52:00Z"),
        created_at=SimpleNamespace(isoformat=lambda: "2026-05-21T07:52:00Z"),
    )

    detection = SimpleNamespace(
        id=uuid.uuid4(),
        document_id=doc_id,
        entity_type="IBAN",
        value_excerpt="FR7612345678901234567890123",
        created_at=SimpleNamespace(isoformat=lambda: "2026-05-21T07:52:00Z"),
    )

    db = _CertificateFakeSession(document, mapping, [detection])
    user = SimpleNamespace(
        id=user_id,
        org_id=org_id,
        is_active=True,
        email="qa@confidoc.test",
    )

    async def _override_db():
        yield db

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    yield app, db, user, document

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_compliance_certificate_requires_auth(client):
    resp = await client.get("/api/v1/documents/some-uuid/compliance-certificate")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_audit_report_pdf_success(client, cert_auth_overrides, monkeypatch):
    _, _, _, document = cert_auth_overrides

    import app.api.v1._doc_export as doc_export

    async def _mock_anon_text(*args, **kwargs):
        return (
            "Document masqué: [SOCIETE_1] facture de 1\u202f234,56 € "
            "– “honoraires” • échéance <= 30 jours."
        )

    monkeypatch.setattr(doc_export, "_get_anonymized_text", _mock_anon_text)

    resp = await client.get(
        f"/api/v1/documents/{document.id}/audit-report-pdf",
        headers={"Authorization": "Bearer fake-token-passed-by-dependency-override"},
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_get_compliance_certificate_success(client, cert_auth_overrides, monkeypatch):
    app_instance, db, user, document = cert_auth_overrides

    # Mock settings.SECRET_KEY to ensure consistent test signature
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "SECRET_KEY", "qa-test-secret-key-12345")

    # Mock storage read if the handler tries to check or load original bytes
    import app.api.v1._doc_shared as doc_shared

    monkeypatch.setattr(doc_shared, "_read_file_or_404", lambda doc: b"%PDF-1.4 mock content")

    # Mock the export gate checks to allow export
    async def _allow_export(*args, **kwargs):
        return None

    monkeypatch.setattr(doc_shared, "_check_export_gate", _allow_export)

    # Mock anonymized text preview
    async def _mock_anon_text(*args, **kwargs):
        return "This is a bank statement for ACME [IBAN_1] done."

    monkeypatch.setattr(doc_shared, "_get_anonymized_text", _mock_anon_text)

    # Make request
    resp = await client.get(
        f"/api/v1/documents/{document.id}/compliance-certificate",
        headers={"Authorization": "Bearer fake-token-passed-by-dependency-override"},
    )

    # Assert 200 OK
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")

    # Assert audit log entry is added to db
    audit_logs = [obj for obj in db.added if obj.__class__.__name__ == "AuditLog"]
    assert len(audit_logs) == 1
    assert audit_logs[0].action == "export:certificate"
    assert str(audit_logs[0].resource_id) == str(document.id)
