"""ConfiDoc — Anonymisation par dictionnaire gouverné (V3).

Remplacement déterministe basé sur des patterns prédéfinis.
Cette version est une façade utilisant les modules spécialisés d'anonymisation.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.services.entity_registry import EntityRegistry
from app.services.anonymization.detector import detect_entities
from app.services.anonymization.pseudonymizer import apply_business_pseudonyms
from app.services.anonymization.cleanup import clean_ocr_artifacts

logger = get_logger(__name__)


def anonymize_with_dictionary(text: str, profile: str = "moderate") -> dict[str, Any]:
    """Anonymise un texte en utilisant les patterns regex spécialisés.

    Returns:
        {
            "anonymized_text": "texte avec tokens",
            "entities": [...],
            "confidence": "high",
            "count": N,
            "method": "dictionary",
            "registry": EntityRegistry
        }
    """
    if not text:
        return {
            "anonymized_text": "",
            "entities": [],
            "confidence": "high",
            "count": 0,
            "method": "dictionary",
            "registry": EntityRegistry(),
        }

    registry = EntityRegistry()
    
    # 1. Détection des entités via patterns regex (ancien dictionnaire + nouveaux patterns)
    detections = detect_entities(text, profile=profile)
    
    # 2. Application des pseudonymes stables
    # En mode dictionnaire, on applique toujours les pseudonymes stables
    detections = apply_business_pseudonyms(text, detections, registry)
    
    # 3. Remplacement dans le texte
    result = text
    # On trie à l'envers pour ne pas décaler les index
    for match in sorted(detections, key=lambda m: m["start_index"], reverse=True):
        result = (
            result[: match["start_index"]]
            + match["replacement"]
            + result[match["end_index"] :]
        )

    # 4. Nettoyage final
    result = clean_ocr_artifacts(result)

    logger.info(
        "dictionary_anonymization_complete",
        detections=len(detections),
    )

    return {
        "anonymized_text": result,
        "entities": detections,
        "confidence": "high",
        "count": len(detections),
        "method": "dictionary",
        "registry": registry,
    }


async def anonymize_document_dictionary(
    text: str,
) -> tuple[str, list[dict[str, Any]], EntityRegistry]:
    """Interface compatible avec le pipeline de traitement.

    Returns:
        (anonymized_text, detections_list, entity_registry)
    """
    result = anonymize_with_dictionary(text)
    return result["anonymized_text"], result["entities"], result["registry"]
