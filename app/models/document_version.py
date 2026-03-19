"""ConfiDoc Backend — Document version model."""

from enum import Enum as PyEnum
import uuid

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class DocumentVersionType(str, PyEnum):
    ORIGINAL_TEXT = "original_text"
    PREVIEW_ANONYMIZED = "preview_anonymized"
    FINAL_ANONYMIZED = "final_anonymized"


class DocumentVersion(BaseModel):
    __tablename__ = "document_versions"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_type: Mapped[DocumentVersionType] = mapped_column(
        Enum(DocumentVersionType),
        nullable=False,
        index=True,
    )
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
