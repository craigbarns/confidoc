"""ConfiDoc Backend — GoldenCaseDraft model.

Represents a draft golden case generated from a human correction. The draft is
intentionally minimal: it only stores the corrected field, the predicted value,
the corrected value and a short source snippet, never the full document. The
sensitive textual columns are stored using the project-wide ``EncryptedString``
type so that any data still readable in the snippet/values stays encrypted at
rest.

Drafts feed the Data Flywheel: human corrections become structured signals that
can later be curated into the golden set, and used to harden extraction,
anonymization rules and prompts.
"""

from __future__ import annotations

import uuid
from enum import Enum as PyEnum

from sqlalchemy import Enum, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantModel
from app.services.crypto_service import EncryptedString


class GoldenDraftStatus(str, PyEnum):
    """Lifecycle of a draft on its way to the curated golden set."""

    DRAFT = "draft"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


# Conservative cap on snippet length: we only want a *short* context around the
# corrected field, never the full document.
SOURCE_SNIPPET_MAX_CHARS = 500
PREDICTED_VALUE_MAX_CHARS = 500
CORRECTED_VALUE_MAX_CHARS = 500


class GoldenCaseDraft(TenantModel):
    """A draft golden case derived from a single human correction.

    Tenant isolation is enforced via ``org_id`` (inherited from
    :class:`~app.models.base.TenantModel`). All queries must filter on this
    column.
    """

    __tablename__ = "golden_case_drafts"
    __table_args__ = (
        Index("ix_golden_case_drafts_org_created", "org_id", "created_at"),
        Index("ix_golden_case_drafts_org_status", "org_id", "status"),
        Index("ix_golden_case_drafts_org_doc_type", "org_id", "document_type"),
        Index("ix_golden_case_drafts_org_error_type", "org_id", "error_type"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    field_name: Mapped[str] = mapped_column(String(120), nullable=False)

    # Sensitive payloads — stored encrypted at rest via Fernet.
    predicted_value: Mapped[str | None] = mapped_column(
        EncryptedString(PREDICTED_VALUE_MAX_CHARS * 4),
        nullable=True,
    )
    corrected_value: Mapped[str] = mapped_column(
        EncryptedString(CORRECTED_VALUE_MAX_CHARS * 4),
        nullable=False,
    )
    source_snippet: Mapped[str | None] = mapped_column(
        EncryptedString(SOURCE_SNIPPET_MAX_CHARS * 4),
        nullable=True,
    )

    error_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    confidence_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    document_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)

    status: Mapped[GoldenDraftStatus] = mapped_column(
        Enum(
            GoldenDraftStatus,
            name="golden_draft_status",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
            native_enum=False,
        ),
        nullable=False,
        default=GoldenDraftStatus.DRAFT,
        server_default=GoldenDraftStatus.DRAFT.value,
        index=True,
    )
