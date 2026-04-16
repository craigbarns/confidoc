"""ConfiDoc — Pont d'extraction structurée (Docling retiré du runtime).

La plateforme s'appuie sur **Mistral OCR** pour le texte ; les tables / sections
pour l'agent de revue ne sont plus fournies par Docling (pas de dépendance HF
en conteneur). Les noms de fonctions sont conservés pour compatibilité des imports.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


async def extract_text_from_file_docling(
    file_content: bytes, extension: str = "pdf"
) -> tuple[str, dict[str, Any]]:
    """Délègue à Mistral OCR (Docling n'est plus utilisé)."""
    logger.info("docling_disabled_using_mistral_ocr")
    from app.services.mistral_ocr_service import extract_text_from_file

    return await extract_text_from_file(file_content, extension)


async def get_structured_content(file_content: bytes, extension: str = "pdf") -> dict[str, Any]:
    """Tables / sections pour l'agent de revue : non disponibles sans Docling."""
    del file_content, extension  # API inchangée
    return {"tables": [], "sections": [], "available": False}
