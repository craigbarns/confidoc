"""ConfiDoc — Service d'Audit Interne et Détection d'Anomalies.

Implémente la vision "Audit Interne" de Deloitte (Case 6) :
- Conformité réglementaire
- Détection de fraudes potentielles
- Analyse proactive des anomalies
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

def run_internal_audit(extracted_data: dict[str, Any], text_context: str) -> dict[str, Any]:
    """Exécute une batterie de tests d'audit sur les données extraites."""
    findings = []
    risk_score = 0
    
    # 1. Analyse des montants ronds (Indicateur classique de fraude ou d'estimation)
    round_amounts = 0
    total_checked = 0
    for m in extracted_data.get("montants_cles", []):
        val = m.get("montant")
        if isinstance(val, (int, float)) and val != 0:
            total_checked += 1
            if val % 100 == 0: # Montant rond à la centaine
                round_amounts += 1
                
    if total_checked > 3 and (round_amounts / total_checked) > 0.5:
        findings.append({
            "type": "fraud_risk",
            "severity": "medium",
            "label": "Proportion élevée de montants ronds",
            "detail": f"{round_amounts}/{total_checked} montants sont des multiples de 100. À vérifier."
        })
        risk_score += 20

    # 2. Cohérence TVA (Heuristique simple)
    # Cherche si on a des montants qui pourraient être de la TVA non déclarée
    if "facture" in str(extracted_data.get("type_document", "")).lower():
        has_tva = any("tva" in str(m.get("libelle", "")).lower() for m in extracted_data.get("montants_cles", []))
        if not has_tva:
            findings.append({
                "type": "compliance",
                "severity": "high",
                "label": "Absence de TVA détectée",
                "detail": "Le document semble être une facture mais aucun montant de TVA n'a été identifié."
            })
            risk_score += 30

    # 3. Détection de mots-clés "sensibles" (Corruption / Blanchiment / Risque réputationnel)
    sensitive_keywords = [
        r"(?i)paradis fiscal", r"(?i)cash", r"(?i)esp[eè]ces", 
        r"(?i)commission occulte", r"(?i)r[eé]tro-commission",
        r"(?i)urgent", r"(?i)confidentiel sans trace"
    ]
    for kw in sensitive_keywords:
        if re.search(kw, text_context):
            findings.append({
                "type": "fraud_risk",
                "severity": "critical",
                "label": f"Terme sensible détecté : {kw.replace('(?i)', '')}",
                "detail": "La présence de ce terme dans le document nécessite une investigation immédiate."
            })
            risk_score += 50

    # 4. Vérification SIRET/SIREN (Conformité)
    siret = extracted_data.get("societe", {}).get("siret")
    if siret and not re.match(r"^\d{14}$", str(siret).replace(" ", "")):
        findings.append({
            "type": "compliance",
            "severity": "low",
            "label": "SIRET mal formé",
            "detail": f"Le SIRET extrait '{siret}' ne respecte pas le format standard de 14 chiffres."
        })
        risk_score += 10

    return {
        "audit_risk_score": min(100, risk_score),
        "audit_findings": findings,
        "requires_investigation": risk_score >= 40
    }
