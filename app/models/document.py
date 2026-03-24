"""ConfiDoc Backend — Document model."""

from enum import Enum as PyEnum
import uuid

from sqlalchemy import Enum, ForeignKey, Index, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, SoftDeleteMixin


class DocumentStatus(str, PyEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Document(SoftDeleteMixin, BaseModel):
    __tablename__ = "documents"
    __table_args__ = (
        # Composite index: user's documents sorted by date (most common query)
        Index("ix_documents_user_created", "uploaded_by_user_id", "created_at"),
        # Composite index: org-level queries sorted by date (tenant isolation)
        Index("ix_documents_org_created", "org_id", "created_at"),
        # Composite index: active (non-deleted) documents per user
        Index("ix_documents_user_active", "uploaded_by_user_id", "is_deleted"),
        # Composite index: status filtering per org
        Index("ix_documents_org_status", "org_id", "status"),
    )

    org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    extension: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_backend: Mapped[str] = mapped_column(String(20), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus), default=DocumentStatus.UPLOADED, nullable=False, index=True
    )

    # Raw file bytes — stored in DB as fallback when external storage is ephemeral
    # (e.g. Railway local /tmp). Nullable for backward compat with existing rows.
    raw_content: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, default=None)
