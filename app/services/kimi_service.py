"""ConfiDoc Backend — Kimi client for anonymized AI summaries + audit validation."""

from __future__ import annotations

import json
from typing import Any, Literal

import httpx
from pydantic import ValidationError

from app.config import get_settings
from app.services.ollama_schemas import AuditResult, SummaryResult

_MAX_VALIDATION_ATTEMPTS = 3


def _extract_json_object(raw_text: str) -> dict[str, Any] | None:
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
        return None
    return None


def _format_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", ()))
        msg = err.get("msg", "")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts) if parts else str(exc)


async def _chat_completion(prompt: str, *, temperature: float) -> str:
    settings = get_settings()
    if not settings.KIMI_ENABLED:
        raise RuntimeError("KIMI_ENABLED=false")
    if not settings.KIMI_API_KEY:
        raise RuntimeError("KIMI_API_KEY manquant")
    headers = {
        "Authorization": f"Bearer {settings.KIMI_API_KEY}",
        "Content-Type": "application/json",
    }
    model_name = settings.KIMI_MODEL
    # Moonshot quirk: some models (ex: kimi-k2.5) only accept temperature=1.
    effective_temperature = 1.0 if "k2.5" in model_name.lower() else temperature
    body = {
        "model": settings.KIMI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Tu réponds uniquement en JSON strict, sans texte autour.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": effective_temperature,
    }
    timeout = float(settings.KIMI_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{settings.KIMI_BASE_URL.rstrip('/')}/chat/completions",
            headers=headers,
            json=body,
        )
    resp.raise_for_status()
    payload = resp.json() or {}
    choices = payload.get("choices") or []
    if not choices:
        return ""
    msg = (choices[0] or {}).get("message") or {}
    return str(msg.get("content") or "")


async def generate_summary_with_kimi(
    payload: dict[str, Any],
    *,
    prudent_mode: bool = False,
    mode: Literal["summary", "review", "draft", "question"] = "summary",
) -> dict[str, Any]:
    quality = payload.get("quality", {}) or {}
    critical_missing_fields = quality.get("critical_missing_fields", []) or []
    quality_facts = {
        "ready_for_ai": bool(quality.get("ready_for_ai", False)),
        "ready_for_ai_core": bool(quality.get("ready_for_ai_core", False)),
        "needs_review": bool(quality.get("needs_review", True)),
        "critical_missing_fields": critical_missing_fields,
        "quality_flags": quality.get("quality_flags", []) or [],
        "coverage_ratio": quality.get("coverage_ratio"),
    }

    mode_instruction = {
        "summary": (
            "Mission: produire une synthèse comptable courte et actionnable pour un collaborateur.\n"
            "Format attendu: 5 points clés max, 3 alertes max, 2 questions de revue max.\n"
        ),
        "review": (
            "Mission: aide à la revue. Priorise les montants/sections à vérifier en premier.\n"
            "Format attendu: points_cles=priorités de contrôle, anomalies_ou_alertes=risques concrets,\n"
            "questions_de_revue=questions de vérification opérationnelles.\n"
        ),
        "draft": (
            "Mission: rédaction assistée. resume_executif doit être une note prête à l'emploi\n"
            "(email client ou note interne), claire et professionnelle.\n"
        ),
        "question": (
            "Mission: répondre à la question utilisateur en s'appuyant uniquement sur les facts backend.\n"
            "Format attendu: resume_executif=réponse courte, points_cles=preuves/facts, anomalies_ou_alertes=limites,\n"
            "questions_de_revue=questions de vérification utiles si incertitude.\n"
        ),
    }[mode]

    base_prompt = (
        "Tu es un assistant comptable. Tu reçois uniquement des données anonymisées.\n"
        "N'invente jamais de chiffres. Si un champ est manquant, dis-le explicitement.\n"
        "Source de vérité non négociable: les faits qualité backend ci-dessous.\n"
        "Interdiction stricte: ne pas contredire ready_for_ai, ready_for_ai_core, needs_review,\n"
        "critical_missing_fields et quality_flags.\n"
        "Si critical_missing_fields est vide ([]), ne jamais écrire qu'il existe des champs critiques manquants.\n"
        "INTERDICTION ABSOLUE DE CALCUL COMPTABLE:\n"
        "- Ne jamais additionner, soustraire ou comparer des postes comptables entre eux\n"
        "- Ne jamais vérifier si capitaux_propres + resultat_exercice = total_passif\n"
        "- Ne jamais signaler d'incohérence arithmétique sauf si explicitement dans quality_flags\n"
        "- Le résultat_exercice est souvent DÉJÀ inclus dans capitaux_propres : ne pas les additionner\n"
        "- Les seules alertes comptables autorisées sont celles listées dans quality_flags backend\n"
        "Réponds avec JSON strict contenant exactement: "
        "resume_executif, points_cles, anomalies_ou_alertes, questions_de_revue, confiance_globale.\n"
    )
    base_prompt += mode_instruction
    if prudent_mode:
        base_prompt += (
            "Mode prudent activé: souligne les limites et recommande la revue humaine "
            "quand la qualité source est incomplète.\n"
        )
    base_prompt += f"\nFacts qualité backend (non discutables):\n{quality_facts}\n"
    base_prompt += f"\nDonnées:\n{payload}"

    repair_suffix = ""
    last_raw = ""
    last_failure = ""
    for attempt in range(1, _MAX_VALIDATION_ATTEMPTS + 1):
        prompt = base_prompt + repair_suffix
        try:
            last_raw = await _chat_completion(prompt, temperature=0.1)
        except Exception as exc:
            last_failure = f"erreur_appel_kimi: {type(exc).__name__}"
            repair_suffix = ""
            if attempt < _MAX_VALIDATION_ATTEMPTS:
                continue
            settings = get_settings()
            return {
                "model": settings.KIMI_MODEL,
                "raw_response": "",
                "validated": None,
                "validation_ok": False,
                "validation_attempts": attempt,
                "last_validation_error": last_failure,
            }
        parsed = _extract_json_object(last_raw)
        if parsed is None:
            last_failure = "Réponse non JSON."
            repair_suffix = (
                "\n\nJSON invalide. Renvoie uniquement un objet JSON avec les clés exactes demandées."
            )
            continue
        try:
            validated = SummaryResult.model_validate(parsed)
            settings = get_settings()
            return {
                "model": settings.KIMI_MODEL,
                "raw_response": last_raw,
                "validated": validated.model_dump(),
                "validation_ok": True,
                "validation_attempts": attempt,
            }
        except ValidationError as exc:
            last_failure = _format_validation_error(exc)
            repair_suffix = f"\n\nJSON invalide: {last_failure}. Corrige le JSON."
    settings = get_settings()
    return {
        "model": settings.KIMI_MODEL,
        "raw_response": last_raw,
        "validated": None,
        "validation_ok": False,
        "validation_attempts": _MAX_VALIDATION_ATTEMPTS,
        "last_validation_error": last_failure or "validation_inconnue",
    }


