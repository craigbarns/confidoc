"""ConfiDoc Backend — Membership model."""

from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Membership(BaseModel):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uix_membership_user_org"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="memberships")
    organization = relationship("Organization", back_populates="memberships")
    role = relationship("Role", back_populates="memberships")
