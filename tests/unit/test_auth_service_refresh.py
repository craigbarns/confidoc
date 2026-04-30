"""Tests refresh token rotation (concurrent use / idempotent delete)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.services import auth_service


def _valid_rt() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        is_revoked=False,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )


@pytest.mark.asyncio
async def test_refresh_concurrent_delete_zero_rows_401_and_rollback(monkeypatch):
    """Si le DELETE ne matche pas (course parallèle), 401 + rollback — pas de SAWarning."""
    rt = _valid_rt()

    select_result = MagicMock()
    select_result.scalar_one_or_none.return_value = rt

    delete_result = MagicMock()
    delete_result.rowcount = 0

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[select_result, delete_result])
    db.rollback = AsyncMock()

    monkeypatch.setattr(
        auth_service, "hash_token", lambda _v: "hashed"
    )

    with pytest.raises(HTTPException) as exc:
        await auth_service.refresh_access_token(db, "opaque-refresh")
    assert exc.value.status_code == 401
    assert "déjà utilisé" in exc.value.detail
    db.rollback.assert_awaited_once()
    db.run_sync.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_success_expunges_after_delete(monkeypatch):
    """Après DELETE réussi, expunge pour éviter un second DELETE ORM au flush."""
    rt = _valid_rt()
    user = SimpleNamespace(id=rt.user_id, is_active=True)

    select_rt = MagicMock()
    select_rt.scalar_one_or_none.return_value = rt
    select_user = MagicMock()
    select_user.scalar_one.return_value = user

    delete_result = MagicMock()
    delete_result.rowcount = 1

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[select_rt, delete_result, select_user])
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.run_sync = AsyncMock()

    monkeypatch.setattr(auth_service, "hash_token", lambda _v: "hashed")
    monkeypatch.setattr(auth_service, "generate_opaque_token", lambda: "new-rt")
    monkeypatch.setattr(auth_service, "create_access_token", lambda _uid: "access-jwt")

    out = await auth_service.refresh_access_token(db, "opaque-refresh")
    assert out.access_token == "access-jwt"
    assert out.refresh_token == "new-rt"
    db.run_sync.assert_awaited_once()
    db.commit.assert_awaited_once()
