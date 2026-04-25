"""ConfiDoc Backend — Document chunks with vector embeddings (PGvector)."""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class DocumentChunk(BaseModel):
    """Chunk of a document with vector embedding for semantic search.

    Uses PGvector's Vector type (stored as native PostgreSQL vector).
    Index: ivfflat for approximate nearest neighbor search.
    """

    __tablename__ = "document_chunks"
    __table_args__ = (
        Index(
            "ix_document_chunks_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # BGE-M3 produces 1024-dimensional embeddings
    embedding: Mapped[list[float]] = mapped_column(Vector(1024), nullable=False)
    source_section: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default=None
    )
