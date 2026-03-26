"""LLM Fallback Extraction — Mistral Large comble les champs critiques manquants.

Pipeline :
  1. build_structured_dataset() extrait par regex (synchrone, rapide, gratuit)
  2. enrich_with_llm_fallback() est appelé en async sur les champs critiques encore null
     → appel Mistral Large ciblé, fusion dans le dataset avec source_hint "llm:mistral-large"

Usage (endpoint FastAPI) :
    structured = build_structured_dataset(...)
    structured = await enrich_with_llm_fallback(structured, extraction_text)
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Champs critiques par doc_type ─────────────────────────────────────────────
# (label FR, type attendu, description courte)
_CRITICAL_FIELDS_SPEC: dict[str, dict[str, tuple[str, str]]] = {
    "bilan": {
        "total_actif": ("Total actif", "montant € décimal"),
        "total_passif": ("Total passif", "montant € décimal"),
        "capitaux_propres": ("Capitaux propres", "montant € décimal"),
        "dettes_financieres": ("Dettes financières / emprunts bancaires", "montant € décimal"),
        "dettes_fournisseurs": ("Dettes fournisseurs", "montant € décimal"),
        "resultat_exercice": ("Résultat de l'exercice", "montant € décimal, négatif si perte"),
    },
    "compte_resultat": {
        "chiffre_affaires": ("Chiffre d'affaires", "montant € décimal"),
        "charges_externes": ("Charges externes / services extérieurs", "montant € décimal"),
        "resultat_exploitation": ("Résultat d'exploitation", "montant € décimal"),
        "resultat_courant": ("Résultat courant avant impôts", "montant € décimal"),
        "resultat_net": ("Résultat net / Bénéfice ou Perte", "montant € décimal"),
    },
    "fiscal_2072": {
        "revenus_bruts": ("Revenus bruts", "montant € décimal"),
        "frais_charges_hors_interets": ("Frais et charges hors intérêts", "montant € décimal"),
        "interets_emprunts": ("Intérêts d'emprunts", "montant € décimal"),
        "revenu_net_foncier": ("Revenu net foncier à répartir", "montant € décimal"),
        "denomination_sci": ("Dénomination de la société / SCI", "texte"),
        "date_cloture_exercice": ("Date de clôture de l'exercice", "date JJ/MM/AAAA"),
        "nombre_associes": ("Nombre d'associés", "entier"),
    },
    "etat_immobilisations": {
        "total_brut_immobilisations": ("Total brut des immobilisations", "montant € décimal"),
        "total_amortissements": ("Total amortissements cumulés", "montant € décimal"),
        "total_net_immobilisations": ("Valeur nette comptable totale", "montant € décimal"),
    },
    "releve_bancaire": {
        "solde_initial": ("Solde initial / ancien solde", "montant € décimal"),
        "solde_final": ("Nouveau solde / solde final", "montant € décimal"),
        "periode_debut": ("Date début de période", "date ISO AAAA-MM-JJ"),
        "periode_fin": ("Date fin de période", "date ISO AAAA-MM-JJ"),
    },
}

# Taille max du texte envoyé au LLM (tokens ≈ chars/4)
_MAX_TEXT_CHARS = 6000


def _build_prompt(doc_type: str, missing_fields: list[str], text: str) -> str:
    spec = _CRITICAL_FIELDS_SPEC.get(doc_type, {})
    fields_to_extract = {k: spec[k] for k in missing_fields if k in spec}
    if not fields_to_extract:
        return ""

    lines = []
    for field_key, (label, type_hint) in fields_to_extract.items():
        lines.append(f'  "{field_key}": // {label} — {type_hint}')

    truncated = text[:_MAX_TEXT_CHARS]
    if len(text) > _MAX_TEXT_CHARS:
        truncated += "\n[... texte tronqué ...]"

    return f"""Tu es un expert-comptable français spécialisé en lecture de documents financiers.
Type de document : {doc_type}

Extrait exactement les champs manquants ci-dessous depuis le texte fourni.
Réponds UNIQUEMENT en JSON valide, sans texte autour, sans commentaires.
Si un champ est introuvable dans le texte, utilise null (jamais de valeur inventée).

Champs à extraire :
{{
{chr(10).join(lines)}
}}

Texte du document :
---
{truncated}
---

