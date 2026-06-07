"""Regression tests for PostgreSQL tenant RLS hardening."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.rls import set_rls_bypass, set_rls_context


class _FakeDb:
    def __init__(self, dialect_name: str | None = "postgresql") -> None:
        self._bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect_name))
        self.executed = []

    def get_bind(self):
        return self._bind

    async def execute(self, stmt):
        self.executed.append(stmt)


def _compiled_params(stmt) -> dict:
    return dict(stmt.compile().params)


@pytest.mark.asyncio
async def test_set_rls_context_sets_transaction_local_org_and_user() -> None:
    db = _FakeDb()
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()

    await set_rls_context(db, org_id=org_id, user_id=user_id)

    assert len(db.executed) == 3
    statements = [str(stmt) for stmt in db.executed]
    assert "app.current_org_id" in statements[0]
    assert "app.current_user_id" in statements[1]
    assert "app.rls_bypass" in statements[2]
    assert _compiled_params(db.executed[0])["org_id"] == str(org_id)
    assert _compiled_params(db.executed[1])["user_id"] == str(user_id)
    assert _compiled_params(db.executed[2])["value"] == "off"


@pytest.mark.asyncio
async def test_set_rls_bypass_is_transaction_local() -> None:
    db = _FakeDb()

    await set_rls_bypass(db, enabled=True)

    assert len(db.executed) == 1
    assert "set_config('app.rls_bypass'" in str(db.executed[0])
    assert _compiled_params(db.executed[0])["value"] == "on"


@pytest.mark.asyncio
async def test_rls_helpers_skip_non_postgres_sessions() -> None:
    db = _FakeDb(dialect_name="sqlite")

    await set_rls_context(db, org_id=uuid.uuid4(), user_id=uuid.uuid4())
    await set_rls_bypass(db, enabled=True)

    assert db.executed == []


def test_rls_migration_forces_tenant_policies_on_business_tables() -> None:
    root = Path(__file__).resolve().parents[2]
    migration = (
        root / "alembic" / "versions" / "e5f6a7b8c9d0_enable_tenant_rls.py"
    ).read_text(encoding="utf-8")
    normalized = " ".join(migration.split())

    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "confidoc_rls_current_org_id" in migration
    assert "confidoc_rls_current_user_id" in migration
    assert "confidoc_rls_bypass" in migration
    assert "uploaded_by_user_id = public.confidoc_rls_current_user_id()" in normalized
    assert 'owner_column="created_by_user_id"' in migration
    for table in (
        "documents",
        "document_versions",
        "entity_detections",
        "pseudonym_mappings",
        "clients",
        "dossiers",
        "golden_case_drafts",
        "api_keys",
        "webhook_endpoints",
        "webhook_deliveries",
        "audit_logs",
    ):
        assert f'"{table}"' in migration

    # Auth discovery tables stay outside this first RLS layer; otherwise login
    # cannot resolve the current organization before the DB context is set.
    assert '"memberships"' not in migration
    assert '"roles"' not in migration
    assert '"organizations"' not in migration
