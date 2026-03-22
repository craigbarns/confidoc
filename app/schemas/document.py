"""ConfiDoc Backend — Schemas Documents."""

from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


class DocumentResponse(BaseModel):
    id: uuid.UUID
    status: str
    original_filename: str
    content_type: str
    extension: str
    size_bytes: int
    sha256: str
    storage_backend: str
    storage_key: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DetectionResponse(BaseModel):
    entity_type: str
    start_index: int
    end_index: int
    value_excerpt: str
    replacement: str


class AnonymizeResponse(BaseModel):
    document_id: uuid.UUID
    status: str
    detections_count: int
    detections: list[DetectionResponse]
    preview_text: str


class DocumentPreviewResponse(BaseModel):
    document_id: uuid.UUID
    status: str
    preview_text: str
    detections_count: int


class ExportResponse(BaseModel):
    document_id: uuid.UUID
    status: str
    final_text: str
    metadata: dict[str, Any]


class FeedbackItem(BaseModel):
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
    source_page: int | None = None
    source_span_start: int | None = None
    source_span_end: int | None = None
    review_comment: str | None = None


class ValidateDocumentRequest(BaseModel):
    # Allows tracking the context when the user applies manual corrections and saves
    doc_type: str = Field(..., max_length=50)
    profile_used: str = Field(..., max_length=50)
    final_text: str | None = Field(
        default=None, 
        description="Le texte final validé par l'humain, s'il a été édité manuellement."
    )
    feedbacks: list[FeedbackItem] = Field(default_factory=list)