async def generate_audit_with_kimi(payload: dict[str, Any], doc_type: str) -> dict[str, Any]:
    quality = payload.get("quality", {}) or {}
    quality_facts = {
        "ready_for_ai": bool(quality.get("ready_for_ai", False)),
        "ready_for_ai_core": bool(quality.get("ready_for_ai_core", False)),
        "needs_review": bool(quality.get("needs_review", True)),
        "critical_missing_fields": quality.get("critical_missing_fields", []) or [],
        "quality_flags": quality.get("quality_flags", []) or [],
    }
    prompt = (
        "Tu es un auditeur documentaire. Entrée anonymisée uniquement.\n"
        "Les facts qualité backend ci-dessous sont non discutables.\n"
        "Interdiction stricte de contredire: ready_for_ai, ready_for_ai_core, needs_review,\n"
        "critical_missing_fields, quality_flags.\n"
        "Si critical_missing_fields est vide ([]), n'affirme jamais qu'il y a des champs critiques manquants.\n"
        "Réponds en JSON strict avec: global_status, checks[].\n"
        "Chaque check: code, description, status(passed|failed|inconclusive), explanation.\n"
        f"Doc type cible: {doc_type}\n"
        f"Facts qualité backend (non discutables):\n{quality_facts}\n"
        f"Données:\n{payload}"
    )
    repair_suffix = ""
    last_raw = ""
    last_failure = ""
    for attempt in range(1, _MAX_VALIDATION_ATTEMPTS + 1):
        try:
            last_raw = await _chat_completion(prompt + repair_suffix, temperature=0.0)
        except Exception as exc:
            last_failure = f"erreur_appel_kimi: {type(exc).__name__}"
            repair_suffix = ""
            if attempt < _MAX_VALIDATION_ATTEMPTS:
                continue
            settings = get_settings()
            return {
                "model": settings.KIMI_MODEL,
                "raw_response": "",
                "validated": None,
                "validation_ok": False,
                "validation_attempts": attempt,
                "last_validation_error": last_failure,
            }
        parsed = _extract_json_object(last_raw)
        if parsed is None:
            last_failure = "Réponse non JSON."
            repair_suffix = "\n\nJSON invalide. Renvoie uniquement l'objet JSON attendu."
            continue
        try:
            validated = AuditResult.model_validate(parsed)
            settings = get_settings()
            return {
                "model": settings.KIMI_MODEL,
                "raw_response": last_raw,
                "validated": validated.model_dump(),
                "validation_ok": True,
                "validation_attempts": attempt,
            }
        except ValidationError as exc:
            last_failure = _format_validation_error(exc)
            repair_suffix = f"\n\nJSON invalide: {last_failure}. Corrige le JSON."
    settings = get_settings()
    return {
        "model": settings.KIMI_MODEL,
        "raw_response": last_raw,
        "validated": None,
        "validation_ok": False,
        "validation_attempts": _MAX_VALIDATION_ATTEMPTS,
        "last_validation_error": last_failure or "validation_inconnue",
    }
