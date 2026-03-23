"""Seuils centralisés extraction/qualité pour datasets structurés."""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings

DEFAULT_THRESHOLDS: dict[str, float] = {
    # Montants
    "amount_min_default": 100.0,
    "amount_min_low": 50.0,
    "amount_abs_hard_cap": 5_000_000.0,
    # Garde-fous composants bilan
    "component_abs_hard_cap": 10_000_000.0,
    "component_vs_passif_ratio_cap": 1.2,
    # Qualité (ready/full/core)
    "quality_ready_coverage_min": 0.8,
    "quality_ready_consistency_min": 0.85,
    "quality_core_numeric_min": 0.85,
    "quality_core_aggregate_min": 0.85,
    # Tolérances agrégées
    "aggregate_rel_tolerance": 0.03,
    "aggregate_abs_tolerance_min": 2.0,
}


@lru_cache
def get_extraction_thresholds() -> dict[str, float]:
    """Return effective thresholds merged with optional env overrides."""
    settings = get_settings()
    out = dict(DEFAULT_THRESHOLDS)
    overrides = {
        "amount_min_default": settings.EXTRACT_AMOUNT_MIN_DEFAULT,
        "amount_min_low": settings.EXTRACT_AMOUNT_MIN_LOW,
        "amount_abs_hard_cap": settings.EXTRACT_AMOUNT_ABS_HARD_CAP,
        "component_abs_hard_cap": settings.EXTRACT_COMPONENT_ABS_HARD_CAP,
        "component_vs_passif_ratio_cap": settings.EXTRACT_COMPONENT_VS_PASSIF_RATIO_CAP,
        "quality_ready_coverage_min": settings.EXTRACT_QUALITY_READY_COVERAGE_MIN,
        "quality_ready_consistency_min": settings.EXTRACT_QUALITY_READY_CONSISTENCY_MIN,
        "quality_core_numeric_min": settings.EXTRACT_QUALITY_CORE_NUMERIC_MIN,
        "quality_core_aggregate_min": settings.EXTRACT_QUALITY_CORE_AGGREGATE_MIN,
        "aggregate_rel_tolerance": settings.EXTRACT_AGGREGATE_REL_TOLERANCE,
        "aggregate_abs_tolerance_min": settings.EXTRACT_AGGREGATE_ABS_TOLERANCE_MIN,
    }
    for key, value in overrides.items():
        if isinstance(value, (int, float)):
            out[key] = float(value)
    return out


THRESHOLDS: dict[str, float] = get_extraction_thresholds()

