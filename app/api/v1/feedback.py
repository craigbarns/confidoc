"""ConfiDoc Backend — API Endpoints pour le Tracking Human-in-the-Loop."""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession
from app.models.human_feedback import HumanFeedback

router = APIRouter()
logger = logging.getLogger(__name__)


class HumanFeedbackCreateArgs(BaseModel):
    document_id: str
    doc_type: str = Field(..., max_length=50)
    profile_used: str = Field(..., max_length=50)
    
    # Types stricts selon la directive business :
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
    original_value_hash: str | None = Field(default=None, max_length=64, description="SHA256 of the original text")
    corrected_value_hash: str | None = Field(default=None, max_length=64, description="SHA256 of the corrected text")
    original_label: str | None = Field(default=None, max_length=50)
    corrected_label: str | None = Field(default=None, max_length=50)
    action_taken: str | None = Field(default=None, max_length=50)
    
    source_page: int | None = None
    source_span_start: int | None = None
    source_span_end: int | None = None
    review_comment: str | None = None


@router.post(
    "/human-corrections",
    status_code=status.HTTP_201_CREATED,
    summary="Enregistrer une correction humaine experte",
)
async def create_human_feedback(
    args: HumanFeedbackCreateArgs,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Stocke de manière anonymisée une correction apportée par le validateur."""
    feedback = HumanFeedback(
        document_id=args.document_id,
        user_id=current_user.id,
        # TODO: organization_id logic via current_user membership if we have it natively
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
    
    logger.info("human_feedback_recorded", feedback_id=str(feedback.id), fb_type=args.feedback_type)
    
    return {
        "status": "recorded",
        "feedback_id": str(feedback.id),
    }


@router.get(
    "/stats",
    status_code=status.HTTP_200_OK,
    summary="Récupérer les statistiques de feedback",
)
async def get_human_feedback_stats(
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Retourne des aggrégations (par doc_type, etc) pour construire le ROI du produit."""
    # V1 : endpoint placeholder pour le dashboard Admin
    return {
        "total_corrections": 0,
        "anomalies_bypassed": 0,
        "message": "Stats to be aggregated via SQL in V2"
    }
