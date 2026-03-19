"""ConfiDoc Backend — Schemas Organization."""

from datetime import datetime
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.organization import PlanType, ProfessionType


class OrganizationBase(BaseModel):
    name: str = Field(..., max_length=255, description="Nom de l'organisation")
    profession_type: ProfessionType = Field(default=ProfessionType.AUTRE)


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    profession_type: Optional[ProfessionType] = None
    settings: Optional[dict[str, Any]] = None


class OrganizationResponse(OrganizationBase):
    id: uuid.UUID
    slug: str
    plan: PlanType
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
