"""ConfiDoc Backend — Service for GoldenCaseDraft (Data Flywheel).

Thin business-logic layer: route handlers stay thin, all the org-scoping and
truncation/sanitisation rules live here.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.document import Document
from app.models.golden_case_draft import (
    CORRECTED_VALUE_MAX_CHARS,
    PREDICTED_VALUE_MAX_CHARS,
    SOURCE_SNIPPET_MAX_CHARS,
    GoldenCaseDraft,
    GoldenDraftStatus,
)

logger = get_logger(__name__)


def _truncate(value: str | None, max_chars: int) -> str | None:
    """Hard cap a textual payload to its max length.

    Pydantic also validates this on the public endpoint, but we re-apply the
    truncation in the service layer because internal callers (e.g. the
    ``validate_document`` flow) bypass the request schema.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    if len(value) <= max_chars:
        return value
    return value[:max_chars]


async def _document_belongs_to_org(
    db: AsyncSession, document_id: uuid.UUID, org_id: uuid.UUID
) -> bool:
    """Cheap tenant-isolation guard: ensure the document is in the caller org."""
    stmt = select(Document.id).where(
        Document.id == document_id,
        Document.org_id == org_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def create_golden_draft(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    document_id: uuid.UUID,
    created_by_user_id: uuid.UUID | None,
    field_name: str,
    predicted_value: str | None,
    corrected_value: str,
    source_snippet: str | None,
    error_type: str,
    confidence_before: float | None,
    document_type: str,
    commit: bool = True,
) -> GoldenCaseDraft:
    """Create and persist a single :class:`GoldenCaseDraft`.

    The caller is responsible for having authenticated/authorized the user and
    for passing a valid ``org_id``. Sensitive payloads are truncated before
    being passed to the encrypted columns.
    """
    draft = GoldenCaseDraft(
        org_id=org_id,
        document_id=document_id,
        created_by_user_id=created_by_user_id,
        field_name=field_name.strip(),
        predicted_value=_truncate(predicted_value, PREDICTED_VALUE_MAX_CHARS),
        corrected_value=_truncate(corrected_value, CORRECTED_VALUE_MAX_CHARS) or "",
        source_snippet=_truncate(source_snippet, SOURCE_SNIPPET_MAX_CHARS),
        error_type=error_type.strip(),
        confidence_before=confidence_before,
        document_type=document_type.strip(),
        status=GoldenDraftStatus.DRAFT,
    )
    db.add(draft)
    if commit:
        await db.commit()
        await db.refresh(draft)
    else:
        await db.flush()
    return draft


async def create_drafts_from_corrections(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    document_id: uuid.UUID,
    created_by_user_id: uuid.UUID | None,
    document_type: str,
    corrected_data: dict[str, Any],
    predicted_data: dict[str, Any] | None = None,
    source_snippet: str | None = None,
    error_type: str = "manual_correction",
    confidence_before: float | None = None,
) -> list[GoldenCaseDraft]:
    """Bulk helper used by the validate flow.

    Each entry in ``corrected_data`` becomes one draft. The original document
    text is never stored — only ``source_snippet`` (already truncated) and the
    field-level corrected value.
    """
    drafts: list[GoldenCaseDraft] = []
    predicted_data = predicted_data or {}
    for field_name, corrected_value in corrected_data.items():
        if corrected_value is None:
            continue
        # Stringify scalars so encrypted-string columns stay simple.
        corrected_str = (
            corrected_value
            if isinstance(corrected_value, str)
            else str(corrected_value)
        )
        predicted_value = predicted_data.get(field_name)
        predicted_str: str | None
        if predicted_value is None:
            predicted_str = None
        elif isinstance(predicted_value, str):
            predicted_str = predicted_value
        else:
            predicted_str = str(predicted_value)

        draft = await create_golden_draft(
            db,
            org_id=org_id,
            document_id=document_id,
            created_by_user_id=created_by_user_id,
            field_name=str(field_name),
            predicted_value=predicted_str,
            corrected_value=corrected_str,
            source_snippet=source_snippet,
            error_type=error_type,
            confidence_before=confidence_before,
            document_type=document_type,
            commit=False,
        )
        drafts.append(draft)

    if drafts:
        await db.commit()
        for draft in drafts:
            await db.refresh(draft)

    return drafts
