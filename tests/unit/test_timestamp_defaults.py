"""Tests for model timestamp defaults."""

from __future__ import annotations

from app.models.client import Client
from app.models.dossier import Dossier


def test_tenant_models_have_application_timestamp_defaults():
    for model in (Client, Dossier):
        assert model.__table__.c.created_at.default is not None
        assert model.__table__.c.updated_at.default is not None
        assert model.__table__.c.created_at.server_default is not None
        assert model.__table__.c.updated_at.server_default is not None
