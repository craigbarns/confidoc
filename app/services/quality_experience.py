"""Couche « expérience » : rend la qualité d'extraction lisible et actionnable (FR)."""

from __future__ import annotations

from typing import Any

# Drapeaux connus (structured + dataset-summary regex) → libellés courts + conseils.
_FLAG_CATALOG: dict[str, tuple[str, str, str]] = {
    # severity: info | warning | risk
    "emails_found": ("warning", "Email potentiellement visible", "Contrôler l'anonymisation sur cette zone."),
    "iban_found": ("warning", "IBAN potentiellement visible", "Vérifier le masquage bancaire."),
    "siret_found": ("warning", "SIRET détecté", "Vérifier les identifiants d'entreprise."),
    "siren_found": ("warning", "SIREN détecté", "Vérifier les identifiants d'entreprise."),
    "low_field_coverage": ("warning", "Couverture des champs faible", "Document atypique ou OCR difficile — revue conseillée."),
    "manual_review_recommended": ("info", "Revue manuelle recommandée", "Valider les montants sur le PDF source."),
    "critical_fields_missing": ("risk", "Champs critiques manquants", "Forcer le type de document ou améliorer le PDF."),
    "bilan_balance_mismatch": ("warning", "Bilan : actif ≠ passif (hors tolérance)", "Comparer totaux avec la plaquette / liasse source."),
    "bilan_balance_minor_gap": ("info", "Bilan : léger écart actif/passif", "Souvent des arrondis ou synthèse — contrôle rapide."),
    "result_chain_inconsistent": ("risk", "Chaîne REX / RC / RN incohérente", "Vérifier les trois résultats sur le document."),
    "result_chain_minor_gap": ("info", "Écart modéré sur la chaîne des résultats", "Contrôler postes financiers / exceptionnels."),
    "annex_consistency_failed": ("warning", "Annexes 2072 : incohérence", "Vérifier annexes 1/2 vs tableaux extraits."),
    "numeric_consistency_low": ("warning", "Cohérence numérique 2072 limitée", "Relire revenus, charges et résultat net."),
    "aggregate_consistency_low": ("warning", "Totaux agrégés vs lignes : écart", "Contrôler sommes des tableaux vs champs."),
}


def _segmentation_note_fr(provenance: dict[str, Any]) -> str | None:
    seg = provenance.get("text_segmentation")
    if not isinstance(seg, dict) or not seg:
        return None
    strat = seg.get("strategy")
    if strat != "semantic_window":
        return None
    fb = seg.get("fallback_to_full_text")
    full_c = seg.get("full_chars")
    seg_c = seg.get("segment_chars")
    if fb is True:
        return (
            "Document long : une fenêtre thématique a été testée ; "
            "l'extraction finale utilise le texte intégral (meilleure qualité)."
        )
    if isinstance(full_c, int) and isinstance(seg_c, int) and full_c > 0:
        return (
            f"Document long : extraction focalisée sur une fenêtre d'environ "
            f"{seg_c:,} caractères ({seg_c * 100 // full_c}% du texte)."
        )
    return "Document long : extraction focalisée sur une fenêtre thématique."


# Champs numériques / seuils exposés par _quality_bilan / _quality_compte_resultat (traçabilité).
_QUALITY_TRACE_KEYS: tuple[str, ...] = (
    "bilan_balance_gap",
    "bilan_balance_tolerance_used",
    "cr_chain_delta_rex_rc",
    "cr_chain_delta_rc_rn",
    "cr_chain_tol_relaxed_rex_rc",
    "cr_chain_tol_relaxed_rc_rn",
)


def _traceability_from_quality(quality: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in _QUALITY_TRACE_KEYS:
        v = quality.get(k)
        if v is not None:
            out[k] = v
    return out


def build_quality_experience(
    *,
    doc_type: str,
    quality: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Résumé structuré pour UI, exports et intégrations."""
    needs_review = bool(quality.get("needs_review", True))
    ready = bool(quality.get("ready_for_ai", False))
    flags = list(quality.get("quality_flags") or [])
    critical = list(quality.get("critical_missing_fields") or [])
    coverage = quality.get("coverage_ratio")

    if critical:
        level = "block"
        headline = (
            f"{len(critical)} champ(s) critique(s) manquant(s) pour « {doc_type} » — "
            "revue ou ressaisie nécessaire avant usage automatisé."
        )
    elif not needs_review and ready:
        level = "ok"
        headline = "Extraction alignée avec les garde-fous : prête pour la suite (sous réserve métier)."
    elif not needs_review:
        level = "ok"
        headline = "Aucun point bloquant détecté sur les règles actuelles."
    else:
        level = "warning"
        if flags:
            headline = f"{len(flags)} point(s) qualité à traiter — revue recommandée."
        else:
            headline = "Revue manuelle recommandée (document ou profil atypique)."

    items: list[dict[str, Any]] = []
    for code in flags:
        meta = _FLAG_CATALOG.get(code)
        if meta:
            sev, label, hint = meta
        else:
            sev, label, hint = ("warning", code.replace("_", " "), "Analyser ce point dans le détail qualité.")
        items.append(
            {
                "code": code,
                "label_fr": label,
                "severity": sev,
                "hint_fr": hint,
            }
        )

    seg_note = _segmentation_note_fr(provenance)

    return {
        "level": level,
        "headline_fr": headline,
        "items": items,
        "segmentation_note_fr": seg_note,
        "traceability": _traceability_from_quality(quality),
        "metrics": {
            "doc_type": doc_type,
            "coverage_ratio": coverage,
            "needs_review": needs_review,
            "ready_for_ai": ready,
            "critical_missing_count": len(critical),
        },
    }
