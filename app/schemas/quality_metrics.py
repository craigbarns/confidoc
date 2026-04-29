"""ConfiDoc Backend — Schemas for the quality / business metrics dashboard."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class QualityDashboardResponse(BaseModel):
    """Org-scoped snapshot of quality + business metrics.

    All metrics are computed against the caller's organization. ``null`` means
    "not enough data yet to compute it" — never a fake or zero placeholder.
    """

    org_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Organization id the metrics were computed for. Null when the "
            "current user has no membership."
        ),
    )
    as_of: datetime

    # ---- Volume ----
    total_documents: int = Field(default=0, ge=0)
    processed_documents: int = Field(default=0, ge=0)
    validated_documents: int = Field(default=0, ge=0)

    # ---- Time-to-value (seconds) ----
    avg_processing_seconds: float | None = Field(
        default=None,
        description=(
            "Average seconds between upload and the first preview-anonymized "
            "version. Null if no document has been processed yet."
        ),
    )
    avg_time_to_validation_seconds: float | None = Field(
        default=None,
        description=(
            "Average seconds between upload and the final validated version. "
            "Null if no document has been validated yet."
        ),
    )

    # ---- Quality ratios ----
    one_shot_full_ready_rate: float | None = Field(
        default=None,
        description=(
            "Share of validated documents that were validated without any "
            "human correction. Null if no document has been validated yet."
        ),
    )
    avg_human_overrides_per_document: float | None = Field(
        default=None,
        description=(
            "Average number of GoldenCaseDraft entries per validated document. "
            "Null if no document has been validated yet."
        ),
    )

    # ---- Flywheel volume ----
    total_golden_case_drafts: int = Field(default=0, ge=0)
    accepted_golden_case_drafts: int = Field(default=0, ge=0)

    # ---- Distributions ----
    corrections_by_field: dict[str, int] = Field(default_factory=dict)
    corrections_by_error_type: dict[str, int] = Field(default_factory=dict)
    documents_by_status: dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)
