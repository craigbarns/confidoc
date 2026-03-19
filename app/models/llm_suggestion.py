"""ConfiDoc Backend — LLM span suggestions."""

import uuid

from sqlalchemy import ForeignKey, Float, String, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class LlmSuggestion(BaseModel):
    __tablename__ = "llm_suggestions"

    llm_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llm_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    entity_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    start_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    end_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    replacement_token: Mapped[str] = mapped_column(String(60), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

