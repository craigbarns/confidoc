"""Organization RBAC helpers for B2B multi-tenant access control.

ConfiDoc uses explicit memberships and role permissions. This module keeps the
product-facing roles simple:

- owner: full organization control
- admin: operational administration
- member: upload/process/export documents
- viewer: read anonymized outputs only

Legacy seeded roles are normalized: ``operator`` behaves as ``member`` and
``auditor`` behaves as a read/audit role.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import http_403
from app.models.document import Document
from app.models.membership import Membership
from app.models.role import Role

ROLE_ALIASES = {
    "operator": "member",
    "auditor": "viewer",
}

ROLE_RANK = {
    "viewer": 10,
    "member": 20,
    "admin": 30,
    "owner": 40,
}

BASELINE_PERMISSIONS = {
    "viewer": {
        "documents.read",
        "exports.read",
        "exports.download",
    },
    "member": {
        "documents.read",
        "documents.raw",
        "documents.upload",
        "documents.process",
        "documents.validate",
        "documents.metadata",
        "exports.read",
        "exports.create",
        "exports.download",
        "audit.read",
    },
    "admin": {
        "documents.*",
        "exports.*",
        "audit.read",
        "audit.export",
        "org.manage",
        "members.manage",
        "policies.manage",
    },
    "owner": {"*"},
}


@dataclass(frozen=True)
class RoleContext:
    org_id: uuid.UUID
    user_id: uuid.UUID
    role_name: str
    permissions: frozenset[str]


def normalize_role_name(value: str | None) -> str:
    role = str(value or "viewer").strip().lower()
    return ROLE_ALIASES.get(role, role)


def role_at_least(role_name: str | None, minimum_role: str) -> bool:
    role = normalize_role_name(role_name)
    minimum = normalize_role_name(minimum_role)
    return ROLE_RANK.get(role, 0) >= ROLE_RANK.get(minimum, 0)


def role_has_permission(
    role_name: str | None,
    permissions: list[str] | tuple[str, ...] | set[str] | frozenset[str] | None,
    permission: str,
) -> bool:
    """Return whether a role grants a permission.

    Supports exact permissions, ``*`` and namespace wildcards such as
    ``documents.*``.
    """
    role = normalize_role_name(role_name)
    effective = set(BASELINE_PERMISSIONS.get(role, set()))
    effective.update(str(item) for item in (permissions or []) if item)

    if "*" in effective or permission in effective:
        return True

    namespace = permission.split(".", 1)[0]
    return f"{namespace}.*" in effective


async def get_org_role_context(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID | None,
) -> RoleContext | None:
    """Load active membership + role for an org."""
    if org_id is None:
        return None

    result = await db.execute(
        select(Membership, Role)
        .join(Role, Role.id == Membership.role_id)
        .where(
            Membership.user_id == user_id,
            Membership.org_id == org_id,
            Membership.is_active.is_(True),
        )
    )
    row = result.first()
    if row is None:
        return None

    membership, role = row
    role_name = normalize_role_name(getattr(role, "name", None))
    permissions = frozenset(str(item) for item in (getattr(role, "permissions", None) or []))
    return RoleContext(
        org_id=membership.org_id,
        user_id=membership.user_id,
        role_name=role_name,
        permissions=permissions,
    )


async def user_active_org_ids(db: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    result = await db.execute(
        select(Membership.org_id).where(
            Membership.user_id == user_id,
            Membership.is_active.is_(True),
        )
    )
    return [row[0] for row in result.all() if row[0]]


async def require_org_permission(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID | None,
    permission: str,
) -> RoleContext:
    context = await get_org_role_context(db, user_id=user_id, org_id=org_id)
    if context is None:
        raise http_403("Acces refuse: organisation non autorisee")
    if not role_has_permission(context.role_name, context.permissions, permission):
        raise http_403("Acces refuse: permission insuffisante")
    return context


async def require_document_permission(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    document: Document,
    permission: str,
) -> None:
    """Require a permission on a document.

    Documents without org_id keep owner-only legacy compatibility. Documents
    with org_id require an active organization membership.
    """
    if document.org_id is None:
        if document.uploaded_by_user_id == user_id:
            return
        raise http_403("Acces refuse: document non autorise")

    context = await require_org_permission(
        db,
        user_id=user_id,
        org_id=document.org_id,
        permission=permission,
    )

    if role_has_permission(context.role_name, context.permissions, permission):
        return
    raise http_403("Acces refuse: permission insuffisante")


def current_user_org_id(current_user: Any) -> uuid.UUID | None:
    value = getattr(current_user, "org_id", None)
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value)) if value else None
    except (TypeError, ValueError):
        return None
