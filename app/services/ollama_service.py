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

async def generate_audit_with_ollama(payload: dict[str, Any], doc_type: str) -> dict[str, Any]:
    """IA locale comme Agent de contrôle métier (Reasoning strict)."""
    settings = get_settings()
    if not settings.OLLAMA_ENABLED:
        raise RuntimeError("OLLAMA_ENABLED=false")

    # Définition des règles métier selon le type
    rules = ""
    if doc_type in ["bilan", "compte_resultat", "accounting", "fiscal_2072"]:
        rules = (
            "1. CHK_EQUILIBRE : Le Total Actif doit être égal au Total Passif (si applicable).\n"
            "2. CHK_PRESENCE_MONTANTS : Vérifier que les lignes principales ne sont pas vides.\n"
            "3. CHK_COHERENCE_NET : Le résultat net affiché doit être logique avec l'exercice.\n"
            "4. CHK_TVA : Le montant de la TVA ou les charges doivent correspondre aux totaux."
        )
    else:
        rules = (
            "1. CHK_INTEGRITE : Vérifier la présence de tous les champs obligatoires (Noms, Dates).\n"
            "2. CHK_COHERENCE_DATES : Les dates de validité doivent être logiques.\n"
            "3. CHK_MONTANTS : Les totaux facturés doivent être justifiés."
        )

    prompt = (
        "Tu es un moteur de contrôle documentaire et d'audit comptable. "
        "Tu travailles UNIQUEMENT sur des données anonymisées structurées. "
        "Tu ne dois JAMAIS inventer un montant, ni compléter silencieusement une valeur absente, "
        "ni contourner ou masquer une incohérence.\n\n"
        "Règles d'évaluation (pour chaque vérification) :\n"
        "- 'passed': La règle est respectée et les données présentes le prouvent.\n"
        "- 'failed': Les données présentes contredisent la règle (ex: Actif != Passif).\n"
        "- 'inconclusive': Impossible de vérifier (champ manquant, tableau tronqué).\n\n"
        f"Voici les règles à contrôler :\n{rules}\n\n"
        "Format de sortie OBLIGATOIRE (JSON strict, aucun commentaire avant ou après) :\n"
        "{\n"
        "  \"global_status\": \"passed\" | \"failed\" | \"inconclusive\",\n"
        "  \"checks\": [\n"
        "    {\n"
        "      \"code\": \"CHK_CODE_NOM\",\n"
        "      \"description\": \"Description de la règle\",\n"
        "      \"status\": \"passed\" | \"failed\" | \"inconclusive\",\n"
        "      \"explanation\": \"Justification très brève basée uniquement sur la donnée.\"\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        f"Données anonymisées structurées fournies pour l'audit :\n{payload}\n"
    )

    body = {
        "model": settings.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.0,  # Zero hallu
        },
    }

    async with httpx.AsyncClient(timeout=float(settings.OLLAMA_TIMEOUT_SECONDS) * 1.5) as client:
        resp = await client.post(f"{settings.OLLAMA_BASE_URL}/api/generate", json=body)
    resp.raise_for_status()
    data = resp.json()
    
    return {
        "model": settings.OLLAMA_MODEL,
        "raw_response": (data or {}).get("response", ""),
    }

