"""ConfiDoc — Anonymisation 100% LLM (Mistral Large).

Pas de regex, pas de patterns — uniquement un LLM qui identifie et remplace les PII.
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.config import get_settings
from app.core.json_utils import extract_json as _clean_json_response
from app.core.logging import get_logger
from app.core.tokens import (
    TOKEN_ADRESSE,
    TOKEN_DATE,
    TOKEN_DATE_NAISSANCE,
    TOKEN_EMAIL,
    TOKEN_IBAN,
    TOKEN_ID,
    TOKEN_MONTANT,
    TOKEN_NSS,
    TOKEN_PERSONNE,
    TOKEN_SIREN,
    TOKEN_SIRET,
    TOKEN_SOCIETE,
    TOKEN_TELEPHONE,
    TOKEN_TVA,
    TOKEN_VILLE,
)
from app.services.mistral_service import _chat_completion

logger = get_logger(__name__)


def _response_fingerprint(raw: str | None) -> dict[str, object]:
    payload = raw or ""
    return {
        "response_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "response_chars": len(payload),
    }


ANONYMIZATION_PROMPT = f"""Tu es un système d'anonymisation de documents confidentiels.

MISSION: Identifie TOUTES les informations personnelles/sensibles et remplace-les par des tokens.

RÈGLES STRICTES:
1. TU NE DOIS JAMAIS REFORMULER LE TEXTE. Tu dois retourner exactement le même texte, mot pour mot, ponctuation comprise, en remplaçant SEULEMENT les entités par les tokens.
2. Si tu modifies une seule virgule ou un saut de ligne, les index seront faux et le système plantera.
3. Remplace par ces tokens EXACTS :
   - Noms de personnes → {TOKEN_PERSONNE}
   - Emails → {TOKEN_EMAIL}
   - Téléphones → {TOKEN_TELEPHONE}
   - Adresses postales → {TOKEN_ADRESSE}
   - Villes / codes postaux → {TOKEN_VILLE}
   - SIRET → {TOKEN_SIRET}
   - SIREN → {TOKEN_SIREN}
   - IBAN/RIB → {TOKEN_IBAN}
   - Noms de sociétés → {TOKEN_SOCIETE}
   - Numéro TVA intracommunautaire → {TOKEN_TVA}
   - Dates de naissance → {TOKEN_DATE_NAISSANCE}
   - Autres dates → {TOKEN_DATE}
   - Numéros de sécurité sociale → {TOKEN_NSS}
   - Montants personnels (non agrégés) → {TOKEN_MONTANT}
   - Identifiants uniques divers → {TOKEN_ID}

2. Garde les informations comptables/financières génériques:
   - "Total actif", "Résultat net" → CONSERVER
   - Montants agrégés du bilan → CONSERVER
   - Postes comptables standards → CONSERVER

3. Format de réponse UNIQUEMENT JSON:
{{{{
  "texte_anonymise": "texte complet avec tokens de remplacement",
  "entites_detectees": [
    {{{{"type": "PERSONNE", "valeur_originale": "Jean Dupont", "position_debut": 123, "position_fin": 134, "token": "{TOKEN_PERSONNE}"}}}}
  ],
  "confiance": "high|medium|low",
  "nb_remplacements": 5
}}}}

Document à anonymiser:
---
{{text}}
---

