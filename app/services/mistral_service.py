"""ConfiDoc Backend — Mistral AI client (drop-in replacement for Kimi)."""

from __future__ import annotations

import json
from typing import Any, Literal

import httpx
from pydantic import ValidationError

from app.config import get_settings
from app.core.logging import get_logger
from app.services.ollama_schemas import AuditResult, SummaryResult

logger = get_logger(__name__)

_MAX_VALIDATION_ATTEMPTS = 3


def _sensitive_mode_enabled(settings: Any) -> bool:
    return getattr(settings, "SENSITIVE_CLIENT_MODE", False) is True


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
    if _sensitive_mode_enabled(settings):
        logger.info("mistral_chat_blocked_sensitive_mode", prompt_length=len(prompt))
        raise RuntimeError("SENSITIVE_CLIENT_MODE=true")
    if not settings.MISTRAL_ENABLED:
        raise RuntimeError("MISTRAL_ENABLED=false")
    if not settings.MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY manquant")

    logger.info("mistral_chat_request", model=settings.MISTRAL_MODEL, prompt_length=len(prompt))

    headers = {
        "Authorization": f"Bearer {settings.MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.MISTRAL_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Tu réponds uniquement en JSON strict, sans texte autour.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
    }
    timeout = float(settings.MISTRAL_TIMEOUT_SECONDS)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{settings.MISTRAL_BASE_URL.rstrip('/')}/v1/chat/completions",
                headers=headers,
                json=body,
            )
        resp.raise_for_status()
        payload = resp.json() or {}
        choices = payload.get("choices") or []
        if not choices:
            logger.warning("mistral_chat_empty_choices")
            return ""
        msg = (choices[0] or {}).get("message") or {}
        content = str(msg.get("content") or "")
        logger.info(
            "mistral_chat_response", response_length=len(content), has_content=bool(content)
        )
        return content
    except Exception as exc:
        error_msg = str(exc) or repr(exc) or "unknown error"
        logger.error(
            "mistral_chat_error",
            error=error_msg,
            error_type=type(exc).__name__,
            error_attrs=dir(exc) if hasattr(exc, "response") else None,
        )
        raise


async def generate_summary_with_mistral(
    payload: dict[str, Any],
    *,
    prudent_mode: bool = False,
    mode: Literal["summary", "review", "draft", "question"] = "summary",
) -> dict[str, Any]:
    settings = get_settings()
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
        "Tu es un assistant comptable expert. Tu reçois uniquement des données anonymisées.\n"
        "N'invente jamais de chiffres. Si un champ est manquant, dis-le explicitement.\n"
        "Source de vérité non négociable: les faits qualité backend ci-dessous.\n"
        "Interdiction stricte: ne pas contredire ready_for_ai, ready_for_ai_core, needs_review,\n"
        "critical_missing_fields, suspicious_fields et quality_flags.\n"
        "Si critical_missing_fields est vide ([]), ne jamais écrire qu'il existe des champs critiques manquants.\n"
        "INTERDICTION ABSOLUE DE REPETER LES NOMS DES FLAGS DANS TA REPONSE: tu ne dois JAMAIS mentionner\n"
        "les termes techniques 'ready_for_ai', 'ready_for_ai_core', 'needs_review', 'critical_missing_fields',\n"
        "'quality_flags', 'suspicious_fields' ou 'coverage_ratio' dans le texte destiné à l'utilisateur.\n"
        "Ces champs sont des consignes internes uniquement.\n"
        "\n"
        "INTERDICTION ABSOLUE D'INFÉRENCE COMPTABLE NON VALIDÉE PAR LE BACKEND:\n"
        "- Ne jamais additionner, soustraire, comparer ou rapprocher librement des postes comptables entre eux\n"
        "- Ne jamais signaler d'incohérence arithmétique sauf si elle apparaît dans quality_flags\n"
        "- Ne jamais écrire qu'un montant est incohérent ou contradictoire sans signal backend explicite\n"
        "- Les seules alertes comptables autorisées sont celles listées dans quality_flags backend\n"
        "\n"
        "RÈGLE SUR LES CHAMPS SUSPECTS:\n"
        "- Si un champ est dans suspicious_fields, le présenter uniquement comme 'à vérifier' ou 'calculé'\n"
        "- Si suspicious_fields est vide, ne pas inventer de doute supplémentaire\n"
        "\n"
        "Réponds avec JSON strict contenant exactement: "
        "resume_executif (string), points_cles (array of strings), anomalies_ou_alertes (array of strings), "
        "questions_de_revue (array of strings), confiance_globale (float entre 0.0 et 1.0, ex: 0.85).\n"
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
            last_failure = f"erreur_appel_mistral: {type(exc).__name__}: {exc}"
            logger.error(
                "mistral_api_error",
                error=last_failure,
                attempt=attempt,
                model=settings.MISTRAL_MODEL,
            )
            repair_suffix = ""
            if attempt < _MAX_VALIDATION_ATTEMPTS:
                continue
            return {
                "model": settings.MISTRAL_MODEL,
                "raw_response": "",
                "validated": None,
                "validation_ok": False,
                "validation_attempts": attempt,
                "last_validation_error": last_failure,
            }
        parsed = _extract_json_object(last_raw)
        if parsed is None:
            last_failure = f"Réponse non JSON: {last_raw[:200]}"
            repair_suffix = "\n\nJSON invalide. Renvoie uniquement un objet JSON avec les clés exactes demandées."
            continue
        try:
            validated = SummaryResult.model_validate(parsed)
            return {
                "model": settings.MISTRAL_MODEL,
                "raw_response": last_raw,
                "validated": validated.model_dump(),
                "validation_ok": True,
                "validation_attempts": attempt,
            }
        except ValidationError as exc:
            last_failure = _format_validation_error(exc)
            repair_suffix = f"\n\nJSON invalide: {last_failure}. Corrige le JSON."
    return {
        "model": settings.MISTRAL_MODEL,
        "raw_response": last_raw,
        "validated": None,
        "validation_ok": False,
        "validation_attempts": _MAX_VALIDATION_ATTEMPTS,
        "last_validation_error": last_failure or "validation_inconnue",
    }


