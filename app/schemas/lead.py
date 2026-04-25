"""ConfiDoc Backend — Public lead schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class BetaLeadCreate(BaseModel):
    """Payload submitted from the public beta access form."""

    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=160)
    company: str = Field(..., min_length=2, max_length=180)
    role: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    team_size: str | None = Field(default=None, max_length=40)
    document_volume: str | None = Field(default=None, max_length=80)
    use_case: str = Field(..., min_length=10, max_length=1200)
    source: str = Field(default="landing", max_length=80)
    consent_to_contact: bool = Field(default=False)

    @field_validator(
        "full_name",
        "company",
        "role",
        "phone",
        "team_size",
        "document_volume",
        "use_case",
        "source",
        mode="before",
    )
    @classmethod
    def _strip_text(cls, value: object) -> object:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("source")
    @classmethod
    def _normalize_source(cls, value: str) -> str:
        normalized = value.lower().replace(" ", "_")
        return "".join(ch for ch in normalized if ch.isalnum() or ch in {"_", "-"})

    @model_validator(mode="after")
    def _require_contact_consent(self) -> BetaLeadCreate:
        if not self.consent_to_contact:
            raise ValueError("Le consentement de contact est requis.")
        return self


class BetaLeadResponse(BaseModel):
    status: Literal["received"]
    message: str
