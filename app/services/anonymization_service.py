"""ConfiDoc Backend — Anonymization Service Facade.

This is a slim facade for backward compatibility.
Logic has been moved to:
- app.services.ocr.*
- app.services.extraction.*
- app.services.classification.*
- app.services.anonymization.*
"""

from typing import Any

from app.services.anonymization.cleanup import clean_ocr_artifacts
from app.services.anonymization.detector import detect_entities
from app.services.anonymization.pseudonymizer import apply_business_pseudonyms
from app.services.classification.service import classify_document_type
from app.services.entity_registry import EntityRegistry
from app.services.extraction.service import (
    extract_text_from_file,
    extract_text_from_file_with_meta,
)
from app.services.anonymization.detector import detect_entities as _detect_entities, is_false_positive as _is_false_positive
from app.services.ocr.engines import HAS_OCR, get_tesseract_config as _get_tesseract_config, ocr_image as _ocr_image
from app.services.ocr.preprocessing import preprocess_image_for_ocr as _preprocess_image_for_ocr, _deskew_image


def anonymize_text(
    text: str,
    profile: str = "moderate",
    document_type: str = "generic",
    registry: EntityRegistry | None = None,
) -> tuple[str, list[dict[str, Any]], EntityRegistry]:
    """Apply regex-based anonymization. (Facade)"""
    if not text or not text.strip():
        return text, [], registry or EntityRegistry()

    if registry is None:
        registry = EntityRegistry()

    detections = detect_entities(text, profile=profile, document_type=document_type)
    
    if profile == "dataset_accounting_pseudo":
        detections = apply_business_pseudonyms(text, detections, registry)
        
    anonymized = text
    # Apply replacements from end to start to preserve indices
    for match in sorted(detections, key=lambda m: m["start_index"], reverse=True):
        anonymized = (
            anonymized[: match["start_index"]]
            + match["replacement"]
            + anonymized[match["end_index"] :]
        )

    # Post-OCR cleanup
    anonymized = clean_ocr_artifacts(anonymized)

    return anonymized, detections, registry
