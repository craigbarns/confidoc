"""Tests for upload endpoints."""

import pytest


class TestUploadValidation:
    """Test file upload validation logic."""

    @pytest.mark.asyncio
    async def test_upload_requires_auth(self, client):
        resp = await client.post("/api/v1/uploads")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_no_file(self, client):
        resp = await client.post(
            "/api/v1/uploads",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code in (401, 422)

    def test_upload_profile_allows_railway_smoke_profiles(self):
        from typing import get_args

        from app.api.v1.uploads import AnonymizationProfile

        profiles = set(get_args(AnonymizationProfile))
        assert "dataset_accounting" in profiles
        assert "dataset_accounting_pseudo" in profiles


class TestUploadExtension:
    """Test extension validation."""

    def test_allowed_extensions_from_config(self):
        from app.config import get_settings

        settings = get_settings()
        assert "pdf" in settings.ALLOWED_EXTENSIONS
        assert "png" in settings.ALLOWED_EXTENSIONS
        assert "exe" not in settings.ALLOWED_EXTENSIONS

    def test_max_upload_size(self):
        from app.config import get_settings

        settings = get_settings()
        assert settings.max_upload_size_bytes == settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        assert settings.max_upload_size_bytes > 0
