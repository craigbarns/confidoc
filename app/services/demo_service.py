"""Public demo result service.

The public demo is intentionally read-only: it only processes the bundled
``demo_doc.pdf`` and never writes a document row.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.services.anonymization_service import anonymize_text, classify_document_type
from app.services.extraction.service import extract_text_from_file_with_meta
from app.services.reidentification_risk_service import analyze_reidentification_risk

logger = get_logger(__name__)

DEMO_DOC_PATH = Path(__file__).resolve().parent.parent / "static" / "demo_doc.pdf"
DEMO_CACHE_KEY = "confidoc:demo:public_result:v2"
_memory_demo_cache: dict[str, Any] | None = None


_EXPORT_POLICIES = {
    "low": {
        "label": "Export autorise",
        "severity": "success",
        "message": (
            "Risque residuel faible. Document exploitable pour une demonstration IA securisee."
        ),
    },
    "medium": {
        "label": "Revue conseillee",
        "severity": "warning",
        "message": "Usage interne acceptable. Revue humaine recommandee avant partage externe.",
    },
    "high": {
        "label": "Validation obligatoire",
        "severity": "danger",
        "message": "Risque eleve. Validation humaine obligatoire avant export ou partage.",
    },
    "critical": {
        "label": "Export bloque",
        "severity": "critical",
        "message": "Risque critique. Renforcer l'anonymisation avant toute diffusion.",
    },
}


def _summarize_entities(detections: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in detections:
        entity_type = str(item.get("entity_type") or "unknown").upper()
        replacement = str(item.get("replacement") or "")
        if replacement.startswith("[") and replacement.endswith("]"):
            entity_type = replacement.strip("[]").split("_", 1)[0].upper()
        summary[entity_type] = summary.get(entity_type, 0) + 1
    return summary


def _excerpt(text: str, max_chars: int = 3200) -> str:
    clean = (text or "").strip()
    if len(clean) <= max_chars:
        return clean
    return clean[:max_chars].rstrip() + "\n..."


def _export_policy_for_risk(level: str | None) -> dict[str, str]:
    return _EXPORT_POLICIES.get(str(level or "low").lower(), _EXPORT_POLICIES["low"])


def _build_demo_proof(result: dict[str, Any]) -> dict[str, Any]:
    risk = result.get("risk") if isinstance(result.get("risk"), dict) else {}
    policy = _export_policy_for_risk(str(risk.get("level") or "low"))
    signals = risk.get("signals") if isinstance(risk.get("signals"), list) else []
    signal_count = sum(
        int(item.get("occurrences", 1))
        for item in signals
        if isinstance(item, dict)
    )

    return {
        "title": "Preuve DPO ConfiDoc",
        "generated_at": datetime.now(UTC).isoformat(),
        "export_policy": policy,
        "residual_signals_count": signal_count,
        "control_points": [
            "Document de demonstration traite en lecture seule, sans upload utilisateur.",
            "Extraction texte puis anonymisation avant tout usage IA.",
            "Entites sensibles remplacees par des tokens explicites et auditables.",
            "Score de risque de reidentification calcule avant export.",
            "Rapport PDF generable pour tracer la methode, les entites et la politique d'export.",
        ],
    }


def _build_mock_demo_result(reason: str | None = None) -> dict[str, Any]:
    """Return a deterministic fallback payload for investor/demo contexts."""
    detections = [
        {
            "entity_type": "person_name",
            "start_index": 3,
            "end_index": 14,
            "value_excerpt": "Jean Dupont",
            "replacement": "[PERSONNE_1]",
        },
        {
            "entity_type": "company",
            "start_index": 26,
            "end_index": 43,
            "value_excerpt": "DUPONT CONSEIL SAS",
            "replacement": "[SOCIETE_1]",
        },
        {
            "entity_type": "siren",
            "start_index": 51,
            "end_index": 62,
            "value_excerpt": "123 456 789",
            "replacement": "[SIREN_1]",
        },
        {
            "entity_type": "amount",
            "start_index": 82,
            "end_index": 91,
            "value_excerpt": "450 000 €",
            "replacement": "[MONTANT_1]",
        },
        {
            "entity_type": "date",
            "start_index": 108,
            "end_index": 118,
            "value_excerpt": "12/03/2026",
            "replacement": "[DATE_1]",
        },
    ]
    result = {
        "status": "ready",
        "source": "mock_demo_fallback",
        "is_mock": True,
        "filename": "demo_doc.pdf",
        "document_type": "bilan",
        "pages": 2,
        "extraction_method": "mock_payload",
        "extraction_provider": "fallback",
        "extraction_model": "deterministic_demo_payload",
        "extraction_meta": {
            "method": "mock_payload",
            "provider": "fallback",
            "model": "deterministic_demo_payload",
            "pages": 2,
        },
        "original_excerpt": (
            "M. Jean Dupont\n"
            "Societe: DUPONT CONSEIL SAS\n"
            "SIREN 123 456 789\n"
            "Capital social: 450 000 €\n"
            "Document date du 12/03/2026\n"
            "Objet: bilan annuel et annexes de gestion."
        ),
        "anonymized_excerpt": (
            "M. [PERSONNE_1]\n"
            "Societe: [SOCIETE_1]\n"
            "SIREN [SIREN_1]\n"
            "Capital social: [MONTANT_1]\n"
            "Document date du [DATE_1]\n"
            "Objet: bilan annuel et annexes de gestion."
        ),
        "detections": detections,
        "detections_count": len(detections),
        "entity_summary": {
            "PERSONNE": 1,
            "SOCIETE": 1,
            "SIREN": 1,
            "MONTANT": 1,
            "DATE": 1,
        },
        "risk": {
            "score": 0.08,
            "level": "low",
            "recommendation": (
                "Fallback mock active. La demonstration reste exploitable pour le pitch "
                "et signale clairement qu'il s'agit d'un payload de secours."
            ),
            "signals": [],
        },
        "trust_signals": [
            "Payload de secours signale explicitement dans l'interface.",
            "Aucune donnee utilisateur n'est stockee.",
            "Tokens stables pour conserver le sens metier.",
            "Score de risque calcule avant export.",
        ],
    }
    if reason:
        result["fallback_reason"] = reason
    result["proof"] = _build_demo_proof(result)
    return result


def _provider_from_extraction_meta(meta: dict[str, Any]) -> str:
    method = str(meta.get("method") or "").lower()
    if method == "mistral_ocr":
        return "mistral"
    if method.startswith("ocr_"):
        return str(meta.get("ocr_engine") or "local_ocr")
    if "pymupdf" in method:
        return "pymupdf"
    return "local"


async def _compute_demo_result() -> dict[str, Any]:
    """Compute the bundled demo result through the same extraction path as uploads."""
    if not DEMO_DOC_PATH.exists():
        raise FileNotFoundError(f"Demo document not found: {DEMO_DOC_PATH}")

    content = DEMO_DOC_PATH.read_bytes()
    original_text, extraction_meta = await extract_text_from_file_with_meta(content, "pdf")
    if not original_text.strip():
        raise ValueError("Demo document extraction returned empty text")

    document_type = classify_document_type(original_text, DEMO_DOC_PATH.name)
    anonymized_text, detections, _registry = anonymize_text(
        original_text,
        profile="dataset_accounting_pseudo",
        document_type=document_type,
    )
    entity_summary = _summarize_entities(detections)
    risk = analyze_reidentification_risk(anonymized_text, entity_summary)
    risk_payload = risk.to_dict()
    extraction_provider = _provider_from_extraction_meta(extraction_meta)

    result = {
        "status": "ready",
        "source": "bundled_demo_doc",
        "is_mock": False,
        "filename": DEMO_DOC_PATH.name,
        "document_type": document_type,
        "pages": int(extraction_meta.get("pages") or 0),
        "extraction_method": extraction_meta.get("method") or "unknown",
        "extraction_provider": extraction_provider,
        "extraction_model": extraction_meta.get("model") or extraction_provider,
        "extraction_meta": {
            "method": extraction_meta.get("method") or "unknown",
            "provider": extraction_provider,
            "model": extraction_meta.get("model") or extraction_provider,
            "pages": int(extraction_meta.get("pages") or 0),
        },
        "original_excerpt": _excerpt(original_text),
        "anonymized_excerpt": _excerpt(anonymized_text),
        "detections": detections[:80],
        "detections_count": len(detections),
        "entity_summary": entity_summary,
        "risk": risk_payload,
        "trust_signals": [
            "OCR execute avant anonymisation.",
            "Texte original jamais envoye au LLM de discussion.",
            "Tokens stables pour conserver le sens metier.",
            "Score de risque calcule avant export.",
        ],
    }
    result["proof"] = _build_demo_proof(result)
    return result


def build_demo_audit_pdf(result: dict[str, Any]) -> bytes:
    """Generate a downloadable DPO proof PDF from the public demo payload."""
    from app.services.pdf_audit_report_service import generate_audit_pdf

    proof = result.get("proof")
    if not isinstance(proof, dict):
        proof = _build_demo_proof(result)

    risk_info = result.get("risk") if isinstance(result.get("risk"), dict) else {}
    risk_info = {
        "score": float(risk_info.get("score") or 0.0),
        "level": str(risk_info.get("level") or "low"),
        "recommendation": str(
            risk_info.get("recommendation")
            or proof.get("export_policy", {}).get("message", "")
        ),
        "human_validated": False,
    }

    entity_summary_raw = result.get("entity_summary")
    entity_summary: dict[str, int] = {}
    if isinstance(entity_summary_raw, dict):
        for key, value in entity_summary_raw.items():
            try:
                entity_summary[str(key)] = int(value)
            except (TypeError, ValueError):
                continue

    generated_at = str(proof.get("generated_at") or datetime.now(UTC).isoformat())
    audit_entries = [
        {
            "timestamp": generated_at,
            "action": "public_demo:extract",
            "method": "GET",
            "status_code": 200,
            "details": {
                "filename": result.get("filename", "demo_doc.pdf"),
                "pages": result.get("pages", 0),
                "method": result.get("extraction_method", "unknown"),
            },
        },
        {
            "timestamp": generated_at,
            "action": "public_demo:anonymize",
            "method": "LOCAL",
            "status_code": 200,
            "details": {
                "entities": result.get("detections_count", 0),
                "profile": "dataset_accounting_pseudo",
            },
        },
        {
            "timestamp": generated_at,
            "action": "public_demo:risk_score",
            "method": "LOCAL",
            "status_code": 200,
            "details": {
                "risk_level": risk_info["level"],
                "risk_score": risk_info["score"],
            },
        },
        {
            "timestamp": generated_at,
            "action": "public_demo:export_policy",
            "method": "LOCAL",
            "status_code": 200,
            "details": {
                "policy": proof.get("export_policy", {}).get("label", "Export autorise"),
            },
        },
    ]

    document_info = {
        "document_id": "public-demo",
        "filename": str(result.get("filename") or "demo_doc.pdf"),
        "created_at": generated_at,
        "doc_type": str(result.get("document_type") or "auto"),
        "status": "demo_ready",
    }

    pdf_output = generate_audit_pdf(
        document_info=document_info,
        risk_info=risk_info,
        entity_summary=entity_summary,
        audit_entries=audit_entries,
        anonymized_text_preview=str(result.get("anonymized_excerpt") or ""),
    )
    if isinstance(pdf_output, bytes):
        return pdf_output
    if isinstance(pdf_output, bytearray):
        return bytes(pdf_output)
    return str(pdf_output).encode("latin-1")


async def _get_redis() -> Any | None:
    try:
        import redis.asyncio as aioredis

        from app.config import get_settings

        settings = get_settings()
        return aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=1,
        )
    except Exception as exc:
        logger.debug("demo_redis_unavailable", error=str(exc))
        return None


async def warm_demo_cache() -> None:
    """Pre-compute and cache the public demo result."""
    global _memory_demo_cache

    try:
        result = await _compute_demo_result()
    except Exception as exc:
        logger.warning("demo_cache_warm_failed", error=str(exc), action="using_mock_fallback")
        result = _build_mock_demo_result(str(exc))

    _memory_demo_cache = result

    redis_client = await _get_redis()
    if redis_client is None:
        logger.info("demo_cache_warmed_memory", detections=result["detections_count"])
        return

    try:
        async with redis_client as redis_conn:
            await redis_conn.set(DEMO_CACHE_KEY, json.dumps(result, ensure_ascii=False))
        logger.info("demo_cache_warmed", detections=result["detections_count"])
    except Exception as exc:
        logger.warning("demo_cache_store_failed", error=str(exc))


async def get_demo_result() -> dict[str, Any] | None:
    """Return the warmed public demo result, or None while warming."""
    if _memory_demo_cache is not None:
        return _memory_demo_cache

    redis_client = await _get_redis()
    if redis_client is None:
        return _build_mock_demo_result("redis_unavailable")

    try:
        async with redis_client as redis_conn:
            raw = await redis_conn.get(DEMO_CACHE_KEY)
    except Exception as exc:
        logger.warning("demo_cache_fetch_failed", error=str(exc))
        return _build_mock_demo_result(str(exc))

    if not raw:
        return _build_mock_demo_result("cache_miss")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return _build_mock_demo_result("invalid_cached_json")

    if isinstance(parsed, dict):
        return parsed
    return _build_mock_demo_result("invalid_cached_payload")
