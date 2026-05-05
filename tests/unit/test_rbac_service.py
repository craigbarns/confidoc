"""Tests for organization RBAC role semantics."""

from __future__ import annotations

from app.services.rbac_service import (
    normalize_role_name,
    role_at_least,
    role_has_permission,
)


def test_role_aliases_match_b2b_role_model() -> None:
    assert normalize_role_name("operator") == "member"
    assert normalize_role_name("auditor") == "viewer"
    assert normalize_role_name("owner") == "owner"


def test_role_hierarchy_owner_admin_member_viewer() -> None:
    assert role_at_least("owner", "admin") is True
    assert role_at_least("admin", "member") is True
    assert role_at_least("member", "viewer") is True
    assert role_at_least("viewer", "member") is False


def test_viewer_can_read_but_cannot_delete_or_administer() -> None:
    assert role_has_permission("viewer", None, "documents.read") is True
    assert role_has_permission("viewer", None, "documents.delete") is False
    assert role_has_permission("viewer", None, "org.manage") is False


def test_member_can_operate_documents_but_not_manage_org() -> None:
    assert role_has_permission("member", None, "documents.upload") is True
    assert role_has_permission("member", None, "documents.process") is True
    assert role_has_permission("member", None, "members.manage") is False


def test_admin_document_wildcard_and_owner_global_wildcard() -> None:
    assert role_has_permission("admin", None, "documents.delete") is True
    assert role_has_permission("admin", None, "exports.download") is True
    assert role_has_permission("owner", None, "members.manage") is True
