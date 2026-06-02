"""ConfiDoc Backend — Document comparison service (N vs N-1).

Compares two versions of accounting documents (e.g. bilan N vs bilan N-1)
to detect significant variations, missing fields, and coherence anomalies.

This is a killer feature for accountants: "Did my client's balance sheet
change significantly year-over-year?"
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.services.llm_extraction_service import extract_with_llm

logger = get_logger(__name__)


async def compare_documents(
    db: AsyncSession,
    current_text: str,
    previous_text: str,
    doc_type: str = "bilan",
) -> dict[str, Any]:
    """Compare two anonymized document texts and return a structured diff.

    Args:
        current_text: Text of the current period document (anonymized)
        previous_text: Text of the previous period document (anonymized)
        doc_type: "bilan", "compte_resultat", "fiscal_2072", etc.

    Returns:
        {
            "summary": str,
            "variations": [
                {
                    "field": str,
                    "current_value": str | float | None,
                    "previous_value": str | float | None,
                    "variation_pct": float | None,
                    "variation_abs": float | None,
                    "severity": "info" | "warning" | "critical",
                    "insight": str,
                }
            ],
            "coherence_flags": [str],
            "global_trend": str,
        }
    """
    # 1) Extract structured data from both documents
    current_data = await extract_with_llm(current_text, doc_type=doc_type)
    previous_data = await extract_with_llm(previous_text, doc_type=doc_type)

    current_fields = _extract_fields_for_comparison(current_data)
    previous_fields = _extract_fields_for_comparison(previous_data)

    # 2) Find all keys present in either document
    all_keys = set(current_fields.keys()) | set(previous_fields.keys())

    variations: list[dict[str, Any]] = []
    coherence_flags: list[str] = []

    for key in sorted(all_keys):
        curr = _to_float(current_fields.get(key))
        prev = _to_float(previous_fields.get(key))

        if curr is None and prev is None:
            continue

        severity = "info"
        insight = ""
        var_pct: float | None = None
        var_abs: float | None = None

        if curr is not None and prev is not None:
            var_abs = round(curr - prev, 2)
            var_pct = round((curr - prev) / abs(prev) * 100, 2) if prev != 0 else None

            # Severity heuristics
            if var_pct is not None:
                if abs(var_pct) > 50:
                    severity = "critical"
                    insight = f"Variation majeure ({var_pct:+.1f}%) — nécessite explication."
                elif abs(var_pct) > 20:
                    severity = "warning"
                    insight = f"Variation significative ({var_pct:+.1f}%) — à vérifier."
                else:
                    insight = f"Variation modérée ({var_pct:+.1f}%)."
            else:
                insight = "Nouvelle valeur (précédente à zéro ou absente)."
        elif curr is None and prev is not None:
            severity = "warning"
            insight = f"Champ absent du document N mais présent en N-1 ({prev})."
            var_abs = -prev
        elif curr is not None and prev is None:
            insight = f"Nouveau champ en N ({curr})."
            var_abs = curr

        variations.append(
            {
                "field": key,
                "current_value": curr,
                "previous_value": prev,
                "variation_pct": var_pct,
                "variation_abs": var_abs,
                "severity": severity,
                "insight": insight,
            }
        )

    # 3) Global coherence checks
    # Bilan-specific: Actif must equal Passif in both periods
    if doc_type == "bilan":
        actif_n = _to_float(current_fields.get("total_actif"))
        passif_n = _to_float(current_fields.get("total_passif"))
        actif_n1 = _to_float(previous_fields.get("total_actif"))
        passif_n1 = _to_float(previous_fields.get("total_passif"))

        if actif_n is not None and passif_n is not None and abs(actif_n - passif_n) > 1:
            coherence_flags.append(
                f"Bilan N déséquilibré : Actif {actif_n:,.0f} ≠ Passif {passif_n:,.0f}"
            )
        if actif_n1 is not None and passif_n1 is not None and abs(actif_n1 - passif_n1) > 1:
            coherence_flags.append(
                f"Bilan N-1 déséquilibré : Actif {actif_n1:,.0f} ≠ Passif {passif_n1:,.0f}"
            )

    # General financial trends coherence checks
    rn_n = _to_float(
        current_fields.get("resultat_net")
        or current_fields.get("resultat_de_l_exercice")
        or current_fields.get("resultat_exercice")
        or current_fields.get("poste_resultat_net")
    )
    rn_n1 = _to_float(
        previous_fields.get("resultat_net")
        or previous_fields.get("resultat_de_l_exercice")
        or previous_fields.get("resultat_exercice")
        or previous_fields.get("poste_resultat_net")
    )
    if rn_n is not None and rn_n < 0 and rn_n1 is not None and rn_n1 > 0:
        coherence_flags.append(
            f"Bilan déficitaire : L'entreprise enregistre un résultat net négatif en N ({rn_n:,.0f} €) alors qu'elle était bénéficiaire en N-1 ({rn_n1:,.0f} €)."
        )

    ca_n = _to_float(
        current_fields.get("chiffre_d_affaires")
        or current_fields.get("chiffre_affaires")
        or current_fields.get("poste_chiffre_d_affaires")
    )
    ca_n1 = _to_float(
        previous_fields.get("chiffre_d_affaires")
        or previous_fields.get("chiffre_affaires")
        or previous_fields.get("poste_chiffre_d_affaires")
    )
    if ca_n is not None and ca_n1 is not None and ca_n1 > 0:
        ca_var = (ca_n - ca_n1) / ca_n1 * 100
        if ca_var < -30:
            coherence_flags.append(
                f"Baisse critique de l'activité : Le chiffre d'affaires a diminué de {abs(ca_var):.1f}% sur l'exercice (N: {ca_n:,.0f} € vs N-1: {ca_n1:,.0f} €)."
            )

    # 4) Summary generation
    critical_count = sum(1 for v in variations if v["severity"] == "critical")
    warning_count = sum(1 for v in variations if v["severity"] == "warning")

    if critical_count > 0:
        global_trend = (
            f"{critical_count} variation(s) majeure(s) détectée(s). Revue approfondie recommandée."
        )
    elif warning_count > 0:
        global_trend = f"{warning_count} point(s) d'attention. Vérification conseillée."
    else:
        global_trend = "Stabilité globale. Aucune variation significative détectée."

    # Sort by severity then by absolute variation
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    variations.sort(
        key=lambda v: (
            severity_order.get(v["severity"], 3),
            -(abs(v["variation_abs"]) if v["variation_abs"] else 0),
        )
    )

    logger.info(
        "document_comparison_complete",
        doc_type=doc_type,
        variations=len(variations),
        critical=critical_count,
        warnings=warning_count,
    )

    return {
        "summary": global_trend,
        "variations": variations,
        "coherence_flags": coherence_flags,
        "global_trend": global_trend,
        "periods": {
            "current": _extract_period_label(current_data, default="N"),
            "previous": _extract_period_label(previous_data, default="N-1"),
        },
    }


def _extract_fields_for_comparison(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize extracted payload to a flat {field -> value} structure."""
    raw_fields = data.get("fields")
    if isinstance(raw_fields, dict):
        return raw_fields

    fields: dict[str, Any] = {}
    totaux = data.get("totaux")
    if isinstance(totaux, dict):
        for key, value in totaux.items():
            if isinstance(value, dict):
                fields[key] = value.get("montant")
            else:
                fields[key] = value

    montants = data.get("montants_cles")
    if isinstance(montants, list):
        for item in montants:
            if not isinstance(item, dict):
                continue
            label = str(item.get("libelle") or "").strip().lower()
            amount = item.get("montant")
            if not label or amount is None:
                continue
            slug = re.sub(r"[^a-z0-9]+", "_", label).strip("_")
            if not slug:
                continue
            key = f"poste_{slug[:80]}"
            fields.setdefault(key, amount)

    return fields


def _extract_period_label(data: dict[str, Any], default: str) -> str:
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        exercice = metadata.get("exercice")
        if isinstance(exercice, str) and exercice.strip():
            return exercice

    exercice_data = data.get("exercice")
    if isinstance(exercice_data, dict):
        for key in ("date_fin", "date_arrete", "date_debut"):
            value = exercice_data.get(key)
            if isinstance(value, str) and value.strip():
                return value

    return default


def _to_float(value: Any) -> float | None:
    """Safely convert an extracted value to float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    # Handle French formatted numbers: "1 234,56" → 1234.56
    if isinstance(value, str):
        cleaned = value.replace(" ", "").replace("\u202f", "").replace("\xa0", "")
        cleaned = cleaned.replace(",", ".")
        # Remove any currency symbols or trailing text
        cleaned = "".join(c for c in cleaned if c.isdigit() or c in "-.").strip()
        if cleaned:
            try:
                return float(cleaned)
            except ValueError:
                pass
    return None
