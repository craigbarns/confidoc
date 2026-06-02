"""ConfiDoc Backend — GDPR Processing Register Model."""

import uuid

from sqlalchemy import Boolean, Column, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class GDPRProcessingRegister(Base):
    """Registre des activités de traitement (Article 30 RGPD)."""

    __tablename__ = "gdpr_processing_register"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String(255), nullable=False)
    purpose = Column(Text, nullable=False)  # Finalité du traitement
    legal_basis = Column(
        String(255), nullable=False
    )  # Base légale (ex: Consentement, Contrat, Obligation légale)
    data_categories = Column(Text, nullable=False)  # Catégories de données traitées
    data_subjects = Column(Text, nullable=False)  # Catégories de personnes concernées
    recipients = Column(Text, nullable=True)  # Destinataires des données
    retention_period = Column(String(100), nullable=False)  # Durée de conservation
    security_measures = Column(
        Text, nullable=False
    )  # Mesures de sécurité (techniques et organisationnelles)
    is_active = Column(Boolean, default=True, nullable=False)
