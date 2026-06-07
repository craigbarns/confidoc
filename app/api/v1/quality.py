"""ConfiDoc Backend — Quality / Data Flywheel endpoints.

Exposes a thin CRUD on :class:`GoldenCaseDraft` so a human correction can be
captured as a draft golden case and curated later.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status
from sqlalchemy import desc, select

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import http_400, http_404
from app.core.logging import get_logger
from app.core.rls import commit_and_restore_rls_context
from app.models.golden_case_draft import GoldenCaseDraft, GoldenDraftStatus
from app.schemas.golden_draft import (
    GoldenDraftCreate,
    GoldenDraftResponse,
    GoldenDraftStatusUpdate,
)
from app.services.golden_draft_service import (
    _document_belongs_to_org,
    create_golden_draft,
)

router = APIRouter()
logger = get_logger(__name__)


@router.post(
    "/golden-drafts",
    response_model=GoldenDraftResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un golden draft à partir d'une correction humaine",
)
async def create_golden_draft_endpoint(
    payload: GoldenDraftCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> GoldenCaseDraft:
    """Persist a draft golden case for the current organization.

    Tenant isolation is enforced by checking that the referenced document
    belongs to the caller's org *before* creating the draft.
    """
    if current_user.org_id is None:
        raise http_400("Aucune organisation associée à l'utilisateur courant")

    if not await _document_belongs_to_org(db, payload.document_id, current_user.org_id):
        raise http_404("Document introuvable")

    draft = await create_golden_draft(
        db,
        org_id=current_user.org_id,
        document_id=payload.document_id,
        created_by_user_id=current_user.id,
        field_name=payload.field_name,
        predicted_value=payload.predicted_value,
        corrected_value=payload.corrected_value,
        source_snippet=payload.source_snippet,
        error_type=payload.error_type,
        confidence_before=payload.confidence_before,
        document_type=payload.document_type,
    )
    logger.info(
        "golden_draft_created",
        draft_id=str(draft.id),
        document_id=str(draft.document_id),
        org_id=str(draft.org_id),
        field_name=draft.field_name,
        error_type=draft.error_type,
    )
    return draft


@router.get(
    "/golden-drafts",
    response_model=list[GoldenDraftResponse],
    status_code=status.HTTP_200_OK,
    summary="Lister les golden drafts de l'organisation",
)
async def list_golden_drafts(
    current_user: CurrentUser,
    db: DbSession,
    status_filter: GoldenDraftStatus | None = Query(default=None, alias="status"),
    document_type: str | None = Query(default=None, max_length=60),
    error_type: str | None = Query(default=None, max_length=60),
    document_id: uuid.UUID | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[GoldenCaseDraft]:
    if current_user.org_id is None:
        return []

    stmt = select(GoldenCaseDraft).where(GoldenCaseDraft.org_id == current_user.org_id)
    if status_filter is not None:
        stmt = stmt.where(GoldenCaseDraft.status == status_filter)
    if document_type is not None:
        stmt = stmt.where(GoldenCaseDraft.document_type == document_type)
    if error_type is not None:
        stmt = stmt.where(GoldenCaseDraft.error_type == error_type)
    if document_id is not None:
        stmt = stmt.where(GoldenCaseDraft.document_id == document_id)

    stmt = stmt.order_by(desc(GoldenCaseDraft.created_at)).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.patch(
    "/golden-drafts/{draft_id}/status",
    response_model=GoldenDraftResponse,
    status_code=status.HTTP_200_OK,
    summary="Mettre à jour le statut d'un golden draft (curation)",
)
async def update_golden_draft_status(
    draft_id: uuid.UUID,
    payload: GoldenDraftStatusUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> GoldenCaseDraft:
    if current_user.org_id is None:
        raise http_404("Golden draft introuvable")

    result = await db.execute(
        select(GoldenCaseDraft).where(
            GoldenCaseDraft.id == draft_id,
            GoldenCaseDraft.org_id == current_user.org_id,
        )
    )
    draft = result.scalar_one_or_none()
    if draft is None:
        # Either it doesn't exist or it belongs to another org — same answer.
        raise http_404("Golden draft introuvable")

    draft.status = payload.status
    await commit_and_restore_rls_context(db, org_id=current_user.org_id, user_id=current_user.id)
    await db.refresh(draft)
    logger.info(
        "golden_draft_status_updated",
        draft_id=str(draft.id),
        org_id=str(draft.org_id),
        status=draft.status.value,
    )
    return draft
