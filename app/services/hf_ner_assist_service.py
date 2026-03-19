"""ConfiDoc Backend — NER assistif via Hugging Face (API gérée)."""

import json
import re
from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()

ALLOWED_REPLACEMENT_TOKENS: set[str] = {
    "[EMAIL]",
    "[PHONE]",
    "[IBAN]",
    "[BIC]",
    "[SIREN]",
    "[SIRET]",
    "[VAT]",
    "[COMPANY]",
    "[PERSON]",
    "[ADDRESS]",
    "[CITY]",
    "[DATE]",
    "[AMOUNT]",
    "[INVOICE_REF]",
    "[REDACTED]",
    "[COUNTRY]",
    "[IDENTITY]",
}


def _replacement_token_for_entity(entity_group: str, entity_text: str) -> str | None:
    g = (entity_group or "").upper()
    if "PER" in g or "PERSON" in g or g in {"HUMAN", "INDIVIDUAL"}:
        return "[PERSON]"
    if "ORG" in g or "ORGANIZATION" in g or "COMPANY" in g:
        return "[COMPANY]"
    if "LOC" in g or "LOCATION" in g or "GPE" in g:
        # Heuristique: une LOC avec chiffres/tokens d'adresse -> adresse, sinon ville.
        if re.search(r"\b\d{1,4}\b", entity_text) or re.search(
            r"\b(rue|avenue|bd|boulevard|chemin|place|quai|route)\b", entity_text, flags=re.IGNORECASE
        ):
            return "[ADDRESS]"
        return "[CITY]"
    if "DATE" in g or "TIME" in g:
        return "[DATE]"
    return None


async def propose_spans_huggingface_ner(snippet_text: str) -> list[dict[str, Any]]:
    """Retourne des spans proposées (start/end relatifs au snippet).

    RGPD: on n'a pas besoin de stocker le snippet, seulement les offsets/hashes en audit.
    """
    if not settings.HF_API_KEY or not settings.HF_INFERENCE_URL:
        return []

    headers = {"Authorization": f"Bearer {settings.HF_API_KEY}"}
    payload: dict[str, Any] = {
        "inputs": snippet_text,
        # activation fréquente pour token-classification NER
        "parameters": {"aggregation_strategy": "simple"},
        "options": {"wait_for_model": True},
    }

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(settings.HF_INFERENCE_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    # HF peut renvoyer soit:
    # - une liste d'entités: [{"entity_group": "...", "score":..., "start":..., "end":..., "word":...}]
    # - un dict wrapper
    entities = None
    if isinstance(data, list):
        entities = data
    elif isinstance(data, dict):
        entities = data.get("entities") or data.get("output") or data.get("predictions")
    if not entities or not isinstance(entities, list):
        return []

    spans: list[dict[str, Any]] = []
    for ent in entities:
        try:
            start = ent.get("start", None)
            end = ent.get("end", None)
            entity_text = ent.get("word", None) or ent.get("entity", None) or ""
            entity_group = ent.get("entity_group", "") or ent.get("group", "") or ""
            score = float(ent.get("score", 0.0))
        except Exception:
            continue

        # Certains endpoints ne fournissent pas start/end.
        if start is None or end is None:
            # Fallback minimal: find la première occurrence du text (si assez long)
            entity_text_norm = (entity_text or "").strip()
            if len(entity_text_norm) < 3:
                continue
            idx = snippet_text.find(entity_text_norm)
            if idx < 0:
                continue
            start = idx
            end = idx + len(entity_text_norm)

        try:
            start_i = int(start)
            end_i = int(end)
        except Exception:
            continue

        if end_i <= start_i:
            continue

        replacement = _replacement_token_for_entity(entity_group, snippet_text[start_i:end_i])
        if not replacement or replacement not in ALLOWED_REPLACEMENT_TOKENS:
            continue

        spans.append(
            {
                "entity_type": replacement.strip("[]").lower(),
                "start": start_i,
                "end": end_i,
                "replacement_token": replacement,
                "confidence": score,
            }
        )

    return spans

