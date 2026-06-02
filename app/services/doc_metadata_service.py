"""ConfiDoc — Détection automatique des métadonnées de documents."""

from __future__ import annotations

import re

COMPANY_ENTITY_TYPES = {"SOCIETE", "ORGANISATION", "LEGAL_DENOMINATION", "COMPANY"}
PERSON_ENTITY_TYPES = {"PERSON", "PERSONNE", "ASSOCIE", "SIGNATAIRE"}
GENERIC_CLIENT_VALUES = {"confidoc", "page", "exercice", "bilan", "client"}

EXERCICE_PATTERNS = [
    r"exercice\s+clos?\s+le\s+\d{1,2}[/.-]\d{1,2}[/.-](\d{4})",
    r"bilan\s+au\s+\d{1,2}\s+\w+\s+(\d{4})",
    r"au\s+31[/. ]12[/. ](\d{4})",
    r"p[eé]riode\s+du\s+\d{1,2}[/.-]\d{1,2}[/.-]\d{4}\s+au\s+\d{1,2}[/.-]\d{1,2}[/.-](\d{4})",
    r"ann[eé]e\s+fiscale\s+(\d{4})",
    r"exercice\s+(\d{4})",
]

CATEGORY_RULES = [
    (
        "releve_bancaire",
        [
            "relevé de compte",
            "releve de compte",
            "solde",
            "iban",
            "débit",
            "crédit",
            "virement reçu",
            "prélèvement",
            "numéro de compte",
            "arrêté du compte",
        ],
    ),
    (
        "liasse_fiscale",
        [
            "liasse fiscale",
            "2065",
            "2050",
            "2051",
            "2052",
            "2053",
            "2058",
            "résultat fiscal",
            "impôt sur les sociétés",
        ],
    ),
    (
        "bilan",
        [
            "bilan",
            "actif",
            "passif",
            "capitaux propres",
            "immobilisations",
            "résultat de l'exercice",
            "compte de résultat",
        ],
    ),
    (
        "grand_livre",
        [
            "grand livre",
            "écriture comptable",
            "balance",
            "lettrage",
        ],
    ),
    (
        "contrat",
        [
            "contrat",
            "convention",
            "avenant",
            "bail",
            "clause",
            "article",
            "signataires",
            "tribunal",
            "juridiction",
            "assignation",
            "jugement",
        ],
    ),
    (
        "facture",
        [
            "facture",
            "invoice",
            "total ttc",
            "total ht",
            "tva",
            "avoir",
            "bon de commande",
        ],
    ),
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


def _detection_value(det: dict) -> str:
    return str(det.get("value_excerpt") or "").strip()


def _is_usable_client_value(value: str) -> bool:
    return len(value) >= 3 and value.lower() not in GENERIC_CLIENT_VALUES


def suggest_client(
    text: str,
    detections: list[dict],
    known_clients: list[str] | None = None,
) -> str | None:
    """Suggère un client en croisant les détections avec les clients connus de la DB."""
    sample = text[:5000]

    # 1. Priorité absolue : match exact avec un client existant dans le texte
    if known_clients:
        for client_name in known_clients:
            if len(client_name) < 4:
                continue
            # Recherche insensible à la casse avec frontières de mots
            pattern = rf"(?i)\b{re.escape(client_name)}\b"
            if re.search(pattern, sample):
                return client_name

    # 2. Heuristique : Première entité de type SOCIETE trouvée
    for det in detections[:15]:
        etype = str(det.get("entity_type") or "").upper()
        val = _detection_value(det)
        if etype in COMPANY_ENTITY_TYPES and _is_usable_client_value(val):
            return val[:80]

    # 3. Repli : Bloc d'identité
    for det in detections[:10]:
        if det.get("entity_type") == "invoice_identity_block":
            val = _detection_value(det).split("\n")[0].strip()
            if _is_usable_client_value(val):
                return val[:80]

    # 4. Dernier repli : personne détectée, utile pour les dossiers de particuliers.
    for det in detections[:15]:
        etype = str(det.get("entity_type") or "").upper()
        val = _detection_value(det)
        if etype in PERSON_ENTITY_TYPES and _is_usable_client_value(val):
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
    known_clients: list[str] | None = None,
) -> dict:
    return {
        "doc_category": classify_doc_category(text, filename),
        "exercice": extract_exercice(text),
        "client_suggestion": suggest_client(text, detections, known_clients=known_clients),
    }
