"""ConfiDoc Backend — Document model."""

from enum import Enum as PyEnum
from typing import TYPE_CHECKING
import uuid

from sqlalchemy import Enum, ForeignKey, Index, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, SoftDeleteMixin

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.dossier import Dossier


class DocumentStatus(str, PyEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    ANONYMIZING = "anonymizing"
    ANONYMIZED = "anonymized"
    REVIEWING = "reviewing"
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
        # Composite index: dossier queries (client + exercice per user)
        Index("ix_documents_client_exercice", "uploaded_by_user_id", "client_name", "exercice"),
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

    # Tags for categorization (e.g. ["facture", "2026", "client-dupont"])
    tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(100)), nullable=True, default=None,
    )

    # Auto-detected document type from classification
    doc_type: Mapped[str | None] = mapped_column(
        String(40), nullable=True, default=None, index=True,
    )

    # Dossier metadata (auto-detected or user-provided at upload)
    client_name: Mapped[str | None] = mapped_column(
        String(120), nullable=True, default=None,
    )
    exercice: Mapped[str | None] = mapped_column(
        String(9), nullable=True, default=None,
    )
    doc_category: Mapped[str | None] = mapped_column(
        String(30), nullable=True, default=None,
    )

    # Raw file bytes — stored in DB as fallback when external storage is ephemeral
    # (e.g. Railway local /tmp). Nullable for backward compat with existing rows.
    raw_content: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, default=None)

    # Formalized Dossier relationships
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    dossier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dossiers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    client = relationship("Client", back_populates="documents")
    dossier = relationship("Dossier", back_populates="documents")
