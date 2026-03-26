"""ConfiDoc Backend — Schemas Documents."""

from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    tags: list[str] | None = None
    doc_type: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DetectionResponse(BaseModel):
    entity_type: str
    start_index: int = Field(ge=0)
    end_index: int = Field(ge=0)
    value_excerpt: str
    replacement: str
    confidence: float = Field(default=0.0)

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


class ValidateDocumentRequest(BaseModel):
    final_text: str | None = Field(
        default=None,
        description="Texte final validé, s'il a été édité manuellement.",
    )
