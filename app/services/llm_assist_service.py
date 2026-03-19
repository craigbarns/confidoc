"""ConfiDoc Backend — LLM assistive span suggestions (RGPD safe)."""

import hashlib
import json
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

ENTITY_TYPE_TO_TOKEN: dict[str, str] = {
    "EMAIL": "[EMAIL]",
    "PHONE": "[PHONE]",
    "IBAN": "[IBAN]",
    "BIC": "[BIC]",
    "SIREN": "[SIREN]",
    "SIRET": "[SIRET]",
    "VAT": "[VAT]",
    "COMPANY": "[COMPANY]",
    "ORG": "[COMPANY]",
    "PERSON": "[PERSON]",
    "ADDRESS": "[ADDRESS]",
    "CITY": "[CITY]",
    "DATE": "[DATE]",
    "AMOUNT": "[AMOUNT]",
    "INVOICE_REF": "[INVOICE_REF]",
    "REDACTED": "[REDACTED]",
    "COUNTRY": "[COUNTRY]",
    "IDENTITY": "[IDENTITY]",
}


def snippet_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def propose_spans_mistral(snippet_text: str) -> list[dict[str, Any]]:
    """Appelle Mistral et renvoie des spans proposées avec start/end relatifs au snippet."""
    if not settings.MISTRAL_API_KEY:
        return []

    system = (
        "Tu es un assistant de détection d'entités sensibles dans des documents comptables français. "
        "Tu dois renvoyer des spans uniquement au format JSON strict et sans aucun texte hors JSON. "
        "N'invente pas des valeurs: si tu n'es pas sûr, renvoie des spans vides."
    )
    user = f"""
Détecte uniquement ces entités si elles apparaissent dans le snippet ci-dessous:
EMAIL, PHONE, IBAN, BIC, SIREN, SIRET, VAT, COMPANY/ORG, PERSON, ADDRESS, CITY, DATE, AMOUNT, INVOICE_REF, COUNTRY.

Règles:
- start/end sont des indices caractères (0-based) dans le snippet.
- replacement_token doit être exactement un des tokens autorisés.
- confidence est un nombre entre 0 et 1.
- Retourne uniquement un JSON du type:
{{
  "spans": [
    {{"entity_type":"EMAIL","start":0,"end":10,"replacement_token":"[EMAIL]","confidence":0.9}}
  ]
}}

Snippet:
\"\"\"{snippet_text}\"\"\"
""".strip()

    payload = {
        "model": settings.MISTRAL_MODEL,
        "temperature": 0,
        "max_tokens": 300,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                f"{settings.MISTRAL_BASE_URL}/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.MISTRAL_API_KEY}"},
                json=payload,
            )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        spans = parsed.get("spans", [])
        cleaned: list[dict[str, Any]] = []
        for s in spans:
            try:
                entity_type = str(s["entity_type"]).upper()
                start = int(s["start"])
                end = int(s["end"])
                replacement_token = str(s["replacement_token"])
                confidence = float(s["confidence"])
            except Exception:
                continue
            if replacement_token not in ALLOWED_REPLACEMENT_TOKENS:
                # Fallback mapping si entity_type est fourni
                replacement_token = ENTITY_TYPE_TO_TOKEN.get(entity_type, replacement_token)
            if replacement_token not in ALLOWED_REPLACEMENT_TOKENS:
                continue
            if start < 0 or end <= start:
                continue
            cleaned.append(
                {
                    "entity_type": entity_type,
                    "start": start,
                    "end": end,
                    "replacement_token": replacement_token,
                    "confidence": confidence,
                }
            )
        return cleaned
    except Exception:
        return []


def build_snippets(text: str, max_snippets: int, snippet_chars: int) -> list[dict[str, Any]]:
    """Sélectionne des snippets autour de mots-clés (minimisation)."""
    lower = text.lower()
    keywords = [
        "facture",
        "tva",
        "montant",
        "règlement",
        "reglement",
        "client",
        "adresse",
        "iban",
        "bic",
        "siren",
        "siret",
        "v.a.t",
        "soci",
        "sas",
        "sci",
        "tarif",
        "pénalité",
        "penalite",
        "France",
    ]

    starts: list[int] = []
    for kw in keywords:
        idx = lower.find(kw.lower())
        if idx >= 0:
            starts.append(idx)

    # Fallback si rien trouvé
    if not starts:
        starts = [0, max(0, len(text) // 2 - snippet_chars // 2), max(0, len(text) - snippet_chars)]

    # Dedup + clamp
    starts = sorted(set(starts))
    selected: list[dict[str, Any]] = []
    for idx in starts[:max_snippets]:
        start = max(0, idx - (snippet_chars // 3))
        end = min(len(text), start + snippet_chars)
        snippet_text = text[start:end]
        selected.append(
            {
                "start": start,
                "end": end,
                "text": snippet_text,
                "sha256": snippet_sha256(snippet_text),
            }
        )
    return selected

