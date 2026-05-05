"""Regression tests for document-level multi-tenant RBAC."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from app.services import rbac_service
from app.services.rbac_service import RoleContext


def _document(*, org_id: uuid.UUID | None, uploaded_by: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(org_id=org_id, uploaded_by_user_id=uploaded_by)


@pytest.mark.asyncio
async def test_org_viewer_can_read_but_cannot_delete_document(monkeypatch) -> None:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    document = _document(org_id=org_id, uploaded_by=uuid.uuid4())

    async def fake_context(_db: Any, *, user_id: uuid.UUID, org_id: uuid.UUID | None):
        return RoleContext(
            org_id=org_id,
            user_id=user_id,
            role_name="viewer",
            permissions=frozenset(),
        )

    monkeypatch.setattr(rbac_service, "get_org_role_context", fake_context)

    await rbac_service.require_document_permission(
        None,
        user_id=user_id,
        document=document,
        permission="documents.read",
    )

    with pytest.raises(HTTPException) as exc_info:
        await rbac_service.require_document_permission(
            None,
            user_id=user_id,
            document=document,
            permission="documents.delete",
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_member_cannot_administer_org_document(monkeypatch) -> None:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    document = _document(org_id=org_id, uploaded_by=uuid.uuid4())

    async def fake_context(_db: Any, *, user_id: uuid.UUID, org_id: uuid.UUID | None):
        return RoleContext(
            org_id=org_id,
            user_id=user_id,
            role_name="member",
            permissions=frozenset(),
        )

    monkeypatch.setattr(rbac_service, "get_org_role_context", fake_context)

    with pytest.raises(HTTPException) as exc_info:
        await rbac_service.require_document_permission(
            None,
            user_id=user_id,
            document=document,
            permission="members.manage",
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_owner_can_delete_org_document(monkeypatch) -> None:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    document = _document(org_id=org_id, uploaded_by=uuid.uuid4())

    async def fake_context(_db: Any, *, user_id: uuid.UUID, org_id: uuid.UUID | None):
        return RoleContext(
            org_id=org_id,
            user_id=user_id,
            role_name="owner",
            permissions=frozenset(),
        )

    monkeypatch.setattr(rbac_service, "get_org_role_context", fake_context)

    await rbac_service.require_document_permission(
        None,
        user_id=user_id,
        document=document,
        permission="documents.delete",
    )


@pytest.mark.asyncio
async def test_cross_org_user_without_membership_is_denied(monkeypatch) -> None:
    user_id = uuid.uuid4()
    document = _document(org_id=uuid.uuid4(), uploaded_by=uuid.uuid4())

    async def no_context(_db: Any, *, user_id: uuid.UUID, org_id: uuid.UUID | None):
        return None

    monkeypatch.setattr(rbac_service, "get_org_role_context", no_context)

    with pytest.raises(HTTPException) as exc_info:
        await rbac_service.require_document_permission(
            None,
            user_id=user_id,
            document=document,
            permission="documents.read",
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_legacy_personal_document_remains_owner_only() -> None:
    owner_id = uuid.uuid4()
    document = _document(org_id=None, uploaded_by=owner_id)

    await rbac_service.require_document_permission(
        None,
        user_id=owner_id,
        document=document,
        permission="documents.delete",
    )

    with pytest.raises(HTTPException) as exc_info:
        await rbac_service.require_document_permission(
            None,
            user_id=uuid.uuid4(),
            document=document,
            permission="documents.read",
        )
    assert exc_info.value.status_code == 403
