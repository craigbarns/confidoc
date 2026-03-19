"""ConfiDoc Backend — Schemas Documents."""

from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict


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
