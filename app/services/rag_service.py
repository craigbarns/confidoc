"""ConfiDoc Backend — Semantic RAG service (PGvector + embeddings).

Provides:
- Document chunking & embedding (BGE-M3 via sentence-transformers)
- Semantic similarity search across document chunks
- Context retrieval for the copilot/QA feature

Fallback: if sentence-transformers is not installed, returns empty results
gracefully so the rest of the app keeps working.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.logging import get_logger
from app.models.document_chunk import DocumentChunk

logger = get_logger(__name__)

# ── Embedding model (lazy singleton) ────────────────────────────────────

_EMBED_MODEL: Any | None = None
_EMBED_MODEL_NAME: str | None = None
_DEFAULT_EMBED_MODEL_NAME = "BAAI/bge-m3"  # 1024d, multilingual, SOTA open-source


def _get_embed_model() -> Any | None:
    """Lazy-load the sentence-transformers model.

    Returns None if the library is not installed (e.g. on Railway Starter
    where the model download would be too heavy).
    """
    global _EMBED_MODEL, _EMBED_MODEL_NAME

    settings = get_settings()
    if not settings.RAG_EMBEDDINGS_ENABLED:
        logger.info("rag_embed_disabled")
        return None

    model_name = settings.RAG_EMBED_MODEL.strip() or _DEFAULT_EMBED_MODEL_NAME
    if _EMBED_MODEL is not None and model_name == _EMBED_MODEL_NAME:
        return _EMBED_MODEL

    try:
        from sentence_transformers import SentenceTransformer

        logger.info("rag_embed_model_loading", model=model_name)
        _EMBED_MODEL = SentenceTransformer(model_name)
        _EMBED_MODEL_NAME = model_name
        logger.info("rag_embed_model_ready", model=model_name)
        return _EMBED_MODEL
    except Exception as exc:
        logger.warning(
            "rag_embed_model_unavailable",
            model=model_name,
            error=str(exc),
        )
        return None


# ── Chunking ────────────────────────────────────────────────────────────

CHUNK_SIZE = 512  # target chars per chunk
CHUNK_OVERLAP = 128  # overlap between chunks for context continuity


def _chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[dict[str, Any]]:
    """Split text into overlapping chunks by paragraphs, then by characters."""
    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 20]
    chunks: list[dict[str, Any]] = []
    idx = 0

    for para in paragraphs:
        if len(para) <= chunk_size:
            chunks.append({"index": idx, "text": para})
            idx += 1
            continue

        # Long paragraph: split with overlap
        start = 0
        while start < len(para):
            end = min(start + chunk_size, len(para))
            # Try to end on a space or sentence boundary
            if end < len(para):
                for sep in (". ", " ", "\n"):
                    pos = para.rfind(sep, start + chunk_size // 2, end)
                    if pos != -1:
                        end = pos + len(sep)
                        break
            chunks.append({"index": idx, "text": para[start:end].strip()})
            idx += 1
            start = end - overlap
            if start < 0:
                start = 0

    return chunks


# ── Public API ──────────────────────────────────────────────────────────


async def embed_document(
    db: AsyncSession,
    document_id: uuid.UUID,
    text: str,
) -> int:
    """Chunk and embed a document, storing vectors in PGvector.

    Returns the number of chunks created. Returns 0 if embeddings
    are unavailable (graceful degradation).
    """
    model = _get_embed_model()
    if model is None:
        logger.info("rag_embed_skipped_no_model", doc_id=str(document_id))
        return 0

    # 1) Remove existing chunks for this document
    await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))

    # 2) Chunk
    chunks = _chunk_text(text)
    if not chunks:
        return 0

    # 3) Embed in batch
    texts = [c["text"] for c in chunks]
    try:
        embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    except Exception as exc:
        logger.error("rag_embed_encode_failed", doc_id=str(document_id), error=str(exc))
        return 0

    # 4) Bulk insert
    rows = [
        {
            "id": uuid.uuid4(),
            "document_id": document_id,
            "chunk_text": c["text"][:4000],  # safety cap
            "chunk_index": c["index"],
            "embedding": emb.tolist(),
        }
        for c, emb in zip(chunks, embeddings, strict=True)
    ]
    await db.execute(insert(DocumentChunk), rows)
    await db.flush()

    logger.info(
        "rag_document_embedded",
        doc_id=str(document_id),
        chunks=len(rows),
    )
    return len(rows)


async def search_similar(
    db: AsyncSession,
    query: str,
    top_k: int = 5,
    document_filter: uuid.UUID | None = None,
) -> list[DocumentChunk]:
    """Semantic search across document chunks.

    Returns the top-k most similar chunks ordered by cosine similarity.
    """
    model = _get_embed_model()
    if model is None:
        return []

    try:
        query_vec = model.encode(
            [query],
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0].tolist()
    except Exception as exc:
        logger.error("rag_search_encode_failed", error=str(exc))
        return []

    stmt = (
        select(DocumentChunk)
        .order_by(DocumentChunk.embedding.cosine_distance(query_vec))
        .limit(top_k)
    )
    if document_filter:
        stmt = stmt.where(DocumentChunk.document_id == document_filter)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def build_rag_context(
    db: AsyncSession,
    query: str,
    document_id: uuid.UUID,
    top_k: int = 5,
) -> str:
    """Build a RAG context string for LLM consumption.

    Retrieves semantic chunks + formats them with sources.
    """
    chunks = await search_similar(db, query, top_k=top_k, document_filter=document_id)
    if not chunks:
        return ""

    parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(f"[Extrait {i}] {chunk.chunk_text}")
    return "\n\n".join(parts)