JSON uniquement :"""


def _parse_llm_response(raw: str, expected_keys: list[str]) -> dict[str, Any]:
    """Extrait et valide le JSON retourné par le LLM."""
    if not raw:
        return {}
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or start >= end:
        return {}
    try:
        obj = json.loads(raw[start : end + 1])
    except Exception:
        # Tentative de nettoyage des commentaires JS (// ...)
        cleaned = re.sub(r"//[^\n]*", "", raw[start : end + 1])
        try:
            obj = json.loads(cleaned)
        except Exception:
            return {}
    if not isinstance(obj, dict):
        return {}
    # Ne garder que les clés attendues
    return {k: obj[k] for k in expected_keys if k in obj}


def _coerce_llm_value(value: Any, field_key: str, doc_type: str) -> Any:
    """Convertit et valide basiquement la valeur retournée par le LLM."""
    if value is None:
        return None
    spec = _CRITICAL_FIELDS_SPEC.get(doc_type, {})
    type_hint = (spec.get(field_key) or ("", ""))[1]

    if "montant" in type_hint or "décimal" in type_hint:
        try:
            v = float(str(value).replace(",", ".").replace("\u00a0", "").replace(" ", ""))
            # Garde-fou : rejeter les valeurs aberrantes (codes PCG, etc.)
            if abs(v) > 5_000_000_000:
                return None
            return round(v, 2)
        except (ValueError, TypeError):
            return None

    if "entier" in type_hint:
        try:
            return int(float(str(value)))
        except (ValueError, TypeError):
            return None

    if "date" in type_hint:
        s = str(value).strip()
        # Accepter JJ/MM/AAAA ou AAAA-MM-JJ
        if re.match(r"^\d{2}/\d{2}/\d{4}$", s) or re.match(r"^\d{4}-\d{2}-\d{2}$", s):
            return s
        return None

    # texte
    s = str(value).strip()
    return s if s and s.lower() != "null" else None


async def enrich_with_llm_fallback(
    dataset: dict[str, Any],
    extraction_text: str,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """
    Enrichit un dataset structuré en appelant Mistral Large pour les champs critiques manquants.

    - Ne fait RIEN si aucun champ critique manquant (sauf force=True).
    - Ne fait RIEN si Mistral n'est pas configuré.
    - Fusionne les valeurs LLM avec source_hint="llm:mistral-large" et confidence=0.72.
    - Recalcule la qualité après enrichissement.

    Retourne le dataset (modifié en place).
    """
    from app.config import get_settings
    from app.services.mistral_service import _chat_completion

    settings = get_settings()
    if not settings.MISTRAL_ENABLED or not settings.MISTRAL_API_KEY:
        return dataset

    doc_type: str = dataset.get("doc_type") or ""
    quality: dict = dataset.get("quality") or {}
    critical_missing: list[str] = quality.get("critical_missing_fields") or []

    if not force and not critical_missing:
        return dataset  # Rien à faire

    spec = _CRITICAL_FIELDS_SPEC.get(doc_type, {})
    # On ne demande au LLM que les champs dans notre spec (pas les champs hors périmètre)
    fields_to_ask = [f for f in critical_missing if f in spec]
    if not fields_to_ask:
        return dataset

    prompt = _build_prompt(doc_type, fields_to_ask, extraction_text)
    if not prompt:
        return dataset

    logger.info(
        "llm_fallback_extraction_start",
        doc_type=doc_type,
        missing_fields=fields_to_ask,
        text_chars=len(extraction_text),
    )

    try:
        raw = await _chat_completion(prompt, temperature=0.0)
    except Exception as exc:
        logger.warning("llm_fallback_extraction_failed", error=str(exc), doc_type=doc_type)
        return dataset

    parsed = _parse_llm_response(raw, fields_to_ask)
    if not parsed:
        logger.warning("llm_fallback_extraction_empty_response", doc_type=doc_type, raw=raw[:200])
        return dataset

    fields: dict[str, Any] = dataset.setdefault("fields", {})
    enriched: list[str] = []

    for field_key, raw_value in parsed.items():
        coerced = _coerce_llm_value(raw_value, field_key, doc_type)
        if coerced is None:
            continue
        # Ne remplace que si le champ est effectivement null/absent
        existing = (fields.get(field_key) or {}).get("value")
        if existing is not None and existing != "" and existing != []:
            continue
        fields[field_key] = {
            "value": coerced,
            "confidence": 0.72,
            "source_hint": "llm:mistral-large",
            "review_required": False,
        }
        enriched.append(field_key)

    if enriched:
        logger.info(
            "llm_fallback_extraction_enriched",
            doc_type=doc_type,
            enriched_fields=enriched,
        )
        # Recalcule critical_missing_fields après enrichissement
        new_missing = [
            f for f in critical_missing
            if (fields.get(f) or {}).get("value") in (None, "", [])
        ]
        dataset["quality"] = {**quality, "critical_missing_fields": new_missing}
        # Ajouter flag de provenance LLM dans les quality_flags
        q_flags: list[str] = list(dataset["quality"].get("quality_flags") or [])
        if "llm_fallback_used" not in q_flags:
            q_flags.append("llm_fallback_used")
        dataset["quality"]["quality_flags"] = sorted(q_flags)

    return dataset
