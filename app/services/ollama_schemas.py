"""Schémas Pydantic pour les sorties JSON strictes Ollama (synthèse + audit)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SummaryResult(BaseModel):
    """Contrat JSON — synthèse comptable (prompt generate_summary_with_ollama)."""

    resume_executif: str = Field(..., min_length=1)
    points_cles: list[str] = Field(default_factory=list)
    anomalies_ou_alertes: list[str] = Field(default_factory=list)
    questions_de_revue: list[str] = Field(default_factory=list)
    confiance_globale: float = Field(ge=0.0, le=1.0)

    @field_validator("confiance_globale", mode="before")
    @classmethod
    def coerce_confidence(cls, v: object) -> float:
        if v is None:
            return 0.0
        try:
            x = float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0
        # Tolère une échelle 0–100 renvoyée par certains modèles
        if x > 1.0 and x <= 100.0:
            x = x / 100.0
        return max(0.0, min(1.0, x))


class AuditCheckItem(BaseModel):
    code: str = Field(..., min_length=1)
    description: str = ""
    status: Literal["passed", "failed", "inconclusive"]
    explanation: str = ""


class AuditResult(BaseModel):
    """Contrat JSON — agent d'audit (prompt generate_audit_with_ollama)."""

    global_status: Literal["passed", "failed", "inconclusive"]
    checks: list[AuditCheckItem] = Field(default_factory=list)

    @field_validator("checks", mode="after")
    @classmethod
    def checks_non_empty(cls, v: list[AuditCheckItem]) -> list[AuditCheckItem]:
        if not v:
            raise ValueError("checks doit contenir au moins une entrée")
        return v
