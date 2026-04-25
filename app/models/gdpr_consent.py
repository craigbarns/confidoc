"""ConfiDoc Backend — GDPR Consent Model."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import Base


class GDPRConsent(Base):
    """Stores user consent for GDPR data processing."""

    __tablename__ = "gdpr_consent"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Consent details
    consent_type = Column(String(50), nullable=False, default="general_processing")
    is_granted = Column(Boolean, nullable=False, default=False)
    
    # Audit trail
    granted_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(255), nullable=True)
    version = Column(String(20), nullable=False, default="1.0")
    
    # Relationships
    user = relationship("User", back_populates="consents")


# Update User model to include relationship
# I'll need to update User model as well.
