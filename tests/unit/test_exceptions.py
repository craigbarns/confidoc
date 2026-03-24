"""Tests for exception helpers."""

from app.core.exceptions import (
    ConfiDocException,
    FileValidationError,
    NotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
    TenantIsolationError,
    http_400,
    http_401,
    http_403,
    http_404,
    http_409,
    http_413,
    http_500,
)


class TestCustomExceptions:
    def test_base_exception(self):
        exc = ConfiDocException("test error")
        assert str(exc) == "test error"

    def test_not_found_is_confidoc_exception(self):
        exc = NotFoundError("not found")
        assert isinstance(exc, ConfiDocException)

    def test_permission_denied(self):
        exc = PermissionDeniedError()
        assert isinstance(exc, ConfiDocException)

    def test_tenant_isolation(self):
        exc = TenantIsolationError("isolation breach")
        assert "isolation" in str(exc)

    def test_file_validation(self):
        exc = FileValidationError("bad file")
        assert isinstance(exc, ConfiDocException)

    def test_quota_exceeded(self):
        exc = QuotaExceededError("quota")
        assert isinstance(exc, ConfiDocException)


class TestHttpHelpers:
    def test_http_400(self):
        exc = http_400("bad request")
        assert exc.status_code == 400
        assert exc.detail == "bad request"

    def test_http_401(self):
        exc = http_401()
        assert exc.status_code == 401
        assert exc.headers == {"WWW-Authenticate": "Bearer"}

    def test_http_403(self):
        exc = http_403("forbidden")
        assert exc.status_code == 403

    def test_http_404(self):
        exc = http_404()
        assert exc.status_code == 404

    def test_http_409(self):
        exc = http_409("conflict")
        assert exc.status_code == 409

    def test_http_413(self):
        exc = http_413()
        assert exc.status_code == 413

    def test_http_500(self):
        exc = http_500()
        assert exc.status_code == 500

    def test_default_messages(self):
        assert http_400().detail == "Requête invalide"
        assert http_404().detail == "Ressource introuvable"
        assert http_500().detail == "Erreur interne"
