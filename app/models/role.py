"""ConfiDoc Backend — Role model."""

from typing import Optional
import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Role(BaseModel):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uix_role_org_id_name"),
    )

    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    organization = relationship("Organization", back_populates="roles")
    memberships = relationship("Membership", back_populates="role")
