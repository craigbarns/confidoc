"""ConfiDoc Backend — PasswordResetToken model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class PasswordResetToken(BaseModel):
    """Token à usage unique pour la réinitialisation de mot de passe.

    - Stocké haché (SHA-256) en base, comme les refresh tokens.
    - Expire après PASSWORD_RESET_TOKEN_EXPIRE_MINUTES minutes.
    - Consommé (supprimé) à la première utilisation réussie.
    - Tous les anciens tokens de l'utilisateur sont invalidés à chaque nouvelle demande.
    """

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(
        String(64),  # SHA-256 hex = 64 chars
        unique=True,
        index=True,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user = relationship("User")
