"""DB schema strategy: auto-init is gated by DB_AUTO_INIT (Alembic owns prod)."""

from types import SimpleNamespace

import pytest

from app.config import Settings
from app.core import database as db


def test_db_auto_init_defaults_true():
    assert Settings().DB_AUTO_INIT is True


@pytest.mark.anyio
async def test_init_database_is_noop_when_auto_init_disabled(monkeypatch):
    """With DB_AUTO_INIT=False, init_database must not touch the engine."""
    monkeypatch.setattr(db, "settings", SimpleNamespace(DB_AUTO_INIT=False))

    class _Boom:
        def begin(self):
            raise AssertionError("engine must not be used when DB_AUTO_INIT is False")

    monkeypatch.setattr(db, "engine", _Boom())
    # Should return cleanly without connecting.
    await db.init_database()
