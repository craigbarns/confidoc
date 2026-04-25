"""ConfiDoc — Service de validation des règles métier comptables.

Vérifie la cohérence arithmétique des extractions (Bilan, CR, 2072).
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


def validate_accounting_coherence(extraction: dict[str, Any]) -> dict[str, Any]:
    """Valide la cohérence des données extraites selon le type de document."""
    doc_type = extraction.get("type_document")
    totaux = extraction.get("totaux", {})
    
    flags = []
    
    if doc_type == "bilan":
        ta = totaux.get("total_actif", {}).get("montant")
        tp = totaux.get("total_passif", {}).get("montant")
        
        if ta is not None and tp is not None:
            gap = abs(ta - tp)
            if gap > 1.0: # Tolérance 1€ pour arrondis OCR
                flags.append(f"bilan_mismatch: écart de {gap:.2f}€")
            else:
                flags.append("bilan_balanced")
        else:
            flags.append("bilan_totals_missing")
            
    elif doc_type == "compte_resultat":
        ca = totaux.get("chiffre_affaires", {}).get("montant")
        rn = totaux.get("resultat_net", {}).get("montant")
        
        # On pourrait ajouter ici des vérifications sur la chaîne REX -> RC -> RN
        # si on avait ces champs dans les totaux.
        if ca is None:
            flags.append("cr_ca_missing")
        if rn is None:
            flags.append("cr_rn_missing")
            
    # Ajout d'un score de fiabilité métier (0-100)
    score = 100
    if "bilan_mismatch" in str(flags):
        score -= 40
    if "missing" in str(flags):
        score -= 20
        
    return {
        "coherence_score": max(0, score),
        "validation_flags": flags,
        "is_valid": "mismatch" not in str(flags) and "missing" not in str(flags)
    }
