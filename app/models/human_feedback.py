"""ConfiDoc Backend — Tracking des corrections humaines (Human-in-the-loop)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class HumanFeedback(BaseModel):
    __tablename__ = "human_feedbacks"

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
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    
    # Metadata sur l'action
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)
    profile_used: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Ex: missed_entity, false_positive, wrong_entity_type, manual_mask_added, manual_unmask, field_correction
    feedback_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    # Valeurs hachées pour confidentialité
    original_value_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    corrected_value_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Métadonnées sur le tag
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    original_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    corrected_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    action_taken: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    # Coordonnées du texte (si applicable)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_span_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_span_end: Mapped[int | None] = mapped_column(Integer, nullable=True)

    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Workflow d'apprentissage métier
    applied_to_rules: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
