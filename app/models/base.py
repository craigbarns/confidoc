"""ConfiDoc Backend — Base model SQLAlchemy."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base déclarative pour tous les models SQLAlchemy."""

    pass


class TimestampMixin:
    """Mixin pour timestamps automatiques."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class BaseModel(Base, TimestampMixin):
    """Model de base avec UUID PK et timestamps.

    Tous les models ConfiDoc héritent de celui-ci.
    """

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )


class TenantModel(BaseModel):
    """Model avec isolation tenant (org_id obligatoire).

    Utilisé pour toutes les entités liées à une organisation.
    """

    __abstract__ = True

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
