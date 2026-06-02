"""ConfiDoc Backend — Dossier schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DossierBase(BaseModel):
    exercice: str = Field(..., pattern=r"^\d{4}(-\d{4})?$")


class DossierCreate(DossierBase):
    client_id: uuid.UUID


class DossierUpdate(DossierBase):
    pass


class DossierResponse(DossierBase):
    id: uuid.UUID
    client_id: uuid.UUID
    org_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
