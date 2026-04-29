"""ConfiDoc Backend — Base model SQLAlchemy."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, func, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base déclarative pour tous les models SQLAlchemy."""

    pass


class TimestampMixin:
    """Mixin pour timestamps automatiques.

    We set both an application-level Python default and a Postgres
    ``server_default`` so timestamps are populated even when a row is
    inserted via raw SQL (migrations, fixtures) or when the column is not
    explicitly provided in code.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class SoftDeleteMixin:
    """Mixin pour soft delete — les lignes supprimées sont marquées, pas effacées."""

    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false", index=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
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
