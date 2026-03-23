"""Seuils centralisés extraction/qualité pour datasets structurés."""

from __future__ import annotations

THRESHOLDS: dict[str, float] = {
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

