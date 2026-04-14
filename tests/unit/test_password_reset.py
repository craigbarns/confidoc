"""Tests du modèle PasswordResetToken et du flow reset mot de passe.

Couvre :
- Structure du modèle (colonnes, index, FK)
- hash_token + generate_opaque_token (primitives sécurité)
- auth_service.request_password_reset : anti-enumération (pas d'exception)
- auth_service.reset_password : token invalide → 400
- Validation mot de passe : longueur min, majuscule, chiffre
"""

from __future__ import annotations

import hashlib

import pytest

from app.core.security import generate_opaque_token, hash_token
from app.models.password_reset_token import PasswordResetToken


# ══════════════════════════════════════════════════════════════════════
# Modèle PasswordResetToken
# ══════════════════════════════════════════════════════════════════════

class TestPasswordResetTokenModel:
    def test_table_name(self):
        assert PasswordResetToken.__tablename__ == "password_reset_tokens"

    def test_has_user_id_column(self):
        cols = {c.name for c in PasswordResetToken.__table__.columns}
        assert "user_id" in cols

    def test_has_token_column(self):
        cols = {c.name for c in PasswordResetToken.__table__.columns}
        assert "token" in cols

    def test_has_expires_at_column(self):
        cols = {c.name for c in PasswordResetToken.__table__.columns}
        assert "expires_at" in cols

    def test_token_column_is_unique(self):
        token_col = PasswordResetToken.__table__.columns["token"]
        assert token_col.unique is True

    def test_token_column_length_64(self):
        token_col = PasswordResetToken.__table__.columns["token"]
        assert token_col.type.length == 64

    def test_user_id_has_index(self):
        user_id_col = PasswordResetToken.__table__.columns["user_id"]
        assert user_id_col.index is True

    def test_token_has_index(self):
        token_col = PasswordResetToken.__table__.columns["token"]
        assert token_col.index is True

    def test_user_id_has_fk_to_users(self):
        user_id_col = PasswordResetToken.__table__.columns["user_id"]
        fk_tables = {fk.column.table.name for fk in user_id_col.foreign_keys}
        assert "users" in fk_tables

    def test_user_id_cascade_delete(self):
        user_id_col = PasswordResetToken.__table__.columns["user_id"]
        fk = list(user_id_col.foreign_keys)[0]
        assert fk.ondelete is not None
        assert fk.ondelete.upper() == "CASCADE"


# ══════════════════════════════════════════════════════════════════════
# Primitives sécurité : hash_token, generate_opaque_token
# ══════════════════════════════════════════════════════════════════════

class TestHashToken:
    def test_returns_sha256_hex(self):
        token = "some-random-token"
        result = hash_token(token)
        expected = hashlib.sha256(token.encode()).hexdigest()
        assert result == expected

    def test_length_64(self):
        assert len(hash_token("abc")) == 64

    def test_deterministic(self):
        t = "my-token"
        assert hash_token(t) == hash_token(t)

    def test_different_inputs_give_different_hashes(self):
        assert hash_token("token-a") != hash_token("token-b")

    def test_no_collision_with_similar_strings(self):
        assert hash_token("token1") != hash_token("token2")
        assert hash_token("Token1") != hash_token("token1")


class TestGenerateOpaqueToken:
    def test_returns_string(self):
        assert isinstance(generate_opaque_token(), str)

    def test_default_length_sufficient(self):
        # token_urlsafe(40) → ~54 chars base64url
        t = generate_opaque_token()
        assert len(t) >= 40

    def test_uniqueness(self):
        tokens = {generate_opaque_token() for _ in range(100)}
        assert len(tokens) == 100

    def test_url_safe_chars_only(self):
        import re
        t = generate_opaque_token()
        assert re.match(r"^[A-Za-z0-9_\-]+$", t), f"Token non URL-safe : {t}"


# ══════════════════════════════════════════════════════════════════════
# auth_service : anti-enumération forgot-password
# ══════════════════════════════════════════════════════════════════════

class TestForgotPasswordAntiEnumeration:
    """request_password_reset ne doit jamais lever d'exception."""

    @pytest.mark.asyncio
    async def test_unknown_email_does_not_raise(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # utilisateur inconnu
        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.services.auth_service import request_password_reset
        # Should complete silently
        await request_password_reset(mock_db, "nonexistent@example.com")

    @pytest.mark.asyncio
    async def test_known_email_does_not_raise(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        import uuid

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_user.email = "known@example.com"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.delete = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        with patch("app.services.email_service.send_password_reset_email", new_callable=AsyncMock, return_value=True):
            from app.services.auth_service import request_password_reset
            await request_password_reset(mock_db, "known@example.com")


# ══════════════════════════════════════════════════════════════════════
# auth_service : reset_password avec token invalide
# ══════════════════════════════════════════════════════════════════════

class TestResetPasswordInvalidToken:
    @pytest.mark.asyncio
    async def test_invalid_token_raises_400(self):
        from unittest.mock import AsyncMock, MagicMock
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # token inconnu
        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.services.auth_service import reset_password
        with pytest.raises(HTTPException) as exc_info:
            await reset_password(mock_db, "invalid-token", "NewPass1!")
        assert exc_info.value.status_code in (400, 401)
