"""ConfiDoc — PseudonymMapping model.

Stores the reversible mapping from [PERSONNE_1] -> real identity.
Encrypted at rest with Fernet. Separate from document content.
Access restricted to document owner + explicit validation step.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class PseudonymMapping(BaseModel):
    __tablename__ = "pseudonym_mappings"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Encrypted JSON blob: {"[PERSONNE_1]": "BARANES GREGORY", ...}
    encrypted_mapping: Mapped[str] = mapped_column(Text, nullable=False)
    # Expiration: mapping auto-deleted after this date
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True,
    )
    # Human validation flag: must be True before export is allowed in high-risk
    human_validated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    validated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    # Risk snapshot at time of anonymization
    risk_score: Mapped[float | None] = mapped_column(nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
