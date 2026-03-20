"""ConfiDoc Backend — Ollama client for anonymized AI summaries."""

from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings


async def generate_summary_with_ollama(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate an accounting-oriented summary from anonymized payload only."""
    settings = get_settings()
    if not settings.OLLAMA_ENABLED:
        raise RuntimeError("OLLAMA_ENABLED=false")

    prompt = (
        "Tu es un assistant comptable. "
        "Tu reçois uniquement des données anonymisées. "
        "Règles strictes: n'invente pas, ne complète pas les champs manquants, "
        "indique clairement ce qui est incertain, et propose les points de revue.\n\n"
        "Format de sortie obligatoire (JSON strict):\n"
        "{"
        "\"resume_executif\": \"...\","
        "\"points_cles\": [\"...\"],"
        "\"anomalies_ou_alertes\": [\"...\"],"
        "\"questions_de_revue\": [\"...\"],"
        "\"confiance_globale\": 0.0"
        "}\n\n"
        f"Données anonymisées:\n{payload}"
    )

    body = {
        "model": settings.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.1,
        },
    }

    async with httpx.AsyncClient(timeout=float(settings.OLLAMA_TIMEOUT_SECONDS)) as client:
        resp = await client.post(f"{settings.OLLAMA_BASE_URL}/api/generate", json=body)
    resp.raise_for_status()
    data = resp.json()
    text = (data or {}).get("response", "")
    return {
        "model": settings.OLLAMA_MODEL,
        "raw_response": text,
    }

