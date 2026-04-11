"""Schemas for ConfiDoc Copilot endpoints."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class CopilotCitation(BaseModel):
    """Evidence snippet used to answer a question."""

    snippet: str = Field(..., min_length=1, max_length=1200)
    score: float = Field(..., ge=0.0, le=1.0)


class CopilotAskRequest(BaseModel):
    """Ask payload."""

    question: str = Field(..., min_length=3, max_length=1500)
    mode: str = Field(default="expert", pattern="^(quick|expert|report)$")


class CopilotAskResponse(BaseModel):
    """Ask response with traceability."""

    answer: str
    citations: list[CopilotCitation]
    confidence: str = Field(..., pattern="^(low|medium|high)$")
    warnings: list[str] = Field(default_factory=list)
    latency_ms: int = Field(default=0, ge=0)


class CopilotCompareRequest(BaseModel):
    """Compare two anonymized documents (e.g. N vs N-1)."""

    other_document_id: uuid.UUID
    question: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional; default asks for a prudent N vs N-1 style comparison.",
    )


DEFAULT_COMPARE_QUESTION = (
    "Compare les éléments chiffrés et indicateurs présents dans les deux documents "
    "(ex. évolution type N vs N-1). N'invente rien : cite uniquement ce qui figure "
    "explicitement dans les textes. Signale les écarts et les informations manquantes."
)
