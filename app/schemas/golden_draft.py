"""ConfiDoc Backend — Schemas for GoldenCaseDraft (Data Flywheel)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.golden_case_draft import (
    CORRECTED_VALUE_MAX_CHARS,
    PREDICTED_VALUE_MAX_CHARS,
    SOURCE_SNIPPET_MAX_CHARS,
    GoldenDraftStatus,
)


class GoldenDraftCreate(BaseModel):
    """Payload accepted by ``POST /quality/golden-drafts``.

    Only the corrected field metadata + a *short* snippet is accepted, never the
    full document content.
    """

    document_id: uuid.UUID
    field_name: str = Field(min_length=1, max_length=120)
    predicted_value: str | None = Field(
        default=None, max_length=PREDICTED_VALUE_MAX_CHARS
    )
    corrected_value: str = Field(
        min_length=1, max_length=CORRECTED_VALUE_MAX_CHARS
    )
    source_snippet: str | None = Field(
        default=None, max_length=SOURCE_SNIPPET_MAX_CHARS
    )
    error_type: str = Field(min_length=1, max_length=60)
    confidence_before: float | None = Field(default=None, ge=0.0, le=1.0)
    document_type: str = Field(min_length=1, max_length=60)


class GoldenDraftStatusUpdate(BaseModel):
    """Payload accepted by ``PATCH /quality/golden-drafts/{id}/status``."""

    status: GoldenDraftStatus


class GoldenDraftResponse(BaseModel):
    """Public representation of a draft.

    Sensitive payloads are decrypted by the ORM layer when reading; this is the
    same trade-off used elsewhere in the codebase (e.g. ``Organization.name``).
    """

    id: uuid.UUID
    org_id: uuid.UUID
    document_id: uuid.UUID
    created_by_user_id: uuid.UUID | None
    field_name: str
    predicted_value: str | None
    corrected_value: str
    source_snippet: str | None
    error_type: str
    confidence_before: float | None
    document_type: str
    status: GoldenDraftStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
