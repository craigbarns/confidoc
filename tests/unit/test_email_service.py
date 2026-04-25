"""Tests du service email (app.services.email_service).

Couvre :
- Mode dev : log le lien si SMTP_HOST absent (hors production)
- Mode prod sans SMTP : retourne False silencieusement
- Envoi réel avec SMTP (mock smtplib)
- Timeout/erreur SMTP retourne False (pas d'exception levée)
"""

from __future__ import annotations

import smtplib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_settings(smtp_host="", is_production=False, smtp_tls=True):
    s = MagicMock()
    s.SMTP_HOST = smtp_host
    s.SMTP_PORT = 587
    s.SMTP_USER = "user@example.com"
    s.SMTP_PASSWORD = "password"
    s.SMTP_FROM = "noreply@example.com"
    s.SMTP_TLS = smtp_tls
    s.is_production = is_production
    s.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 30
    s.APP_BASE_URL = "https://confidoc.test"
    return s


class TestEmailServiceDevMode:
    """En dev sans SMTP, le lien est loggé et retourne True."""

    @pytest.mark.asyncio
    async def test_dev_mode_returns_true(self):
        settings = _make_settings(smtp_host="", is_production=False)
        with patch("app.services.email_service.get_settings", return_value=settings):
            from app.services import email_service
            result = await email_service.send_password_reset_email(
                "user@test.com", "https://example.com/reset?token=abc"
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_dev_mode_does_not_raise(self):
        settings = _make_settings(smtp_host="", is_production=False)
        with patch("app.services.email_service.get_settings", return_value=settings):
            from app.services import email_service
            try:
                await email_service.send_password_reset_email(
                    "anyone@domain.org", "http://localhost/reset?token=xyz"
                )
            except Exception as e:
                pytest.fail(f"Ne doit pas lever d'exception : {e}")


class TestEmailServiceProductionNoSMTP:
    """En production sans SMTP, retourne False silencieusement."""

    @pytest.mark.asyncio
    async def test_prod_no_smtp_returns_false(self):
        settings = _make_settings(smtp_host="", is_production=True)
        with patch("app.services.email_service.get_settings", return_value=settings):
            from app.services import email_service
            result = await email_service.send_password_reset_email(
                "user@test.com", "https://example.com/reset?token=abc"
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_prod_no_smtp_does_not_raise(self):
        settings = _make_settings(smtp_host="", is_production=True)
        with patch("app.services.email_service.get_settings", return_value=settings):
            from app.services import email_service
            try:
                await email_service.send_password_reset_email(
                    "user@test.com", "https://example.com/reset"
                )
            except Exception as e:
                pytest.fail(f"Ne doit pas lever d'exception : {e}")


class TestEmailServiceSMTP:
    """Avec SMTP configuré, utilise smtplib (mock)."""

    def _smtp_ctx_manager(self):
        mock_server = MagicMock()
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)
        return mock_server

    @pytest.mark.asyncio
    async def test_smtp_tls_send_returns_true(self):
        settings = _make_settings(smtp_host="smtp.example.com", is_production=False, smtp_tls=True)
        mock_server = self._smtp_ctx_manager()

        with patch("app.services.email_service.get_settings", return_value=settings), \
             patch("smtplib.SMTP", return_value=mock_server):
            from app.services import email_service
            result = await email_service.send_password_reset_email(
                "dest@test.com", "https://app.io/reset?token=tok"
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_smtp_calls_sendmail(self):
        settings = _make_settings(smtp_host="smtp.example.com", is_production=False, smtp_tls=True)
        mock_server = self._smtp_ctx_manager()

        with patch("app.services.email_service.get_settings", return_value=settings), \
             patch("smtplib.SMTP", return_value=mock_server):
            from app.services import email_service
            await email_service.send_password_reset_email(
                "dest@test.com", "https://app.io/reset?token=tok"
            )
            mock_server.sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_smtp_error_returns_false(self):
        settings = _make_settings(smtp_host="smtp.example.com", is_production=False, smtp_tls=True)

        with patch("app.services.email_service.get_settings", return_value=settings), \
             patch("smtplib.SMTP", side_effect=smtplib.SMTPException("connexion refusée")):
            from app.services import email_service
            result = await email_service.send_password_reset_email(
                "dest@test.com", "https://app.io/reset?token=tok"
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_smtp_timeout_returns_false(self):
        settings = _make_settings(smtp_host="smtp.example.com", is_production=False, smtp_tls=True)

        with patch("app.services.email_service.get_settings", return_value=settings), \
             patch("smtplib.SMTP", side_effect=TimeoutError("timeout")):
            from app.services import email_service
            result = await email_service.send_password_reset_email(
                "dest@test.com", "https://app.io/reset"
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_beta_welcome_email_uses_smtp(self):
        settings = _make_settings(smtp_host="smtp.example.com", is_production=False, smtp_tls=True)
        mock_server = self._smtp_ctx_manager()

        with patch("app.services.email_service.get_settings", return_value=settings), \
             patch("smtplib.SMTP", return_value=mock_server):
            from app.services import email_service
            result = await email_service.send_beta_welcome_email(
                {
                    "email": "dest@test.com",
                    "full_name": "Marie Martin",
                    "company": "Cabinet Martin",
                    "use_case": "Anonymisation de bilans clients",
                }
            )
            assert result is True
            mock_server.sendmail.assert_called_once()
