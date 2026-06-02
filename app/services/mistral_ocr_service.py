"""ConfiDoc — OCR 100% Mistral (mistral-ocr-latest).

Remplace PyMuPDF/Tesseract par l'OCR Mistral natif.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

import httpx

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Redis cache helpers (OCR result by SHA256) ──────────────────────────

_REDIS_CACHE_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 jours


def _ocr_cache_key(file_hash: str) -> str:
    return f"confidoc:ocr:v1:{file_hash}"


async def _get_redis() -> Any | None:
    """Renvoie un client Redis async, ou None si indisponible."""
    try:
        import redis.asyncio as aioredis

        from app.config import get_settings

        settings = get_settings()
        return aioredis.from_url(
            settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2
        )
    except Exception:
        return None


async def _fetch_ocr_from_cache(file_hash: str) -> dict[str, Any] | None:
    """Récupère un résultat OCR depuis Redis. Renvoie None si miss ou erreur."""
    redis = await _get_redis()
    if redis is None:
        return None
    try:
        raw = await redis.get(_ocr_cache_key(file_hash))
        await redis.close()
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None


async def _store_ocr_in_cache(file_hash: str, text: str, meta: dict[str, Any]) -> None:
    """Stocke un résultat OCR dans Redis (TTL 7 jours). Ignore silencieusement les erreurs."""
    redis = await _get_redis()
    if redis is None:
        return
    try:
        payload = json.dumps({"text": text, "meta": meta}, default=str)
        await redis.setex(_ocr_cache_key(file_hash), _REDIS_CACHE_TTL_SECONDS, payload)
        await redis.close()
    except Exception:
        pass


async def extract_text_with_mistral_ocr(
    file_content: bytes,
    filename: str = "",
    mime_type: str = "application/pdf",
) -> dict[str, Any]:
    """Extrait le texte d'un PDF/image via Mistral OCR.

    Args:
        file_content: Contenu brut du fichier
        filename: Nom du fichier (pour l'extension)
        mime_type: Type MIME (application/pdf, image/png, etc.)

    Returns:
        {
            "text": "texte extrait",
            "pages": [{"page": 1, "text": "...", "markdown": "..."}],
            "model": "mistral-ocr-latest",
            "confidence": "high"
        }
    """
    settings = get_settings()

    if getattr(settings, "SENSITIVE_CLIENT_MODE", False) is True:
        logger.info("mistral_ocr_skipped", reason="sensitive_client_mode")
        return {
            "text": "",
            "pages": [],
            "model": "none",
            "confidence": "low",
            "error": "Sensitive client mode disables external OCR",
        }

    if not settings.MISTRAL_ENABLED or not settings.MISTRAL_API_KEY:
        logger.warning("mistral_ocr_skipped", reason="not_configured")
        return {
            "text": "",
            "pages": [],
            "model": "none",
            "confidence": "low",
            "error": "Mistral not configured",
        }

    # Encode le fichier en base64
    base64_content = base64.b64encode(file_content).decode("utf-8")

    # Détermine le format
    if "pdf" in mime_type.lower() or filename.lower().endswith(".pdf"):
        document_url = f"data:application/pdf;base64,{base64_content}"
    else:
        # Images
        ext = filename.split(".")[-1].lower() if "." in filename else "png"
        document_url = f"data:image/{ext};base64,{base64_content}"

    headers = {
        "Authorization": f"Bearer {settings.MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }

    # Appel API OCR Mistral - FORCE le modèle OCR (pas le chat!)
    ocr_model = "mistral-ocr-latest"  # HARDCODÉ: ne pas utiliser settings.MISTRAL_MODEL
    body = {
        "model": ocr_model,
        "document": {
            "type": "document_url",
            "document_url": document_url,
        },
    }

    try:
        logger.info("mistral_ocr_request", model=ocr_model, file_size=len(file_content))
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.MISTRAL_BASE_URL.rstrip('/')}/v1/ocr",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            result = resp.json()
            logger.info("mistral_ocr_response", status=resp.status_code, keys=list(result.keys()))
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response else 0
        logger.error("mistral_ocr_http_error", status=status_code)
        return {
            "text": "",
            "pages": [],
            "model": ocr_model,
            "confidence": "low",
            "error": f"HTTP {status_code or '?'}",
        }
    except Exception as exc:
        logger.error("mistral_ocr_api_error", error=str(exc), error_type=type(exc).__name__)
        return {"text": "", "pages": [], "model": ocr_model, "confidence": "low", "error": str(exc)}

    # Parse le résultat - Mistral OCR retourne 'pages' avec 'markdown' dans chaque page
    pages = result.get("pages", [])
    logger.info("mistral_ocr_pages", page_count=len(pages))

    # Debug: log first page structure
    if pages:
        logger.info(
            "mistral_ocr_first_page",
            keys=list(pages[0].keys()) if isinstance(pages[0], dict) else "not_dict",
        )

    all_text = "\n\n".join([p.get("markdown", p.get("text", "")) for p in pages])

    logger.info(
        "mistral_ocr_complete",
        pages=len(pages),
        chars=len(all_text),
        model=ocr_model,
    )

    return {
        "text": all_text,
        "pages": [
            {
                "page": i + 1,
                "text": p.get("text", ""),
                "markdown": p.get("markdown", ""),
            }
            for i, p in enumerate(pages)
        ],
        "model": ocr_model,
        "confidence": "high" if pages else "low",
    }


async def extract_text_from_file(
    content: bytes,
    extension: str = "pdf",
) -> tuple[str, dict[str, Any]]:
    """Interface compatible avec anonymization_service.extract_text_from_file.

    Ajoute un cache Redis par SHA256 du fichier pour éviter les appels
    API redondants (coût Mistral et latence).

    Returns:
        (texte, metadata)
    """
    file_hash = hashlib.sha256(content).hexdigest()
    settings = get_settings()
    if getattr(settings, "SENSITIVE_CLIENT_MODE", False) is True:
        logger.info("mistral_ocr_file_skipped", reason="sensitive_client_mode")
        return "", {
            "extension": extension,
            "method": "disabled:sensitive_client_mode",
            "model": "none",
            "pages": 0,
            "error": "Sensitive client mode disables external OCR",
        }

    # ── Cache hit ──
    cached = await _fetch_ocr_from_cache(file_hash)
    if cached is not None:
        logger.info("ocr_cache_hit", sha256=file_hash[:16], extension=extension)
        return cached["text"], cached["meta"]

    # ── Cache miss → appel Mistral ──
    mime_types = {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "tiff": "image/tiff",
        "tif": "image/tiff",
    }

    mime = mime_types.get(extension.lower(), "application/octet-stream")

    result = await extract_text_with_mistral_ocr(
        file_content=content,
        filename=f"document.{extension}",
        mime_type=mime,
    )

    meta: dict[str, Any] = {
        "extension": extension,
        "method": "mistral_ocr",
        "model": result.get("model"),
        "pages": len(result.get("pages", [])),
    }

    if result.get("error"):
        meta["error"] = result["error"]
        return "", meta

    text = result["text"]

    # ── Stocker dans le cache ──
    await _store_ocr_in_cache(file_hash, text, meta)

    return text, meta
