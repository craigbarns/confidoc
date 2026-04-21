"""ConfiDoc — Service de Mapping PCG (Plan Comptable Général).

Utilise l'IA pour suggérer des codes comptables français à partir des libellés extraits.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Liste simplifiée des racines PCG communes pour guider l'IA
PCG_ROOTS = {
    "601": "Achats de matières premières",
    "606": "Achats non stockés de matières et fournitures (énergie, fournitures bureau)",
    "611": "Sous-traitance générale",
    "613": "Locations",
    "615": "Entretien et réparations",
    "616": "Primes d'assurances",
    "621": "Personnel extérieur à l'entreprise",
    "622": "Rémunérations d'intermédiaires et honoraires",
    "623": "Publicité, publications, relations publiques",
    "625": "Déplacements, missions et réceptions",
    "626": "Frais postaux et de télécommunications",
    "627": "Services bancaires et assimilés",
    "641": "Rémunérations du personnel",
    "701": "Ventes de produits finis",
    "706": "Prestations de services",
    "707": "Ventes de marchandises",
    "401": "Fournisseurs",
    "411": "Clients",
    "512": "Banque",
}

def suggest_pcg_code(libelle: str, nature: str) -> dict[str, Any]:
    """Suggère un code PCG et un label normalisé pour un libellé donné.
    Note: En production, cela pourrait appeler un LLM ou une recherche vectorielle.
    """
    lib = libelle.lower()
    
    # Heuristiques simples de base (le LLM fera le reste dans le prompt d'extraction)
    if "loyer" in lib or "location" in lib:
        return {"code": "613000", "label": "Locations"}
    if "honoraires" in lib or "avocat" in lib or "comptable" in lib:
        return {"code": "622600", "label": "Honoraires"}
    if "edf" in lib or "electricite" in lib or "energie" in lib:
        return {"code": "606100", "label": "Fournitures non stockables (Énergie)"}
    if "orange" in lib or "sfr" in lib or "telephone" in lib or "internet" in lib:
        return {"code": "626000", "label": "Frais postaux et de télécommunications"}
    if "salaire" in lib or "remuneration" in lib:
        return {"code": "641000", "label": "Rémunérations du personnel"}
    
    # Fallback par nature
    if nature == "charge":
        return {"code": "606300", "label": "Fournitures d'entretien et de petit équipement"}
    if nature == "produit":
        return {"code": "706000", "label": "Prestations de services"}
        
    return {"code": "471000", "label": "Compte d'attente (à classer)"}
