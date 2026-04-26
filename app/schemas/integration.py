"""Schemas for API integrations."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator

DEFAULT_API_SCOPES = ["documents:read", "documents:write", "ai:read"]
DEFAULT_WEBHOOK_EVENTS = ["document.ready", "document.failed", "document.validated"]


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=lambda: DEFAULT_API_SCOPES.copy())
    expires_at: datetime | None = None

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: list[str]) -> list[str]:
        cleaned = [scope.strip() for scope in value if scope.strip()]
        if not cleaned:
            return DEFAULT_API_SCOPES.copy()
        allowed = set(DEFAULT_API_SCOPES)
        unknown = sorted(set(cleaned) - allowed)
        if unknown:
            raise ValueError(f"Scopes inconnus: {', '.join(unknown)}")
        return sorted(set(cleaned))


class ApiKeyCreateResponse(BaseModel):
    id: UUID
    name: str
    key_prefix: str
    api_key: str
    scopes: list[str]
    expires_at: datetime | None
    created_at: datetime


class ApiKeyResponse(BaseModel):
    id: UUID
    name: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class WebhookCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: HttpUrl
    events: list[str] = Field(default_factory=lambda: ["document.ready"])
    signing_secret: str | None = Field(default=None, min_length=16, max_length=500)

    @field_validator("events")
    @classmethod
    def validate_events(cls, value: list[str]) -> list[str]:
        cleaned = [event.strip() for event in value if event.strip()]
        if not cleaned:
            return ["document.ready"]
        allowed = set(DEFAULT_WEBHOOK_EVENTS + ["integration.test"])
        unknown = sorted(set(cleaned) - allowed)
        if unknown:
            raise ValueError(f"Evenements inconnus: {', '.join(unknown)}")
        return sorted(set(cleaned))


class WebhookResponse(BaseModel):
    id: UUID
    name: str
    url: str
    events: list[str]
    is_active: bool
    failure_count: int
    last_success_at: datetime | None
    last_failure_at: datetime | None
    created_at: datetime


class WebhookCreateResponse(WebhookResponse):
    signing_secret: str


class WebhookTestResponse(BaseModel):
    status: str
    endpoint_id: UUID
    delivered: bool


class IntegrationGuideResponse(BaseModel):
    title: str
    base_url: str
    auth_header: str
    upload_example: dict[str, Any]
    webhook_events: list[str]
