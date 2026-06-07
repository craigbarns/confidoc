"""PostgreSQL Row Level Security context helpers.

RLS policies read transaction-local settings. The values are intentionally
request-scoped via ``set_config(..., is_local=true)`` so pooled connections do
not keep tenant context after commit/rollback.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _dialect_name(db: AsyncSession) -> str | None:
    try:
        bind = db.get_bind()
        return getattr(getattr(bind, "dialect", None), "name", None)
    except Exception:
        return None


def _is_postgres(db: AsyncSession) -> bool:
    name = _dialect_name(db)
    return name in {None, "postgresql"}


def _uuid_setting(value: object | None) -> str:
    if value is None:
        return ""
    if isinstance(value, uuid.UUID):
        return str(value)
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError):
        return ""


async def set_rls_context(
    db: AsyncSession,
    *,
    org_id: object | None,
    user_id: object | None = None,
) -> None:
    """Set the current tenant/user context for the active DB transaction."""
    if not _is_postgres(db):
        return

    await db.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)").bindparams(
            org_id=_uuid_setting(org_id)
        )
    )
    await db.execute(
        text("SELECT set_config('app.current_user_id', :user_id, true)").bindparams(
            user_id=_uuid_setting(user_id)
        )
    )
    await set_rls_bypass(db, enabled=False)


async def commit_and_restore_rls_context(
    db: AsyncSession,
    *,
    org_id: object | None,
    user_id: object | None = None,
) -> None:
    """Commit, then restore RLS context for continued work on the same session."""
    await db.commit()
    await set_rls_context(db, org_id=org_id, user_id=user_id)


async def set_rls_bypass(db: AsyncSession, *, enabled: bool) -> None:
    """Set or clear service-level RLS bypass for the active DB transaction."""
    if not _is_postgres(db):
        return

    value = "on" if enabled else "off"
    await db.execute(
        text("SELECT set_config('app.rls_bypass', :value, true)").bindparams(value=value)
    )


@asynccontextmanager
async def rls_bypass(db: AsyncSession) -> AsyncIterator[None]:
    """Temporarily bypass RLS inside the current transaction."""
    await set_rls_bypass(db, enabled=True)
    try:
        yield
    finally:
        await set_rls_bypass(db, enabled=False)
