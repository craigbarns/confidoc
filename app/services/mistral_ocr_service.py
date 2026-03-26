"""ConfiDoc — OCR 100% Mistral (mistral-ocr-latest).

Remplace PyMuPDF/Tesseract par l'OCR Mistral natif.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


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
    
    if not settings.MISTRAL_ENABLED or not settings.MISTRAL_API_KEY:
        logger.warning("mistral_ocr_skipped", reason="not_configured")
        return {
            "text": "",
            "pages": [],
            "model": "none",
            "confidence": "low",
            "error": "Mistral not configured"
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
        }
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
    except Exception as exc:
        logger.error("mistral_ocr_api_error", error=str(exc), error_type=type(exc).__name__)
        return {
            "text": "",
            "pages": [],
            "model": ocr_model,
            "confidence": "low",
            "error": str(exc)
        }
    
    # Parse le résultat - Mistral OCR retourne 'pages' avec 'markdown' dans chaque page
    pages = result.get("pages", [])
    logger.info("mistral_ocr_pages", page_count=len(pages))
    
    # Debug: log first page structure
    if pages:
        logger.info("mistral_ocr_first_page", keys=list(pages[0].keys()) if isinstance(pages[0], dict) else "not_dict")
    
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
    
    Returns:
        (texte, metadata)
    """
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
    
    meta = {
        "extension": extension,
        "method": "mistral_ocr",
        "model": result.get("model"),
        "pages": len(result.get("pages", [])),
    }
    
    if result.get("error"):
        meta["error"] = result["error"]
        # Fallback: retourne vide
        return "", meta
    
    return result["text"], meta
