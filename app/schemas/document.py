"""ConfiDoc Backend — Schemas Documents."""

from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator
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
    start_index: int = Field(ge=0)
    end_index: int = Field(ge=0)
    value_excerpt: str
    replacement: str

    @model_validator(mode="after")
    def check_span_order(self) -> "DetectionResponse":
        if self.end_index < self.start_index:
            raise ValueError("end_index must be >= start_index")
        return self


class AnonymizeResponse(BaseModel):
    document_id: uuid.UUID
    status: str
    detections_count: int = Field(ge=0)
    detections: list[DetectionResponse]
    preview_text: str


class DocumentPreviewResponse(BaseModel):
    document_id: uuid.UUID
    status: str
    preview_text: str
    detections_count: int = Field(ge=0)


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
    source_page: int | None = Field(default=None, ge=0)
    source_span_start: int | None = Field(default=None, ge=0)
    source_span_end: int | None = Field(default=None, ge=0)
    review_comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def check_feedback_consistency(self) -> "FeedbackItem":
        """Validate cross-field consistency based on feedback_type."""
        ft = self.feedback_type
        if ft == "missed_entity" and not self.entity_type:
            raise ValueError("missed_entity feedback requires entity_type")
        if ft == "wrong_entity_type" and (not self.original_label or not self.corrected_label):
            raise ValueError("wrong_entity_type feedback requires original_label and corrected_label")
        if ft == "field_correction" and not self.corrected_value_hash:
            raise ValueError("field_correction feedback requires corrected_value_hash")
        if self.source_span_start is not None and self.source_span_end is not None:
            if self.source_span_end < self.source_span_start:
                raise ValueError("source_span_end must be >= source_span_start")
        return self


class ValidateDocumentRequest(BaseModel):
    doc_type: str = Field(default="generic", max_length=50)
    profile_used: str = Field(default="dataset_accounting_pseudo", max_length=50)
    final_text: str | None = Field(
        default=None,
        description="Le texte final validé par l'humain, s'il a été édité manuellement.",
    )
    feedbacks: list[FeedbackItem] = Field(default_factory=list, max_length=200)


class HumanFeedbackResponse(BaseModel):
    """Response schema for human feedback recording."""
    status: str
    feedback_id: str
    feedback_type: str
