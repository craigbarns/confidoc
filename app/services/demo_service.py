"""Public demo result service.

The public demo is intentionally read-only: it only processes the bundled
``demo_doc.pdf`` and never writes a document row.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.services.anonymization_service import anonymize_text, classify_document_type
from app.services.fast_extraction_service import extract_text_sync
from app.services.reidentification_risk_service import analyze_reidentification_risk

logger = get_logger(__name__)

DEMO_DOC_PATH = Path(__file__).resolve().parent.parent / "static" / "demo_doc.pdf"
DEMO_CACHE_KEY = "confidoc:demo:public_result:v1"
_memory_demo_cache: dict[str, Any] | None = None


def _summarize_entities(detections: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in detections:
        entity_type = str(item.get("entity_type") or "unknown").upper()
        replacement = str(item.get("replacement") or "")
        if replacement.startswith("[") and replacement.endswith("]"):
            entity_type = replacement.strip("[]").split("_", 1)[0].upper()
        summary[entity_type] = summary.get(entity_type, 0) + 1
    return summary


def _excerpt(text: str, max_chars: int = 1800) -> str:
    clean = (text or "").strip()
    if len(clean) <= max_chars:
        return clean
    return clean[:max_chars].rstrip() + "\n..."


def _compute_demo_result() -> dict[str, Any]:
    """Compute the bundled demo result synchronously."""
    if not DEMO_DOC_PATH.exists():
        raise FileNotFoundError(f"Demo document not found: {DEMO_DOC_PATH}")

    content = DEMO_DOC_PATH.read_bytes()
    extraction = extract_text_sync(content, "pdf")
    original_text = str(extraction.get("text") or "")
    if not original_text.strip():
        raise ValueError("Demo document extraction returned empty text")

    document_type = classify_document_type(original_text, DEMO_DOC_PATH.name)
    anonymized_text, detections, _registry = anonymize_text(
        original_text,
        profile="dataset_accounting_pseudo",
        document_type=document_type,
    )
    entity_summary = _summarize_entities(detections)
    risk = analyze_reidentification_risk(anonymized_text, entity_summary)

    return {
        "status": "ready",
        "source": "bundled_demo_doc",
        "filename": DEMO_DOC_PATH.name,
        "document_type": document_type,
        "pages": int(extraction.get("pages") or 0),
        "extraction_method": extraction.get("method") or "unknown",
        "original_excerpt": _excerpt(original_text),
        "anonymized_excerpt": _excerpt(anonymized_text),
        "detections": detections[:80],
        "detections_count": len(detections),
        "entity_summary": entity_summary,
        "risk": risk.to_dict(),
    }


async def _get_redis() -> Any | None:
    try:
        import redis.asyncio as aioredis

        from app.config import get_settings

        settings = get_settings()
        return aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=1,
        )
    except Exception as exc:
        logger.debug("demo_redis_unavailable", error=str(exc))
        return None


async def warm_demo_cache() -> None:
    """Pre-compute and cache the public demo result."""
    global _memory_demo_cache

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _compute_demo_result)
        _memory_demo_cache = result
    except Exception as exc:
        logger.warning("demo_cache_warm_failed", error=str(exc))
        return

    redis_client = await _get_redis()
    if redis_client is None:
        logger.info("demo_cache_warmed_memory", detections=result["detections_count"])
        return

    try:
        async with redis_client as redis_conn:
            await redis_conn.set(DEMO_CACHE_KEY, json.dumps(result, ensure_ascii=False))
        logger.info("demo_cache_warmed", detections=result["detections_count"])
    except Exception as exc:
        logger.warning("demo_cache_store_failed", error=str(exc))


async def get_demo_result() -> dict[str, Any] | None:
    """Return the warmed public demo result, or None while warming."""
    if _memory_demo_cache is not None:
        return _memory_demo_cache

    redis_client = await _get_redis()
    if redis_client is None:
        return None

    try:
        async with redis_client as redis_conn:
            raw = await redis_conn.get(DEMO_CACHE_KEY)
    except Exception as exc:
        logger.warning("demo_cache_fetch_failed", error=str(exc))
        return None

    if not raw:
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None

    if isinstance(parsed, dict):
        return parsed
    return None
