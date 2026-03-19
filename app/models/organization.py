"""ConfiDoc Backend — Organization model."""

from enum import Enum as PyEnum
from typing import Any

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class ProfessionType(str, PyEnum):
    CABINET_COMPTABLE = "cabinet_comptable"
    NOTAIRE = "notaire"
    AVOCAT = "avocat"
    AUDITEUR = "auditeur"
    AUTRE = "autre"


class PlanType(str, PyEnum):
    TRIAL = "trial"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class Organization(BaseModel):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    profession_type: Mapped[ProfessionType] = mapped_column(
        Enum(ProfessionType), default=ProfessionType.AUTRE, index=True
    )
    plan: Mapped[PlanType] = mapped_column(Enum(PlanType), default=PlanType.TRIAL)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    settings: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    memberships = relationship("Membership", back_populates="organization", cascade="all, delete-orphan")
    roles = relationship("Role", back_populates="organization", cascade="all, delete-orphan")
