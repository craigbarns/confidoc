"""ConfiDoc - Service de scoring du risque de reidentification.

Conforme aux recommandations CNIL :
- L'anonymisation doit rendre impossible l'identification, pas seulement la masquer.
- Le risque se mesure par la combinaison de quasi-identifiants residuels.

Score: 0.0 (risque nul) a 1.0 (reidentification quasi-certaine).
Seuils:
  <= 0.20  -> anonymisation forte (RGPD-safe pour export/IA)
  0.21-0.50 -> pseudonymisation acceptable (usage interne)
  > 0.50 -> risque eleve, revue humaine obligatoire
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RiskSignal:
    category: str
    description: str
    weight: float
    occurrences: int = 1
    examples: list[str] = field(default_factory=list)


@dataclass
class ReidentificationReport:
    score: float
    level: str
    signals: list[RiskSignal]
    recommendation: str
    quasi_identifiers_count: int
    unique_combinations_estimate: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 3),
            "level": self.level,
            "recommendation": self.recommendation,
            "quasi_identifiers_count": self.quasi_identifiers_count,
            "unique_combinations_estimate": self.unique_combinations_estimate,
            "signals": [
                {
                    "category": s.category,
                    "description": s.description,
                    "weight": round(s.weight, 3),
                    "occurrences": s.occurrences,
                    "examples": s.examples[:3],
                }
                for s in self.signals
            ],
        }


_RESIDUAL_PATTERNS: list[tuple[str, str, re.Pattern[str], float]] = [
    (
        "address_residual",
        "Adresse ou fragment d'adresse non masque",
        re.compile(
            r"\b\d{1,4}\s*[,.]?\s*(?:rue|avenue|bd|boulevard|traverse|chemin|impasse|route|place)\s+[^\n]{5,}",
            re.IGNORECASE,
        ),
        0.15,
    ),
    (
        "city_residual",
        "Ville en clair",
        re.compile(
            r"\b(?:Marseille|Paris|Lyon|Toulouse|Bordeaux|Nice|Nantes|Montpellier|Strasbourg|Lille"
            r"|Aix-en-Provence|Saint-[A-Z][a-z]+)\b",
            re.IGNORECASE,
        ),
        0.08,
    ),
    (
        "postal_code",
        "Code postal visible",
        re.compile(r"\b(?:13\d{3}|75\d{3}|69\d{3}|31\d{3}|33\d{3})\b"),
        0.06,
    ),
    (
        "person_name_near_token",
        "Prenom/nom residuel avant un token personne",
        re.compile(r"(?i)\b[A-Za-z][a-z'-]{2,15}[ \t]+\[(?:PERSONNE|ASSOCIE|PRENOM)_\d+\]"),
        0.20,
    ),
    (
        "person_name_near_token_after",
        "Prenom/nom residuel apres un token personne",
        re.compile(r"(?i)\[(?:PERSONNE|ASSOCIE|PRENOM)_\d+\][ \t]+[A-Za-z][a-z'-]{2,15}\b"),
        0.20,
    ),
    (
        "birth_date_visible",
        "Date de naissance visible",
        re.compile(r"(?i)(?:ne|nee|naissance)\s*[:\-]?\s*\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}"),
        0.18,
    ),
    (
        "department_visible",
        "Departement de naissance/residence visible",
        re.compile(r"(?i)(?:departement|dept)\s*[:\-]?\s*\d{1,3}"),
        0.05,
    ),
    (
        "siret_partial",
        "SIRET/SIREN partiel visible",
        re.compile(r"\b\d{9,14}\b"),
        0.12,
    ),
    (
        "iban_visible",
        "IBAN visible",
        re.compile(r"\b[A-Z]{2}\d{2}\s?[A-Z0-9]{4}\s?(?:[A-Z0-9]{4}\s?){2,7}"),
        0.15,
    ),
    (
        "email_visible",
        "Email visible",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        0.20,
    ),
    (
        "phone_visible",
        "Telephone visible",
        re.compile(r"\b(?:\+33|0)\s?[1-9](?:[\s.\-]?\d{2}){4}\b"),
        0.10,
    ),
    (
        "company_name_residual",
        "Raison sociale potentiellement visible",
        re.compile(r"\b(?:SAS|SARL|SCI|EURL|SELARL|SCP|SA)\s+[A-Z][A-Za-z\s\-]{3,30}\b"),
        0.12,
    ),
    (
        "subsidiary_cluster",
        "Cluster de filiales identifiable",
        re.compile(r"\[SOCIETE_LIEE_\d+\]", re.IGNORECASE),
        0.03,
    ),
    (
        "ownership_pct",
        "Pourcentage de detention identifiable",
        re.compile(
            r"\b(?:100|[1-9]\d?)\s*%\s*(?:des\s+parts|detention|participation|associe)",
            re.IGNORECASE,
        ),
        0.07,
    ),
    (
        "loan_ref_residual",
        "Reference d'emprunt visible",
        re.compile(r"(?i)(?:emprunt|pret|credit)\s*(?:n[o])?\s*[:\-]?\s*\d{6,15}"),
        0.08,
    ),
    (
        "brand_model",
        "Marque/modele identifiable",
        re.compile(r"\b(?:Tesla|Mercedes|BMW|Audi|Porsche|Tiime|Sage|Cegid|EBP)\b", re.IGNORECASE),
        0.04,
    ),
]

_COMBINATION_THRESHOLDS = [
    (2, 0.10),
    (3, 0.15),
    (4, 0.20),
    (5, 0.25),
]


def analyze_reidentification_risk(
    anonymized_text: str,
    entity_summary: dict[str, int] | None = None,
) -> ReidentificationReport:
    """Analyze re-identification risk of an anonymized document."""
    if not anonymized_text or not anonymized_text.strip():
        return ReidentificationReport(
            score=0.0, level="low", signals=[],
            recommendation="Document vide.",
            quasi_identifiers_count=0, unique_combinations_estimate=0,
        )

    signals: list[RiskSignal] = []
    categories_found: set[str] = set()

    for cat, desc, pattern, weight in _RESIDUAL_PATTERNS:
        matches = list(pattern.finditer(anonymized_text))
        if not matches:
            continue

        real_matches = []
        for m in matches:
            val = m.group(0)
            if val.startswith("[") and val.endswith("]"):
                continue
            pre = anonymized_text[max(0, m.start() - 1) : m.start()]
            post = anonymized_text[m.end() : min(len(anonymized_text), m.end() + 1)]
            if pre == "[" or post == "]":
                continue
            real_matches.append(val)

        if not real_matches:
            continue

        categories_found.add(cat)
        signals.append(RiskSignal(
            category=cat, description=desc, weight=weight,
            occurrences=len(real_matches),
            examples=[v[:80] for v in real_matches[:3]],
        ))

    base_score = min(sum(s.weight * min(s.occurrences, 5) for s in signals), 0.75)

    n_categories = len(categories_found)
    combo_bonus = 0.0
    for threshold, bonus in _COMBINATION_THRESHOLDS:
        if n_categories >= threshold:
            combo_bonus = bonus

    total_score = min(base_score + combo_bonus, 1.0)
    unique_est = max(1, n_categories * sum(s.occurrences for s in signals))

    if total_score <= 0.20:
        level = "low"
        recommendation = (
            "Anonymisation forte. Document exploitable pour export, "
            "entrainement IA, ou partage externe."
        )
    elif total_score <= 0.50:
        level = "medium"
        recommendation = (
            "Pseudonymisation acceptable pour usage interne avec controle. "
            "Non recommande pour partage externe sans revue humaine."
        )
    elif total_score <= 0.75:
        level = "high"
        recommendation = (
            "Risque eleve de reidentification par recoupement. "
            "Revue humaine obligatoire avant tout partage."
        )
    else:
        level = "critical"
        recommendation = (
            "Anonymisation insuffisante. "
            "Ne pas partager en l'etat. Renforcer les regles."
        )

    return ReidentificationReport(
        score=total_score, level=level, signals=signals,
        recommendation=recommendation,
        quasi_identifiers_count=sum(s.occurrences for s in signals),
        unique_combinations_estimate=unique_est,
    )
