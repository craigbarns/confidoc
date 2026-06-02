"""ConfiDoc Backend — Client model."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SoftDeleteMixin, TenantModel

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.dossier import Dossier


class Client(SoftDeleteMixin, TenantModel):
    __tablename__ = "clients"

    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Relationships
    dossiers = relationship("Dossier", back_populates="client", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="client")
