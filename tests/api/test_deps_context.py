"""Tests for API dependency request context."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.api import deps


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def first(self):
        return self.value


class _Db:
    def __init__(self, *values):
        self.results = [_Result(value) for value in values]

    async def execute(self, _stmt):
        return self.results.pop(0)


@pytest.mark.anyio
async def test_current_user_exposes_current_org_id(monkeypatch):
    org_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), is_active=True, is_platform_admin=False)
    membership = SimpleNamespace(org_id=org_id)
    request = Request({"type": "http", "headers": []})

    monkeypatch.setattr(deps, "decode_access_token", lambda _token: {"sub": str(user.id)})

    current_user = await deps.get_current_user(request, _Db(user, membership), token="jwt-token")

    assert current_user is user
    assert current_user.org_id == org_id
    assert request.state.org_id == org_id