Réponds UNIQUEMENT avec le JSON, sans texte avant ou après:"""


def _fallback_anonymize(text: str) -> str:
    """Anonymisation fallback deterministe si LLM echoue."""
    try:
        from app.services.dictionary_anonymization_service import anonymize_with_dictionary

        return str(anonymize_with_dictionary(text).get("anonymized_text") or "")
    except Exception as exc:
        logger.warning("llm_anonymization_dictionary_fallback_failed", error=str(exc))

    patterns = [
        (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", TOKEN_EMAIL),
        (r"\b(?:\+33|0)\s?[1-9](?:[\s.-]?\d{2}){4}\b", TOKEN_TELEPHONE),
        (
            r"\b[A-Z]{2}\d{2}[\s]?[A-Z0-9]{4}[\s]?(?:[A-Z0-9]{4}[\s]?){2,7}[A-Z0-9]{1,4}\b",
            TOKEN_IBAN,
        ),
        (r"\b\d{3}[\s.-]?\d{3}[\s.-]?\d{3}[\s.-]?\d{5}\b", TOKEN_SIRET),
    ]

    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result)
    return result


async def anonymize_with_llm(text: str) -> dict[str, Any]:
    """Anonymise un texte via Mistral Large.

    Args:
        text: Texte brut à anonymiser

    Returns:
        {
            "anonymized_text": "texte avec tokens",
            "entities": [...],
            "confidence": "high|medium|low",
            "count": N
        }
    """
    settings = get_settings()

    if getattr(settings, "SENSITIVE_CLIENT_MODE", False) is True:
        logger.info("llm_anonymization_skipped", reason="sensitive_client_mode")
        return {
            "anonymized_text": _fallback_anonymize(text),
            "entities": [],
            "confidence": "low",
            "count": 0,
            "method": "fallback:regex_sensitive_client_mode",
        }

    if not settings.MISTRAL_ENABLED or not settings.MISTRAL_API_KEY:
        logger.warning("llm_anonymization_skipped", reason="mistral_not_configured")
        # Fallback sur regex basiques
        return {
            "anonymized_text": _fallback_anonymize(text),
            "entities": [],
            "confidence": "low",
            "count": 0,
            "method": "fallback:regex",
        }

    # Limite la taille (coût + contexte)
    max_chars = 12000
    truncated_text = text[:max_chars]
    is_truncated = len(text) > max_chars

    if is_truncated:
        truncated_text += "\n...[suite du document tronquée pour l'anonymisation]..."

    prompt = ANONYMIZATION_PROMPT.format(text=truncated_text)

    try:
        raw_response = await _chat_completion(prompt, temperature=0.1)
    except Exception as exc:
        logger.error("llm_anonymization_api_error", error=str(exc))
        return {
            "anonymized_text": _fallback_anonymize(text),
            "entities": [],
            "confidence": "low",
            "count": 0,
            "method": "fallback:regex_after_error",
        }

    parsed = _clean_json_response(raw_response)
    if parsed is None:
        logger.warning("llm_anonymization_parse_failed", **_response_fingerprint(raw_response))
        return {
            "anonymized_text": _fallback_anonymize(text),
            "entities": [],
            "confidence": "low",
            "count": 0,
            "method": "fallback:regex_after_parse_error",
        }

    # Extrait le texte anonymisé
    anonymized_text = parsed.get("texte_anonymise", _fallback_anonymize(text))

    # Normalise les entités
    entities = []
    for e in parsed.get("entites_detectees", []):
        if isinstance(e, dict):
            entities.append(
                {
                    "entity_type": e.get("type", "UNKNOWN"),
                    "start_index": e.get("position_debut", 0),
                    "end_index": e.get("position_fin", 0),
                    "value_excerpt": e.get("valeur_originale", "")[:100],
                    "replacement": e.get("token", "[REDACTED]"),
                    "confidence": 0.9 if parsed.get("confiance") == "high" else 0.7,
                }
            )

    logger.info(
        "llm_anonymization_complete",
        nb_entites=len(entities),
        confiance=parsed.get("confiance", "unknown"),
        tronque=is_truncated,
    )

    return {
        "anonymized_text": anonymized_text,
        "entities": entities,
        "confidence": parsed.get("confiance", "medium"),
        "count": len(entities),
        "method": "llm:mistral-large",
    }


async def anonymize_document_full(text: str) -> tuple[str, list[dict]]:
    """Interface compatible avec l'ancien système.

    Returns:
        (anonymized_text, detections_list)
    """
    result = await anonymize_with_llm(text)
    return result["anonymized_text"], result["entities"]
