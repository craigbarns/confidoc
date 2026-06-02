"""ConfiDoc Backend — JSON utilities."""

import json
import re
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


def extract_json(raw_text: str) -> dict[str, Any]:
    """Extract and parse JSON from a raw string (potentially containing markdown)."""
    if not raw_text:
        return {}

    # Try to find the JSON block
    start = raw_text.find("{")
    end = raw_text.rfind("}")

    if start == -1 or end == -1 or start >= end:
        return {}

    candidate = raw_text[start : end + 1]

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # Try cleaning common LLM artifacts
        try:
            # Remove trailing commas
            cleaned = re.sub(r",\s*}", "}", candidate)
            cleaned = re.sub(r",\s*]", "]", cleaned)
            # Remove double newlines
            cleaned = cleaned.replace("\n\n", "\n")
            return json.loads(cleaned)
        except Exception as exc:
            logger.warning("json_extraction_failed", error=str(exc), raw_snippet=raw_text[:200])
            return {}


def safe_json_loads(data: str | bytes) -> Any:
    """Safely load JSON data with error handling."""
    if not data:
        return None
    try:
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("safe_json_loads_failed", error=str(exc))
        return None