async def stream_mistral_response(
    user_content: str,
    *,
    system_prompt: str | None = None,
    temperature: float = 0.3,
):
    """Async generator — yield text chunks from a streaming Mistral completion."""
    settings = get_settings()
    if _sensitive_mode_enabled(settings):
        logger.info("mistral_stream_blocked_sensitive_mode", prompt_length=len(user_content))
        yield "Mode client sensible actif : IA externe désactivée."
        return
    if not settings.MISTRAL_ENABLED or not settings.MISTRAL_API_KEY:
        yield "Mode streaming non disponible (MISTRAL_ENABLED=false ou clé manquante)."
        return
    headers = {
        "Authorization": f"Bearer {settings.MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }
    messages = [
        {
            "role": "system",
            "content": system_prompt
            or (
                "Tu es un assistant comptable et juridique expert, integre dans ConfiDoc. "
                "REGLES ABSOLUES: "
                "1) Ne JAMAIS inventer de montants, ventilations ou repartitions qui ne sont PAS explicitement dans le document. "
                "2) Ne JAMAIS creer de tableaux speculatifs avec des montants fictifs (ex: 'CIR 300 000 euros'). "
                "3) Quand un poste comptable manque de detail dans le document, dire CLAIREMENT: "
                "'Le document ne fournit pas la ventilation de ce poste.' "
                "4) Toujours distinguer ce qui EST dans le document (fait) de ce qui POURRAIT etre (hypothese). "
                "5) Pour les hypotheses, utiliser: 'Ce poste pourrait inclure...' SANS inventer de montants. "
                "6) Ne jamais qualifier un element de non-conforme ou anormal sans preuve chiffree dans le document. "
                "7) Repondre en francais, de maniere professionnelle et factuelle."
            ),
        },
        {"role": "user", "content": user_content},
    ]
    body = {
        "model": settings.MISTRAL_MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    try:
        async with httpx.AsyncClient(timeout=float(settings.MISTRAL_TIMEOUT_SECONDS)) as client:
            async with client.stream(
                "POST",
                f"{settings.MISTRAL_BASE_URL.rstrip('/')}/v1/chat/completions",
                headers=headers,
                json=body,
            ) as resp:
                if resp.status_code != 200:
                    await resp.aread()
                    yield f"[Erreur Mistral {resp.status_code}: réponse fournisseur indisponible]"
                    return
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        chunk = json.loads(data)
                        content = (
                            ((chunk.get("choices") or [{}])[0]).get("delta", {}).get("content")
                            or ""
                        )
                        if content:
                            yield content
                    except Exception:
                        continue
    except httpx.TimeoutException:
        yield "[Erreur: délai d'attente Mistral dépassé]"
    except Exception as exc:
        yield f"[Erreur Mistral: {exc}]"


async def generate_audit_with_mistral(payload: dict[str, Any], doc_type: str) -> dict[str, Any]:
    settings = get_settings()
    quality = payload.get("quality", {}) or {}
    quality_facts = {
        "ready_for_ai": bool(quality.get("ready_for_ai", False)),
        "ready_for_ai_core": bool(quality.get("ready_for_ai_core", False)),
        "needs_review": bool(quality.get("needs_review", True)),
        "critical_missing_fields": quality.get("critical_missing_fields", []) or [],
        "quality_flags": quality.get("quality_flags", []) or [],
    }
    prompt = (
        "Tu es un auditeur documentaire expert. Entrée anonymisée uniquement.\n"
        "Les facts qualité backend ci-dessous sont non discutables.\n"
        "Interdiction stricte de contredire: ready_for_ai, ready_for_ai_core, needs_review,\n"
        "critical_missing_fields, quality_flags.\n"
        "Si critical_missing_fields est vide ([]), n'affirme jamais qu'il y a des champs critiques manquants.\n"
        "Ne mentionne JAMAIS les noms techniques des flags dans tes explications.\n"
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
            last_failure = f"erreur_appel_mistral: {type(exc).__name__}"
            repair_suffix = ""
            if attempt < _MAX_VALIDATION_ATTEMPTS:
                continue
            return {
                "model": settings.MISTRAL_MODEL,
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
            return {
                "model": settings.MISTRAL_MODEL,
                "raw_response": last_raw,
                "validated": validated.model_dump(),
                "validation_ok": True,
                "validation_attempts": attempt,
            }
        except ValidationError as exc:
            last_failure = _format_validation_error(exc)
            repair_suffix = f"\n\nJSON invalide: {last_failure}. Corrige le JSON."
    return {
        "model": settings.MISTRAL_MODEL,
        "raw_response": last_raw,
        "validated": None,
        "validation_ok": False,
        "validation_attempts": _MAX_VALIDATION_ATTEMPTS,
        "last_validation_error": last_failure or "validation_inconnue",
    }
