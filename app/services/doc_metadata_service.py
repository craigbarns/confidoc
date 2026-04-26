"""ConfiDoc — Détection automatique des métadonnées de documents."""

from __future__ import annotations

import re

EXERCICE_PATTERNS = [
    r"exercice\s+clos?\s+le\s+\d{1,2}[/.-]\d{1,2}[/.-](\d{4})",
    r"bilan\s+au\s+\d{1,2}\s+\w+\s+(\d{4})",
    r"au\s+31[/. ]12[/. ](\d{4})",
    r"p[eé]riode\s+du\s+\d{1,2}[/.-]\d{1,2}[/.-]\d{4}\s+au\s+\d{1,2}[/.-]\d{1,2}[/.-](\d{4})",
    r"ann[eé]e\s+fiscale\s+(\d{4})",
    r"exercice\s+(\d{4})",
]

CATEGORY_RULES = [
    ("releve_bancaire", [
        "relevé de compte", "releve de compte", "solde", "iban",
        "débit", "crédit", "virement reçu", "prélèvement",
        "numéro de compte", "arrêté du compte",
    ]),
    ("liasse_fiscale", [
        "liasse fiscale", "2065", "2050", "2051", "2052", "2053",
        "2058", "résultat fiscal",
        "impôt sur les sociétés",
    ]),
    ("bilan", [
        "bilan", "actif", "passif", "capitaux propres",
        "immobilisations", "résultat de l'exercice",
        "compte de résultat",
    ]),
    ("grand_livre", [
        "grand livre", "écriture comptable",
        "balance", "lettrage",
    ]),
    ("contrat", [
        "contrat", "convention", "avenant", "bail",
        "clause", "article", "signataires",
    ]),
    ("facture", [
        "facture", "invoice", "total ttc", "total ht",
        "tva", "avoir", "bon de commande",
    ]),
]


def extract_exercice(text: str) -> str | None:
    sample = text[:8000].lower()
    for pattern in EXERCICE_PATTERNS:
        m = re.search(pattern, sample)
        if m:
            year = int(m.group(1))
            if 2010 <= year <= 2030:
                return str(year)
    return None


def suggest_client(text: str, detections: list[dict]) -> str | None:
    for det in detections[:20]:
        etype = str(det.get("entity_type") or "").upper()
        val = str(det.get("value_excerpt") or "").strip()
        if etype in ("COMPANY", "SOCIETE", "ORGANISATION") and len(val) >= 3:
            return val[:80]
    for det in detections[:20]:
        etype = str(det.get("entity_type") or "").upper()
        val = str(det.get("value_excerpt") or "").strip()
        if etype in ("PERSON", "PERSONNE", "PERSON_NAME") and len(val) >= 3:
            return val[:80]
    return None


def classify_doc_category(text: str, filename: str = "") -> str:
    source = f"{filename}\n{text[:8000]}".lower()
    best: str | None = None
    best_score = 0
    for category, hints in CATEGORY_RULES:
        score = sum(1 for h in hints if h in source)
        if score > best_score:
            best_score = score
            best = category
    if best_score >= 2:
        return best  # type: ignore[return-value]
    # Single strong hint (first 3 hints per category)
    for category, hints in CATEGORY_RULES:
        if any(h in source for h in hints[:3]):
            return category
    return "autre"


def build_metadata_suggestions(
    text: str,
    filename: str,
    detections: list[dict],
) -> dict:
    return {
        "doc_category": classify_doc_category(text, filename),
        "exercice": extract_exercice(text),
        "client_suggestion": suggest_client(text, detections),
    }
