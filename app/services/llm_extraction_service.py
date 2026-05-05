"""ConfiDoc — Extraction structurée 100% LLM (Mistral Large).

Pas de regex, pas de règles métier complexes.
Uniquement un prompt structuré + validation JSON.
"""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import suppress
from typing import Any

from app.config import get_settings
from app.core.logging import get_logger
from app.services.audit_service import run_internal_audit
from app.services.business_rule_service import validate_accounting_coherence
from app.services.mistral_service import _chat_completion
from app.services.pcg_mapping_service import suggest_pcg_code

logger = get_logger(__name__)


def _response_fingerprint(raw: str | None) -> dict[str, object]:
    payload = raw or ""
    return {
        "response_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "response_chars": len(payload),
    }

EXTRACTION_PROMPT = """Tu es un expert-comptable français.
Extrais les informations clés du document ci-dessous.

RÈGLES ABSOLUES:
1. Réponds UNIQUEMENT en JSON valide, sans texte avant/après
2. N'invente aucune information - utilise null si non trouvé
3. Les montants sont en euros (nombre, sans séparateur de milliers)
4. Les dates au format JJ/MM/AAAA

RÈGLES PCG (PLAN COMPTABLE GÉNÉRAL):
Pour chaque montant extrait, suggère le code PCG à 6 chiffres le plus approprié
(ex: 606100, 622600, 706000).
- 606xxx: Énergie, fournitures
- 613xxx: Locations
- 622xxx: Honoraires
- 625xxx: Déplacements
- 626xxx: Télécoms/Poste
- 641xxx: Salaires
- 706xxx: Prestations services

CHAMPS À EXTRAIRE:
{{
  "type_document": "bilan|compte_resultat|2072|releve_bancaire|facture|autre",
  "societe": {{
    "denomination": "string|null",
    "siret": "string|null",
    "forme_juridique": "string|null"
  }},
  "exercice": {{
    "date_debut": "JJ/MM/AAAA|null",
    "date_fin": "JJ/MM/AAAA|null",
    "date_arrete": "JJ/MM/AAAA|null"
  }},
  "montants_cles": [
    {{
      "libelle": "string",
      "montant": number,
      "nature": "actif|passif|produit|charge|solde",
      "pcg_code": "string|null",
      "source_snippet": "fragment de texte original exact"
    }}
  ],
  "totaux": {{
    "total_actif": {{ "montant": number|null, "source_snippet": "string|null" }},
    "total_passif": {{ "montant": number|null, "source_snippet": "string|null" }},
    "resultat_net": {{ "montant": number|null, "source_snippet": "string|null" }},
    "chiffre_affaires": {{ "montant": number|null, "source_snippet": "string|null" }}
  }},
  "confiance": "high|medium|low"
}}

CONSIGNES SPÉCIFIQUES:
- type_document: identifie précisément le type de document comptable
- montants_cles: extrait TOUS les montants significatifs avec leur nature comptable.
- pcg_code: suggère le code comptable français à 6 chiffres le plus probable.
- source_snippet: TRÈS IMPORTANT. Recopie exactement le fragment de texte
  (environ 30-50 caractères) où le chiffre a été trouvé.
- totaux: privilégie les totaux généraux.
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
            "total_actif": {"montant": None, "source_snippet": None},
            "total_passif": {"montant": None, "source_snippet": None},
            "resultat_net": {"montant": None, "source_snippet": None},
            "chiffre_affaires": {"montant": None, "source_snippet": None},
        },
        "confiance": data.get("confiance") or "low",
        "source": data.get("source") or "llm:mistral-large",
        "business_rules": {}
    }

    # Normalise montants_cles
    montants = data.get("montants_cles", [])
    if isinstance(montants, list):
        for m in montants:
            if isinstance(m, dict) and m.get("montant") is not None:
                try:
                    montant_val = float(m["montant"])
                    libelle = str(m.get("libelle", ""))
                    nature = str(m.get("nature", "autre"))

                    # Récupère le code PCG suggéré par le LLM ou utilise l'heuristique
                    pcg_code = str(m.get("pcg_code") or "")
                    if not pcg_code:
                        suggestion = suggest_pcg_code(libelle, nature)
                        pcg_code = suggestion["code"]

                    result["montants_cles"].append({
                        "libelle": libelle,
                        "montant": montant_val,
                        "nature": nature,
                        "pcg_code": pcg_code,
                        "source_snippet": str(m.get("source_snippet", ""))
                    })
                except (ValueError, TypeError):
                    pass

    # Normalise totaux
    totaux_raw = data.get("totaux", {})
    if isinstance(totaux_raw, dict):
        for key in ["total_actif", "total_passif", "resultat_net", "chiffre_affaires"]:
            raw_val = totaux_raw.get(key)
            if isinstance(raw_val, dict):
                try:
                    raw_amount = raw_val.get("montant")
                    m = float(raw_amount) if raw_amount is not None else None
                    result["totaux"][key]["montant"] = m
                    result["totaux"][key]["source_snippet"] = str(
                        raw_val.get("source_snippet") or ""
                    )
                except (ValueError, TypeError):
                    pass
            elif raw_val is not None:  # Backwards compatibility
                with suppress(ValueError, TypeError):
                    result["totaux"][key]["montant"] = float(raw_val)

    # Appel au service de règles métier comptables
    result["business_rules"] = validate_accounting_coherence(result)

    return result


def _semantic_chunking(text: str, max_chars: int = 15000) -> str:
    """
    Réduit le texte en gardant les sections clés (Bilan, CR) pour éviter
    le phénomène de 'Lost in the middle' du LLM sur les plaquettes de 50 pages.
    """
    if len(text) <= max_chars:
        return text

    logger.info("llm_semantic_chunking_triggered", original_length=len(text))

    # 1. Chercher les pages "Bilan" (Actif/Passif) et "Compte de résultat"
    keywords = [
        r"(?i)\bbilan\b",
        r"(?i)total\s*actif",
        r"(?i)total\s*passif",
        r"(?i)compte\s*de\s*r[ée]sultat",
        r"(?i)r[ée]sultat\s*de\s*l[' ]?exercice",
        r"(?i)2072",
        r"(?i)liasse\s*fiscale"
    ]

    # Diviser par pages ou gros blocs (approximation)
    blocks = re.split(r"(?:\n\s*){3,}", text)

    scored_blocks = []
    for i, block in enumerate(blocks):
        score = sum(1 for kw in keywords if re.search(kw, block))
        scored_blocks.append((score, i, block))

    # Trier par score décroissant et garder les meilleurs blocs jusqu'à max_chars
    scored_blocks.sort(key=lambda x: x[0], reverse=True)

    selected_indices = set()
    current_len = 0
    for _score, i, block in scored_blocks:
        if current_len + len(block) > max_chars:
            break
        selected_indices.add(i)
        current_len += len(block)

    # Reconstruire dans l'ordre original
    final_text = "\n\n[...] Section ignorée [...]\n\n".join(
        blocks[i] for i in range(len(blocks)) if i in selected_indices
    )

    return final_text


async def extract_with_llm(text: str, doc_type: str | None = None) -> dict[str, Any]:
    """Extrait les données structurées d'un document via Mistral Large.

    Args:
        text: Texte anonymisé du document

    Returns:
        Structure normalisée avec type_document, montants, totaux, etc.
    """
    settings = get_settings()

    if getattr(settings, "SENSITIVE_CLIENT_MODE", False) is True:
        logger.info("llm_extraction_skipped", reason="sensitive_client_mode")
        return _validate_and_normalize({"source": "disabled:sensitive_client_mode"})

    if not settings.MISTRAL_ENABLED or not settings.MISTRAL_API_KEY:
        logger.warning("llm_extraction_skipped", reason="mistral_not_configured")
        return _validate_and_normalize({})

    # Utilisation de la segmentation sémantique au lieu du simple truncate bête
    truncated_text = _semantic_chunking(text, max_chars=15000)

    prompt = EXTRACTION_PROMPT.format(text=truncated_text)
    if doc_type:
        prompt = f"Type de document attendu: {doc_type}\n\n{prompt}"

    try:
        raw_response = await _chat_completion(prompt, temperature=0.1)
    except Exception as exc:
        logger.error("llm_extraction_api_error", error=str(exc))
        return _validate_and_normalize({})

    parsed = _clean_json_response(raw_response)
    if parsed is None:
        logger.warning("llm_extraction_parse_failed", **_response_fingerprint(raw_response))
        return _validate_and_normalize({})

    result = _validate_and_normalize(parsed)

    # ── Audit Interne Automatisé ──────────────────────────────────────────
    audit_results = run_internal_audit(result, text)
    result.update(audit_results)
    # ──────────────────────────────────────────────────────────────────────

    logger.info(
        "llm_extraction_complete",
        type_document=result["type_document"],
        confiance=result["confiance"],
        nb_montants=len(result["montants_cles"]),
        audit_risk_score=result.get("audit_risk_score", 0),
    )

    return result
