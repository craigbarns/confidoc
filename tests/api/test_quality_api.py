"""Tests for /api/v1/quality/golden-drafts (Data Flywheel)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList


# ──────────────────────────────────────────────────────────────────────
# Route registration
# ──────────────────────────────────────────────────────────────────────


class TestQualityRouterStructure:
    def _get_paths(self) -> list[str]:
        from app.api.v1.quality import router

        return [r.path for r in router.routes]

    def test_create_route_exists(self):
        assert "/golden-drafts" in self._get_paths()

    def test_status_route_exists(self):
        assert "/golden-drafts/{draft_id}/status" in self._get_paths()

    def test_quality_router_registered_in_v1(self):
        from app.api.v1.router import router

        all_paths = [getattr(r, "path", "") for r in router.routes]
        assert any("/quality/golden-drafts" in p for p in all_paths)


# ──────────────────────────────────────────────────────────────────────
# Auth required
# ──────────────────────────────────────────────────────────────────────


class TestQualityAuthRequired:
    @pytest.mark.asyncio
    async def test_post_requires_auth(self, client):
        resp = await client.post("/api/v1/quality/golden-drafts", json={})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_requires_auth(self, client):
        resp = await client.get("/api/v1/quality/golden-drafts")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_patch_requires_auth(self, client):
        resp = await client.patch(
            f"/api/v1/quality/golden-drafts/{uuid.uuid4()}/status",
            json={"status": "accepted"},
        )
        assert resp.status_code == 401


# ──────────────────────────────────────────────────────────────────────
# Schema validation
# ──────────────────────────────────────────────────────────────────────


class TestGoldenDraftCreateSchema:
    def test_required_fields_validation(self):
        from pydantic import ValidationError

        from app.schemas.golden_draft import GoldenDraftCreate

        with pytest.raises(ValidationError):
            GoldenDraftCreate()  # type: ignore[call-arg]

    def test_corrected_value_max_length_enforced(self):
        from pydantic import ValidationError

        from app.models.golden_case_draft import CORRECTED_VALUE_MAX_CHARS
        from app.schemas.golden_draft import GoldenDraftCreate

        with pytest.raises(ValidationError):
            GoldenDraftCreate(
                document_id=uuid.uuid4(),
                field_name="x",
                corrected_value="x" * (CORRECTED_VALUE_MAX_CHARS + 1),
                error_type="manual_correction",
                document_type="invoice",
            )

    def test_source_snippet_max_length_enforced(self):
        from pydantic import ValidationError

        from app.models.golden_case_draft import SOURCE_SNIPPET_MAX_CHARS
        from app.schemas.golden_draft import GoldenDraftCreate

        with pytest.raises(ValidationError):
            GoldenDraftCreate(
                document_id=uuid.uuid4(),
                field_name="x",
                corrected_value="ok",
                source_snippet="s" * (SOURCE_SNIPPET_MAX_CHARS + 1),
                error_type="manual_correction",
                document_type="invoice",
            )

    def test_status_update_validates_enum(self):
        from pydantic import ValidationError

        from app.schemas.golden_draft import GoldenDraftStatusUpdate

        with pytest.raises(ValidationError):
            GoldenDraftStatusUpdate(status="archived")  # type: ignore[arg-type]


# ──────────────────────────────────────────────────────────────────────
# Tiny in-memory async session: only handles the queries our endpoints
# build. Using this avoids requiring Postgres/SQLite for unit tests, while
# still exercising the real route handlers and tenant filtering.
# ──────────────────────────────────────────────────────────────────────


@dataclass
class _DocStub:
    id: uuid.UUID
    org_id: uuid.UUID


class _FakeResult:
    def __init__(self, rows: list[Any]):
        self._rows = list(rows)

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalars(self) -> "_FakeResult":
        return self

    def all(self) -> list[Any]:
        return list(self._rows)


class _FakeAsyncSession:
    """Minimal AsyncSession-like object for our two select shapes."""

    def __init__(self) -> None:
        self.documents: dict[uuid.UUID, _DocStub] = {}
        self.drafts: dict[uuid.UUID, Any] = {}

    # ---- query interpretation ----
    @staticmethod
    def _eval(clause: Any, obj: Any) -> bool:
        if clause is None:
            return True
        if isinstance(clause, BooleanClauseList):
            results = [_FakeAsyncSession._eval(c, obj) for c in clause.clauses]
            if clause.operator is operators.and_:
                return all(results)
            if clause.operator is operators.or_:
                return any(results)
            return all(results)
        if isinstance(clause, BinaryExpression):
            col = clause.left
            val = getattr(clause.right, "value", clause.right)
            attr = getattr(col, "key", None) or getattr(col, "name", None)
            if attr is None:
                return False
            actual = getattr(obj, attr, None)
            op = clause.operator
            if op is operators.eq:
                return actual == val
            if op is operators.ne:
                return actual != val
            return True
        return True

    async def execute(self, stmt: Any) -> _FakeResult:
        from app.models.document import Document
        from app.models.golden_case_draft import GoldenCaseDraft

        descs = stmt.column_descriptions or []
        target = descs[0].get("entity") if descs else None
        target_type = descs[0].get("type") if descs else None

        if target is Document or target_type is Document:
            matches = [
                d for d in self.documents.values() if self._eval(stmt.whereclause, d)
            ]
            return _FakeResult([m.id for m in matches])

        if target is GoldenCaseDraft or target_type is GoldenCaseDraft:
            matches = [
                d for d in self.drafts.values() if self._eval(stmt.whereclause, d)
            ]
            # Approximate ORDER BY created_at DESC for the list endpoint.
            matches.sort(
                key=lambda x: getattr(x, "created_at", 0) or 0, reverse=True
            )
            return _FakeResult(matches)

        return _FakeResult([])

    # ---- mutation surface ----
    def add(self, obj: Any) -> None:
        from datetime import UTC, datetime

        if obj.id is None:
            obj.id = uuid.uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(UTC)
        obj.updated_at = obj.created_at
        self.drafts[obj.id] = obj

    async def commit(self) -> None:
        from datetime import UTC, datetime

        for d in self.drafts.values():
            d.updated_at = datetime.now(UTC)

    async def refresh(self, obj: Any) -> None:
        # No-op: object is already up to date in our in-memory store.
        return None

    async def flush(self) -> None:
        return None

    async def close(self) -> None:
        return None


@pytest.fixture
def fake_db_factory():
    """Factory that returns a fresh fake session per test."""
    sessions: list[_FakeAsyncSession] = []

    def _make() -> _FakeAsyncSession:
        s = _FakeAsyncSession()
        sessions.append(s)
        return s

    return _make


@pytest.fixture
def app_with_overrides(fake_db_factory):
    """Yield (app, db, set_user) with deps overridden."""
    from app.api.deps import get_current_user
    from app.core.database import get_db
    from app.main import app

    db = fake_db_factory()

    state: dict[str, Any] = {"user": None}

    async def _override_db():
        yield db

    async def _override_user():
        if state["user"] is None:
            raise RuntimeError("set_user not called")
        return state["user"]

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    def set_user(user_id: uuid.UUID, org_id: uuid.UUID | None) -> Any:
        from types import SimpleNamespace

        u = SimpleNamespace(id=user_id, org_id=org_id, is_active=True)
        state["user"] = u
        return u

    yield app, db, set_user

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


# ──────────────────────────────────────────────────────────────────────
# Integration tests: full route logic with fake session
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_golden_draft_persists_in_org(app_with_overrides, client):
    _, db, set_user = app_with_overrides
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    set_user(user_id, org_id)

    doc_id = uuid.uuid4()
    db.documents[doc_id] = _DocStub(id=doc_id, org_id=org_id)

    payload = {
        "document_id": str(doc_id),
        "field_name": "total_ttc",
        "predicted_value": "1200.00",
        "corrected_value": "1234.56",
        "source_snippet": "Total TTC: [MONTANT_1]",
        "error_type": "wrong_extraction",
        "confidence_before": 0.42,
        "document_type": "invoice",
    }
    resp = await client.post("/api/v1/quality/golden-drafts", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "draft"
    assert body["org_id"] == str(org_id)
    assert body["field_name"] == "total_ttc"
    assert body["corrected_value"] == "1234.56"
    assert len(db.drafts) == 1


@pytest.mark.asyncio
async def test_create_validates_required_fields(app_with_overrides, client):
    _, db, set_user = app_with_overrides
    set_user(uuid.uuid4(), uuid.uuid4())

    resp = await client.post(
        "/api/v1/quality/golden-drafts",
        json={"document_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_rejects_document_from_other_org(
    app_with_overrides, client
):
    _, db, set_user = app_with_overrides
    org_id = uuid.uuid4()
    other_org_id = uuid.uuid4()
    set_user(uuid.uuid4(), org_id)

    doc_id = uuid.uuid4()
    db.documents[doc_id] = _DocStub(id=doc_id, org_id=other_org_id)

    payload = {
        "document_id": str(doc_id),
        "field_name": "siret",
        "corrected_value": "12345678900012",
        "error_type": "missed_extraction",
        "document_type": "invoice",
    }
    resp = await client.post("/api/v1/quality/golden-drafts", json=payload)
    assert resp.status_code == 404
    assert len(db.drafts) == 0


@pytest.mark.asyncio
async def test_list_filters_by_org(app_with_overrides, client):
    _, db, set_user = app_with_overrides
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    set_user(uuid.uuid4(), org_a)

    doc_a = uuid.uuid4()
    doc_b = uuid.uuid4()
    db.documents[doc_a] = _DocStub(id=doc_a, org_id=org_a)
    db.documents[doc_b] = _DocStub(id=doc_b, org_id=org_b)

    # Seed drafts directly (bypass POST so we can plant cross-org data).
    from app.models.golden_case_draft import GoldenCaseDraft, GoldenDraftStatus

    for org, doc in ((org_a, doc_a), (org_b, doc_b), (org_a, doc_a)):
        d = GoldenCaseDraft(
            org_id=org,
            document_id=doc,
            created_by_user_id=None,
            field_name="f",
            corrected_value="v",
            error_type="manual_correction",
            document_type="invoice",
            status=GoldenDraftStatus.DRAFT,
        )
        db.add(d)

    resp = await client.get("/api/v1/quality/golden-drafts")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    for item in body:
        assert item["org_id"] == str(org_a)


@pytest.mark.asyncio
async def test_list_filters_by_status_and_doc_type(app_with_overrides, client):
    _, db, set_user = app_with_overrides
    org_id = uuid.uuid4()
    set_user(uuid.uuid4(), org_id)

    from app.models.golden_case_draft import GoldenCaseDraft, GoldenDraftStatus

    seed = [
        ("invoice", GoldenDraftStatus.DRAFT, "wrong_extraction"),
        ("invoice", GoldenDraftStatus.ACCEPTED, "wrong_extraction"),
        ("contract", GoldenDraftStatus.DRAFT, "missed_field"),
    ]
    for doc_type, status_val, err in seed:
        d = GoldenCaseDraft(
            org_id=org_id,
            document_id=uuid.uuid4(),
            created_by_user_id=None,
            field_name="f",
            corrected_value="v",
            error_type=err,
            document_type=doc_type,
            status=status_val,
        )
        db.add(d)

    resp = await client.get(
        "/api/v1/quality/golden-drafts?status=draft&document_type=invoice"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["document_type"] == "invoice"
    assert body[0]["status"] == "draft"

    resp = await client.get(
        "/api/v1/quality/golden-drafts?error_type=missed_field"
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_status_change_updates_persisted_draft(
    app_with_overrides, client
):
    _, db, set_user = app_with_overrides
    org_id = uuid.uuid4()
    set_user(uuid.uuid4(), org_id)

    from app.models.golden_case_draft import GoldenCaseDraft, GoldenDraftStatus

    d = GoldenCaseDraft(
        org_id=org_id,
        document_id=uuid.uuid4(),
        created_by_user_id=None,
        field_name="total_ttc",
        corrected_value="1234.56",
        error_type="wrong_extraction",
        document_type="invoice",
        status=GoldenDraftStatus.DRAFT,
    )
    db.add(d)

    resp = await client.patch(
        f"/api/v1/quality/golden-drafts/{d.id}/status",
        json={"status": "accepted"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
    assert db.drafts[d.id].status == GoldenDraftStatus.ACCEPTED


@pytest.mark.asyncio
async def test_status_change_blocked_for_other_org(app_with_overrides, client):
    _, db, set_user = app_with_overrides
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    set_user(uuid.uuid4(), org_a)

    from app.models.golden_case_draft import GoldenCaseDraft, GoldenDraftStatus

    other_draft = GoldenCaseDraft(
        org_id=org_b,
        document_id=uuid.uuid4(),
        created_by_user_id=None,
        field_name="x",
        corrected_value="y",
        error_type="wrong_extraction",
        document_type="invoice",
        status=GoldenDraftStatus.DRAFT,
    )
    db.add(other_draft)

    resp = await client.patch(
        f"/api/v1/quality/golden-drafts/{other_draft.id}/status",
        json={"status": "accepted"},
    )
    assert resp.status_code == 404
    assert db.drafts[other_draft.id].status == GoldenDraftStatus.DRAFT


@pytest.mark.asyncio
async def test_status_change_invalid_value_returns_422(
    app_with_overrides, client
):
    _, db, set_user = app_with_overrides
    set_user(uuid.uuid4(), uuid.uuid4())

    resp = await client.patch(
        f"/api/v1/quality/golden-drafts/{uuid.uuid4()}/status",
        json={"status": "archived"},
    )
    assert resp.status_code == 422
