"""ConfiDoc Backend — KB accounting records for RAG."""

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class KbAccountingRecord(BaseModel):
    __tablename__ = "kb_accounting_records"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
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

    doc_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    code_comptable: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    categorie_pcg: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    montant_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    libelle: Mapped[str] = mapped_column(Text, nullable=False)

    # "risk-free gate" for downstream LLM usage
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
