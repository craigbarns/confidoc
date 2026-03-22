"""ConfiDoc Backend — Ollama client for anonymized AI summaries + validation Pydantic."""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import get_settings
from app.services.ollama_schemas import AuditResult, SummaryResult

# 1er appel + jusqu'à 2 retentes si JSON / schéma invalides
_MAX_VALIDATION_ATTEMPTS = 3


def extract_json_object_from_llm(raw_text: str) -> dict[str, Any] | None:
    """Extrait le premier objet JSON `{...}` du texte LLM (tolère du bruit autour)."""
    if not raw_text:
        return None
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or start >= end:
        return None
    try:
        obj = json.loads(raw_text[start : end + 1])
        if isinstance(obj, dict) and obj:
            return obj
    except Exception:
        pass
    return None


def _format_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", ()))
        msg = err.get("msg", "")
        if loc:
            parts.append(f"{loc}: {msg}")
        else:
            parts.append(msg)
    return "; ".join(parts) if parts else str(exc)


async def _post_generate(body: dict[str, Any], *, timeout_scale: float = 2.0) -> str:
    settings = get_settings()
    timeout = float(settings.OLLAMA_TIMEOUT_SECONDS) * timeout_scale
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{settings.OLLAMA_BASE_URL}/api/generate", json=body)
    resp.raise_for_status()
    data = resp.json()
    return (data or {}).get("response", "") or ""


async def generate_summary_with_ollama(payload: dict[str, Any]) -> dict[str, Any]:
    """Génère une synthèse ; valide SummaryResult avec jusqu'à 3 tentatives (repair prompt)."""
    settings = get_settings()
    if not settings.OLLAMA_ENABLED:
        raise RuntimeError("OLLAMA_ENABLED=false")

    base_prompt = (
        "Tu es un assistant comptable. "
        "Tu reçois uniquement des données anonymisées. "
        "Règles strictes: n'invente pas, ne complète pas les champs manquants, "
        "indique clairement ce qui est incertain, et propose les points de revue.\n\n"
        "Format de sortie obligatoire (JSON strict, clés exactes) :\n"
        "{"
        '"resume_executif": "...",'
        '"points_cles": ["..."],'
        '"anomalies_ou_alertes": ["..."],'
        '"questions_de_revue": ["..."],'
        '"confiance_globale": 0.0'
        "}\n"
        "confiance_globale doit être un nombre entre 0.0 et 1.0.\n\n"
        f"Données anonymisées:\n{payload}"
    )

    repair_suffix = ""
    last_raw = ""
    last_failure = ""

    for attempt in range(1, _MAX_VALIDATION_ATTEMPTS + 1):
        if repair_suffix:
            prompt = base_prompt + repair_suffix
        else:
            prompt = base_prompt

        body = {
            "model": settings.OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }
        last_raw = await _post_generate(body, timeout_scale=2.0)
        parsed = extract_json_object_from_llm(last_raw)
        if parsed is None:
            last_failure = "Réponse non JSON ou objet vide : fournir un unique objet JSON."
            repair_suffix = (
                "\n\n--- CORRECTION OBLIGATOIRE ---\n"
                f"Problème détecté : {last_failure}\n"
                "Réponds uniquement avec un objet JSON valide, sans markdown ni texte avant/après, "
                "avec exactement les clés : resume_executif, points_cles, anomalies_ou_alertes, "
                "questions_de_revue, confiance_globale.\n"
            )
            continue

        try:
            validated = SummaryResult.model_validate(parsed)
            return {
                "model": settings.OLLAMA_MODEL,
                "raw_response": last_raw,
                "validated": validated.model_dump(),
                "validation_ok": True,
                "validation_attempts": attempt,
            }
        except ValidationError as exc:
            last_failure = _format_validation_error(exc)
            repair_suffix = (
                "\n\n--- CORRECTION OBLIGATOIRE ---\n"
                f"Ton JSON précédent est invalide : {last_failure}\n"
                "Corrige et renvoie uniquement l'objet JSON corrigé, "
                "avec les clés exactes : resume_executif, points_cles, anomalies_ou_alertes, "
                "questions_de_revue, confiance_globale (nombre 0.0–1.0).\n"
            )

    return {
        "model": settings.OLLAMA_MODEL,
        "raw_response": last_raw,
        "validated": None,
        "validation_ok": False,
        "validation_attempts": _MAX_VALIDATION_ATTEMPTS,
        "last_validation_error": last_failure or "validation_inconnue",
    }


async def generate_audit_with_ollama(payload: dict[str, Any], doc_type: str) -> dict[str, Any]:
    """Agent d'audit ; valide AuditResult avec jusqu'à 3 tentatives."""
    settings = get_settings()
    if not settings.OLLAMA_ENABLED:
        raise RuntimeError("OLLAMA_ENABLED=false")

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

    base_prompt = (
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
        '  "global_status": "passed" | "failed" | "inconclusive",\n'
        '  "checks": [\n'
        "    {\n"
        '      "code": "CHK_CODE_NOM",\n'
        '      "description": "Description de la règle",\n'
        '      "status": "passed" | "failed" | "inconclusive",\n'
        '      "explanation": "Justification très brève basée uniquement sur la donnée."\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Le tableau checks doit contenir au moins une entrée.\n\n"
        f"Données anonymisées structurées fournies pour l'audit :\n{payload}\n"
    )

    repair_suffix = ""
    last_raw = ""
    last_failure = ""

    for attempt in range(1, _MAX_VALIDATION_ATTEMPTS + 1):
        prompt = base_prompt + repair_suffix if repair_suffix else base_prompt

        body = {
            "model": settings.OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0},
        }
        last_raw = await _post_generate(body, timeout_scale=1.5)

        parsed = extract_json_object_from_llm(last_raw)
        if parsed is None:
            last_failure = "Réponse non JSON ou objet vide."
            repair_suffix = (
                "\n\n--- CORRECTION OBLIGATOIRE ---\n"
                f"Problème : {last_failure}\n"
                "Renvoie uniquement un objet JSON avec global_status et checks "
                "(au moins un élément dans checks). Chaque check a code, description, status, explanation.\n"
            )
            continue

        try:
            validated = AuditResult.model_validate(parsed)
            return {
                "model": settings.OLLAMA_MODEL,
                "raw_response": last_raw,
                "validated": validated.model_dump(),
                "validation_ok": True,
                "validation_attempts": attempt,
            }
        except ValidationError as exc:
            last_failure = _format_validation_error(exc)
            repair_suffix = (
                "\n\n--- CORRECTION OBLIGATOIRE ---\n"
                f"JSON invalide : {last_failure}\n"
                "Corrige : global_status parmi passed/failed/inconclusive ; "
                "checks = tableau non vide d'objets avec code, description, status, explanation.\n"
            )

    return {
        "model": settings.OLLAMA_MODEL,
        "raw_response": last_raw,
        "validated": None,
        "validation_ok": False,
        "validation_attempts": _MAX_VALIDATION_ATTEMPTS,
        "last_validation_error": last_failure or "validation_inconnue",
    }
