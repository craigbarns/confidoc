"""ConfiDoc Backend — Dossier model."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantModel, SoftDeleteMixin

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.document import Document


class Dossier(SoftDeleteMixin, TenantModel):
    __tablename__ = "dossiers"
    __table_args__ = (
        UniqueConstraint("client_id", "exercice", name="uq_dossier_client_exercice"),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    exercice: Mapped[str] = mapped_column(String(9), nullable=False, index=True) # e.g. "2024" or "2024-2025"
    
    # Relationships
    client = relationship("Client", back_populates="dossiers")
    documents = relationship("Document", back_populates="dossier")
