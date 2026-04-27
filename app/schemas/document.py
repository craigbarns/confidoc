"""ConfiDoc Backend — Schemas Documents."""

from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


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
    client_id: uuid.UUID | None = None
    dossier_id: uuid.UUID | None = None
    client_name: str | None = None
    exercice: str | None = None
    doc_category: str | None = None
    search_snippet: str | None = None
    is_deleted: bool = False
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: Any) -> str:
        if hasattr(v, "value"):
            return str(v.value)
        return str(v)


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
    entity_summary: dict[str, int] = Field(default_factory=dict)


class ValidateDocumentRequest(BaseModel):
    final_text: str | None = Field(
        default=None,
        description="Texte final validé, s'il a été édité manuellement.",
    )
    doc_type: str | None = Field(
        default=None,
        description="Le type de document validé (ex: bilan, compte_resultat).",
    )
    corrected_data: dict[str, Any] | None = Field(
        default=None,
        description="Les données structurées après correction humaine (pour Golden Sets).",
    )


class EntityMappingItem(BaseModel):
    """A single entity placeholder → original values mapping."""
    placeholder: str = Field(description="Le token anonymisé, ex: [PERSONNE_1]")
    entity_type: str = Field(description="Type sémantique: PERSON, COMPANY, ADDRESS...")
    occurrences: int = Field(ge=0, description="Nombre d'occurrences dans le document")


class KeyAmountItem(BaseModel):
    libelle: str
    montant: float
    nature: str = Field(default="autre")
    pcg_code: str | None = Field(default=None)
    source_snippet: str | None = Field(default=None)


class StructuredDocumentResponse(BaseModel):
    """Sortie structurée pour exploitation IA/RAG."""
    document_id: uuid.UUID
    doc_type: str | None = Field(default=None, description="Type détecté: invoice, accounting, legal, generic")
    status: str
    original_filename: str

    # Entity mapping — key info for downstream AI
    entity_summary: dict[str, int] = Field(
        default_factory=dict,
        description="Comptage par type d'entité: {PERSONNE: 3, SOCIETE: 2, ...}",
    )
    entity_tags: list[EntityMappingItem] = Field(
        default_factory=list,
        description="Liste détaillée des entités détectées avec leur placeholder",
    )

    # Text content
    anonymized_text: str | None = Field(
        default=None,
        description="Texte anonymisé complet (si disponible)",
    )
    text_length: int = Field(default=0, description="Longueur du texte anonymisé")

    # Detections count
    detections_count: int = Field(ge=0, default=0)

    # New Business and Audit fields
    montants_cles: list[KeyAmountItem] = Field(default_factory=list)
    totaux: dict[str, Any] = Field(default_factory=dict)
    business_rules: dict[str, Any] = Field(default_factory=dict)
    audit_risk_score: int = Field(default=0)
    audit_findings: list[dict[str, Any]] = Field(default_factory=list)
    requires_investigation: bool = Field(default=False)

    # Metadata
    anonymization_method: str | None = Field(
        default=None,
        description="Méthode utilisée: dictionary, llm:mistral-large, etc.",
    )
    created_at: datetime


class DocumentMetadataPatch(BaseModel):
    client_id: uuid.UUID | None = Field(default=None)
    dossier_id: uuid.UUID | None = Field(default=None)
    client_name: str | None = Field(default=None, max_length=120)
    exercice: str | None = Field(default=None, pattern=r"^\d{4}$")
    doc_category: str | None = Field(default=None, max_length=30)


class DossierDoc(BaseModel):
    id: uuid.UUID
    original_filename: str
    doc_category: str | None = None
    status: str
    size_bytes: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: Any) -> str:
        if hasattr(v, "value"):
            return str(v.value)
        return str(v)


class DossierExercice(BaseModel):
    exercice: str | None
    doc_count: int
    ready_count: int
    processing_count: int
    doc_categories: list[str]
    documents: list[DossierDoc]


class DossierClient(BaseModel):
    client_name: str
    exercices: list[DossierExercice]
    total_docs: int
    last_activity: datetime | None

