"""ConfiDoc Backend — API Endpoints pour le Tracking Human-in-the-Loop."""

import uuid
from typing import Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import http_404
from app.core.logging import get_logger
from app.models.document import Document
from app.models.human_feedback import HumanFeedback
from app.schemas.document import HumanFeedbackResponse

router = APIRouter()
logger = get_logger(__name__)


class HumanFeedbackCreateArgs(BaseModel):
    document_id: uuid.UUID
    doc_type: str = Field(..., max_length=50)
    profile_used: str = Field(..., max_length=50)

    feedback_type: Literal[
        "missed_entity",
        "false_positive",
        "wrong_entity_type",
        "wrong_placeholder_type",
        "manual_mask_added",
        "manual_unmask",
        "field_correction",
    ]

    entity_type: str | None = Field(default=None, max_length=50)
    original_value_hash: str | None = Field(default=None, max_length=64)
    corrected_value_hash: str | None = Field(default=None, max_length=64)
    original_label: str | None = Field(default=None, max_length=50)
    corrected_label: str | None = Field(default=None, max_length=50)
    action_taken: str | None = Field(default=None, max_length=50)

    source_page: int | None = Field(default=None, ge=0)
    source_span_start: int | None = Field(default=None, ge=0)
    source_span_end: int | None = Field(default=None, ge=0)
    review_comment: str | None = Field(default=None, max_length=2000)


@router.post(
    "/human-corrections",
    response_model=HumanFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enregistrer une correction humaine experte",
)
async def create_human_feedback(
    args: HumanFeedbackCreateArgs,
    current_user: CurrentUser,
    db: DbSession,
) -> HumanFeedbackResponse:
    """Stocke de manière anonymisée une correction apportée par le validateur."""
    # Verify document exists and belongs to user
    doc_result = await db.execute(
        select(Document).where(
            Document.id == args.document_id,
            Document.uploaded_by_user_id == current_user.id,
        )
    )
    if not doc_result.scalar_one_or_none():
        raise http_404("Document introuvable ou accès refusé")

    feedback = HumanFeedback(
        document_id=args.document_id,
        user_id=current_user.id,
        doc_type=args.doc_type,
        profile_used=args.profile_used,
        feedback_type=args.feedback_type,
        entity_type=args.entity_type,
        original_value_hash=args.original_value_hash,
        corrected_value_hash=args.corrected_value_hash,
        original_label=args.original_label,
        corrected_label=args.corrected_label,
        action_taken=args.action_taken,
        source_page=args.source_page,
        source_span_start=args.source_span_start,
        source_span_end=args.source_span_end,
        review_comment=args.review_comment,
    )

    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    logger.info(
        "human_feedback_recorded",
        feedback_id=str(feedback.id),
        feedback_type=args.feedback_type,
        document_id=str(args.document_id),
        user_id=str(current_user.id),
    )

    return HumanFeedbackResponse(
        status="recorded",
        feedback_id=str(feedback.id),
        feedback_type=args.feedback_type,
    )


@router.get(
    "/stats",
    status_code=status.HTTP_200_OK,
    summary="Récupérer les statistiques de feedback",
)
async def get_human_feedback_stats(
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Retourne des agrégations par doc_type et feedback_type."""
    total_result = await db.execute(select(func.count()).select_from(HumanFeedback))
    total = total_result.scalar() or 0

    by_type_result = await db.execute(
        select(HumanFeedback.feedback_type, func.count())
        .group_by(HumanFeedback.feedback_type)
    )
    by_type = {row[0]: row[1] for row in by_type_result.all()}

    by_doc_type_result = await db.execute(
        select(HumanFeedback.doc_type, func.count())
        .group_by(HumanFeedback.doc_type)
    )
    by_doc_type = {row[0]: row[1] for row in by_doc_type_result.all()}

    return {
        "total_corrections": total,
        "by_feedback_type": by_type,
        "by_doc_type": by_doc_type,
    }
