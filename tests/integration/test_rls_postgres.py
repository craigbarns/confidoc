"""PostgreSQL integration tests for tenant Row Level Security."""

from __future__ import annotations

import importlib
import os
import uuid
from collections.abc import Iterable

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

pytestmark = pytest.mark.postgres

APP_ROLE = "confidoc_rls_test_app"
APP_PASSWORD = "confidoc_rls_test_password"


def _database_url() -> str:
    url = os.getenv("TEST_POSTGRES_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("TEST_POSTGRES_DATABASE_URL is not set")
    return url


def _app_database_url(admin_url: str) -> str:
    url = make_url(admin_url)
    return url.set(username=APP_ROLE, password=APP_PASSWORD).render_as_string(hide_password=False)


async def _execute_many(conn: AsyncConnection, statements: Iterable[str]) -> None:
    for statement in statements:
        await conn.execute(text(statement))


def _run_rls_migration(sync_conn) -> None:
    migration = importlib.import_module("alembic.versions.e5f6a7b8c9d0_enable_tenant_rls")
    context = MigrationContext.configure(sync_conn)
    with Operations.context(context):
        migration.upgrade()


async def _reset_database(admin_url: str) -> None:
    engine = create_async_engine(admin_url, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            await _execute_many(
                conn,
                (
                    "DROP SCHEMA IF EXISTS public CASCADE",
                    "CREATE SCHEMA public",
                    f"DROP ROLE IF EXISTS {APP_ROLE}",
                    f"CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_PASSWORD}'",
                    "GRANT USAGE ON SCHEMA public TO public",
                ),
            )

            await _execute_many(
                conn,
                (
                    """
                    CREATE TABLE organizations (
                        id uuid PRIMARY KEY,
                        name text NOT NULL,
                        slug text NOT NULL
                    )
                    """,
                    """
                    CREATE TABLE users (
                        id uuid PRIMARY KEY,
                        email text NOT NULL
                    )
                    """,
                    """
                    CREATE TABLE documents (
                        id uuid PRIMARY KEY,
                        org_id uuid NULL REFERENCES organizations(id),
                        uploaded_by_user_id uuid NOT NULL REFERENCES users(id),
                        original_filename text NOT NULL
                    )
                    """,
                    """
                    CREATE TABLE document_versions (
                        id uuid PRIMARY KEY,
                        document_id uuid NOT NULL REFERENCES documents(id),
                        content_text text NOT NULL
                    )
                    """,
                ),
            )

            await conn.run_sync(_run_rls_migration)

            await _execute_many(
                conn,
                (
                    f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}",
                    f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {APP_ROLE}",
                ),
            )
    finally:
        await engine.dispose()


async def _seed_two_orgs(admin_url: str) -> dict[str, uuid.UUID]:
    ids = {
        "org_a": uuid.uuid4(),
        "org_b": uuid.uuid4(),
        "user_a": uuid.uuid4(),
        "user_b": uuid.uuid4(),
        "doc_a": uuid.uuid4(),
        "doc_b": uuid.uuid4(),
        "legacy_a": uuid.uuid4(),
        "legacy_b": uuid.uuid4(),
        "version_a": uuid.uuid4(),
        "version_b": uuid.uuid4(),
    }
    engine = create_async_engine(admin_url, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO organizations (id, name, slug)
                    VALUES (:org_a, 'Cabinet A', 'cabinet-a'), (:org_b, 'Cabinet B', 'cabinet-b')
                    """
                ),
                ids,
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO users (id, email)
                    VALUES (:user_a, 'a@confidoc.test'), (:user_b, 'b@confidoc.test')
                    """
                ),
                ids,
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO documents (id, org_id, uploaded_by_user_id, original_filename)
                    VALUES
                        (:doc_a, :org_a, :user_a, 'org-a.pdf'),
                        (:doc_b, :org_b, :user_b, 'org-b.pdf'),
                        (:legacy_a, NULL, :user_a, 'legacy-a.pdf'),
                        (:legacy_b, NULL, :user_b, 'legacy-b.pdf')
                    """
                ),
                ids,
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO document_versions (id, document_id, content_text)
                    VALUES
                        (:version_a, :doc_a, 'version org A'),
                        (:version_b, :doc_b, 'version org B')
                    """
                ),
                ids,
            )
    finally:
        await engine.dispose()
    return ids


async def _visible_document_filenames(
    conn: AsyncConnection,
    *,
    org_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    bypass: bool = False,
) -> list[str]:
    await conn.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(org_id) if org_id else ""},
    )
    await conn.execute(
        text("SELECT set_config('app.current_user_id', :user_id, true)"),
        {"user_id": str(user_id) if user_id else ""},
    )
    await conn.execute(
        text("SELECT set_config('app.rls_bypass', :bypass, true)"),
        {"bypass": "on" if bypass else "off"},
    )
    result = await conn.execute(
        text("SELECT original_filename FROM documents ORDER BY original_filename")
    )
    return list(result.scalars().all())


async def _visible_version_texts(
    conn: AsyncConnection,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[str]:
    await conn.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(org_id)},
    )
    await conn.execute(
        text("SELECT set_config('app.current_user_id', :user_id, true)"),
        {"user_id": str(user_id)},
    )
    await conn.execute(text("SELECT set_config('app.rls_bypass', 'off', true)"))
    result = await conn.execute(text("SELECT content_text FROM document_versions"))
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_postgres_rls_isolates_two_orgs_and_fails_closed() -> None:
    admin_url = _database_url()
    await _reset_database(admin_url)
    ids = await _seed_two_orgs(admin_url)

    app_engine = create_async_engine(_app_database_url(admin_url), pool_pre_ping=True)
    try:
        async with app_engine.begin() as conn:
            assert await _visible_document_filenames(conn) == []

        async with app_engine.begin() as conn:
            assert await _visible_document_filenames(
                conn,
                org_id=ids["org_a"],
                user_id=ids["user_a"],
            ) == ["legacy-a.pdf", "org-a.pdf"]

        async with app_engine.begin() as conn:
            assert await _visible_document_filenames(
                conn,
                org_id=ids["org_b"],
                user_id=ids["user_b"],
            ) == ["legacy-b.pdf", "org-b.pdf"]

        async with app_engine.begin() as conn:
            assert await _visible_version_texts(
                conn,
                org_id=ids["org_a"],
                user_id=ids["user_a"],
            ) == ["version org A"]

        async with app_engine.begin() as conn:
            assert await _visible_document_filenames(conn, bypass=True) == [
                "legacy-a.pdf",
                "legacy-b.pdf",
                "org-a.pdf",
                "org-b.pdf",
            ]
    finally:
        await app_engine.dispose()
