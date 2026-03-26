"""ConfiDoc — Extraction structurée 100% LLM (Mistral Large).

Pas de regex, pas de règles métier complexes.
Uniquement un prompt structuré + validation JSON.
"""

from __future__ import annotations

import json
from typing import Any

from app.config import get_settings
from app.core.logging import get_logger
from app.services.mistral_service import _chat_completion

logger = get_logger(__name__)

EXTRACTION_PROMPT = """Tu es un expert-comptable français. Extrais les informations clés du document ci-dessous.

RÈGLES ABSOLUES:
1. Réponds UNIQUEMENT en JSON valide, sans texte avant/après
2. N'invente aucune information - utilise null si non trouvé
3. Les montants sont en euros (nombre, sans séparateur de milliers)
4. Les dates au format JJ/MM/AAAA

CHAMPS À EXTRAIRE:
{
  "type_document": "bilan|compte_resultat|2072|releve_bancaire|facture|autre",
  "societe": {
    "denomination": "string|null",
    "siret": "string|null",
    "forme_juridique": "string|null"
  },
  "exercice": {
    "date_debut": "JJ/MM/AAAA|null",
    "date_fin": "JJ/MM/AAAA|null",
    "date_arrete": "JJ/MM/AAAA|null"
  },
  "montants_cles": [
    {"libelle": "string", "montant": number, "nature": "actif|passif|produit|charge|solde"}
  ],
  "totaux": {
    "total_actif": number|null,
    "total_passif": number|null,
    "resultat_net": number|null,
    "chiffre_affaires": number|null
  },
  "confiance": "high|medium|low"
}

CONSIGNES SPÉCIFIQUES:
- type_document: identifie précisément le type de document comptable
- montants_cles: extrait TOUS les montants significatifs avec leur nature comptable
- totaux: privilégie les totaux généraux (total actif/passif bilan, résultat net, etc.)
- confiance: "high" si sûr, "medium" si ambigu, "low" si incertain

Document à analyser:
---
{text}
---

JSON uniquement:"""


def _clean_json_response(raw: str) -> dict[str, Any] | None:
    """Extrait et parse le JSON de la réponse LLM."""
    if not raw:
        return None
    
    # Cherche le bloc JSON
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or start >= end:
        return None
    
    try:
        return json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        # Tentative de nettoyage
        cleaned = raw[start:end + 1]
        cleaned = cleaned.replace("\n", " ")
        cleaned = cleaned.replace("'", '"')
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None


def _validate_and_normalize(data: dict[str, Any]) -> dict[str, Any]:
    """Valide et normalise la structure extraite."""
    if not isinstance(data, dict):
        data = {}
    
    # Structure par défaut
    result = {
        "type_document": data.get("type_document") or "autre",
        "societe": {
            "denomination": data.get("societe", {}).get("denomination"),
            "siret": data.get("societe", {}).get("siret"),
            "forme_juridique": data.get("societe", {}).get("forme_juridique"),
        },
        "exercice": {
            "date_debut": data.get("exercice", {}).get("date_debut"),
            "date_fin": data.get("exercice", {}).get("date_fin"),
            "date_arrete": data.get("exercice", {}).get("date_arrete"),
        },
        "montants_cles": [],
        "totaux": {
            "total_actif": None,
            "total_passif": None,
            "resultat_net": None,
            "chiffre_affaires": None,
        },
        "confiance": data.get("confiance") or "low",
        "source": "llm:mistral-large",
    }
    
    # Normalise montants_cles
    montants = data.get("montants_cles", [])
    if isinstance(montants, list):
        for m in montants:
            if isinstance(m, dict) and m.get("montant") is not None:
                try:
                    montant_val = float(m["montant"])
                    result["montants_cles"].append({
                        "libelle": str(m.get("libelle", "")),
                        "montant": montant_val,
                        "nature": m.get("nature", "autre"),
                    })
                except (ValueError, TypeError):
                    pass
    
    # Normalise totaux
    totaux = data.get("totaux", {})
    if isinstance(totaux, dict):
        for key in ["total_actif", "total_passif", "resultat_net", "chiffre_affaires"]:
            val = totaux.get(key)
            if val is not None:
                try:
                    result["totaux"][key] = float(val)
                except (ValueError, TypeError):
                    pass
    
    return result


async def extract_with_llm(text: str) -> dict[str, Any]:
    """Extrait les données structurées d'un document via Mistral Large.
    
    Args:
        text: Texte anonymisé du document
        
    Returns:
        Structure normalisée avec type_document, montants, totaux, etc.
    """
    settings = get_settings()
    
    if not settings.MISTRAL_ENABLED or not settings.MISTRAL_API_KEY:
        logger.warning("llm_extraction_skipped", reason="mistral_not_configured")
        return _validate_and_normalize({})
    
    # Limite la taille du texte (coût + contexte LLM)
    max_chars = 8000
    truncated_text = text[:max_chars]
    if len(text) > max_chars:
        truncated_text += "\n...[texte tronqué]..."
    
    prompt = EXTRACTION_PROMPT.format(text=truncated_text)
    
    try:
        raw_response = await _chat_completion(prompt, temperature=0.1)
    except Exception as exc:
        logger.error("llm_extraction_api_error", error=str(exc))
        return _validate_and_normalize({})
    
    parsed = _clean_json_response(raw_response)
    if parsed is None:
        logger.warning("llm_extraction_parse_failed", raw=raw_response[:200])
        return _validate_and_normalize({})
    
    result = _validate_and_normalize(parsed)
    
    logger.info(
        "llm_extraction_complete",
        type_document=result["type_document"],
        confiance=result["confiance"],
        nb_montants=len(result["montants_cles"]),
    )
    
    return result
