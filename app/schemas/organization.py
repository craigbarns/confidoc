"""ConfiDoc Backend — Schemas Organization."""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.organization import PlanType, ProfessionType


class OrganizationBase(BaseModel):
    name: str = Field(..., max_length=255, description="Nom de l'organisation")
    profession_type: ProfessionType = Field(default=ProfessionType.AUTRE)


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    profession_type: ProfessionType | None = None
    settings: dict[str, Any] | None = None


class OrganizationResponse(OrganizationBase):
    id: uuid.UUID
    slug: str
    plan: PlanType
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
