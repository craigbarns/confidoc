"""ConfiDoc Backend — Text extraction and anonymization service (v2)."""

import re
from typing import Any

import fitz


# ──────────────────────────────────────────────────────────────────────
# REGEX PATTERNS — applied in every profile
# ──────────────────────────────────────────────────────────────────────

PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # Identifiers
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    ("phone_fr", re.compile(r"\b(?:\+33|0)\s?[1-9](?:[\s.\-]?\d{2}){4}\b"), "[PHONE]"),
    ("phone_intl", re.compile(r"\+\d{1,3}[\s.\-]?\d(?:[\s.\-]?\d){6,14}\b"), "[PHONE]"),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[\s]?[A-Z0-9]{4}[\s]?(?:[A-Z0-9]{4}[\s]?){2,7}[A-Z0-9]{1,4}\b"), "[IBAN]"),
    ("iban_compact", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), "[IBAN]"),
    ("bic", re.compile(r"\b[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b"), "[BIC]"),
    ("siret", re.compile(r"\b\d{3}[\s.\-]?\d{3}[\s.\-]?\d{3}[\s.\-]?\d{5}\b"), "[SIRET]"),
    ("siren", re.compile(r"\b\d{3}[\s.\-]?\d{3}[\s.\-]?\d{3}\b"), "[SIREN]"),
    ("vat_fr", re.compile(r"\bFR\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{3}\b"), "[VAT]"),
    ("nss", re.compile(r"\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b"), "[NSS]"),

    # Addresses & locations
    (
        "address_line",
        re.compile(
            r"\b\d{1,4}[\s,]+(?:rue|avenue|av\.?|boulevard|bd\.?|chemin|impasse|allée|allee|"
            r"place|quai|route|passage|cours|square|résidence|residence|lotissement|hameau|"
            r"voie|faubourg|sentier)\s+[^\n,]{3,80}",
            re.IGNORECASE,
        ),
        "[ADDRESS]",
    ),
    ("postal_city", re.compile(r"\b\d{5}\s+[A-Za-zÀ-ÖØ-öø-ÿ''\- ]{2,40}\b"), "[CITY]"),

    # Persons (with title prefix)
    (
        "person_title",
        re.compile(
            r"\b(?:M\.|Mr\.|Monsieur|Mme|Madame|Mlle|Mademoiselle|Dr\.?|Me|Maître|Maitre)"
            r"\s+[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ''\-]+(?:\s+[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ''\-]+){0,2}\b"
        ),
        "[PERSON]",
    ),
]

# ──────────────────────────────────────────────────────────────────────
# STRICT-ONLY PATTERNS — applied in strict / dataset profiles
# ──────────────────────────────────────────────────────────────────────

STRICT_ONLY_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # Dates
    ("date_fr", re.compile(
        r"\b(?:0?[1-9]|[12]\d|3[01])[/\-.](?:0?[1-9]|1[0-2])[/\-.](?:19|20)\d{2}\b"
    ), "[DATE]"),
    ("date_iso", re.compile(r"\b(?:19|20)\d{2}[\-/](?:0?[1-9]|1[0-2])[\-/](?:0?[1-9]|[12]\d|3[01])\b"), "[DATE]"),
    ("date_text_fr", re.compile(
        r"\b(?:0?[1-9]|[12]\d|3[01])\s+(?:janvier|février|fevrier|mars|avril|mai|juin|"
        r"juillet|août|aout|septembre|octobre|novembre|décembre|decembre)\s+(?:19|20)\d{2}\b",
        re.IGNORECASE,
    ), "[DATE]"),

    # Monetary amounts
    ("amount_eur", re.compile(
        r"\b\d{1,3}(?:[\s\u00a0]?\d{3})*(?:[.,]\d{2})?\s?(?:€|EUR|euros?)\b", re.IGNORECASE
    ), "[AMOUNT]"),
    ("amount_plain", re.compile(r"\b\d{1,3}(?:[\s\u00a0]?\d{3})*,\d{2}\b"), "[AMOUNT]"),

    # Invoice references
    ("invoice_number", re.compile(
        r"(?i)\b(?:facture|invoice|fact|fa|fac|avoir|devis|bon\sde\scommande|bdc|bl)"
        r"\s*(?:n[°o]|#|num(?:é|e)ro)?\s*[:\-]?\s*[A-Z0-9\-/]{2,20}\b"
    ), "[INVOICE_REF]"),

    # Company names (legal forms)
    ("company_legal_name", re.compile(
        r"\b(?:SAS|SARL|EURL|SCI|SELARL|SCP|SA|SNC|EI|EIRL|SASU|SEL|GIE)"
        r"\s+[A-Z0-9][A-Z0-9\s\-'&]{1,60}\b"
    ), "[COMPANY]"),

    # Person names (two+ capitalized words)
    ("person_name", re.compile(
        r"\b[A-ZÀ-ÖØ-Ý][a-zà-öø-ÿ''\-]{2,}"
        r"\s+[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ''\-]{2,}\b"
    ), "[PERSON]"),

    # All-caps person names (e.g. "BARANES GREGORY")
    ("person_uppercase", re.compile(
        r"\b[A-ZÀ-ÖØ-Ý]{2,}(?:\s+[A-ZÀ-ÖØ-Ý]{2,}){1,3}\b"
    ), "[PERSON]"),

    # Country
    ("country", re.compile(r"\bFrance\b", re.IGNORECASE), "[COUNTRY]"),

    # Residence/address block patterns
    (
        "address_residence",
        re.compile(
            r"\b[A-Z]?\s?\d{1,4}\s+(?:LES\s+TERRASSES|TERRASSES|R[eé]sidence|RESIDENCE|Bâtiment|BATIMENT|B[âa]t\.?)"
            r"\s+(?:DE|DU|DES)?\s*[A-Za-zÀ-ÖØ-öø-ÿ''\- ]{3,50}\b",
            re.IGNORECASE,
        ),
        "[ADDRESS]",
    ),

    # Bank account code + label  (e.g. "51210000 QONTO")
    (
        "bank_account_code_label",
        re.compile(r"\b(512\d{5})\s+([A-Z0-9][A-Z0-9\s&/\\'\-]{1,40})\b", re.IGNORECASE),
        "[REDACTED]",
    ),
]

# ──────────────────────────────────────────────────────────────────────
# LABEL : VALUE  detection  (e.g. "Nom : Baranes")
# ──────────────────────────────────────────────────────────────────────

LABEL_VALUE_PATTERN = re.compile(
    r"(?im)^(?:nom|prénom|prenom|raison\s+sociale|société|societe|"
    r"client|destinataire|titulaire|bénéficiaire|beneficiaire|"
    r"adresse|email|e[\-]?mail|téléphone|telephone|tel|tél|mobile|portable|"
    r"iban|bic|siret|siren|tva(?:\s+intracom)?|"
    r"n[°o]\s*(?:client|compte|dossier|contrat))"
    r"\s*[:\-]\s*(.+)$"
)

INVOICE_HINTS = (
    "facture", "invoice", "tva", "total ttc", "total ht",
    "montant ht", "règlement", "reglement", "avoir", "devis",
)

# ──────────────────────────────────────────────────────────────────────
# FALSE-POSITIVE FILTER — words that look like entities but aren't
# ──────────────────────────────────────────────────────────────────────

FALSE_POSITIVE_WORDS: set[str] = {
    # Common uppercase header words in French accounting/invoices
    "FACTURE", "AVOIR", "DEVIS", "TOTAL", "MONTANT", "DESIGNATION",
    "DÉSIGNATION", "DESCRIPTION", "QUANTITÉ", "QUANTITE", "PRIX",
    "UNITAIRE", "HT", "TTC", "TVA", "SOLDE", "REPORT", "SOUS",
    "DATE", "NUMERO", "NUMÉRO", "RÉFÉRENCE", "REFERENCE", "PAGE",
    "OBJET", "NOTE", "COMPTE", "DÉBIT", "DEBIT", "CRÉDIT", "CREDIT",
    "PIÈCE", "PIECE", "LIBELLÉ", "LIBELLE", "JOURNAL", "EXERCICE",
    "PÉRIODE", "PERIODE", "BILAN", "ACTIF", "PASSIF", "CHARGES",
    "PRODUITS", "RÉSULTAT", "RESULTAT", "BRUT", "NET", "BALANCE",
    "GÉNÉRALE", "GENERALE", "ANALYTIQUE", "AUXILIAIRE", "GRAND",
    "LIVRE", "BORDEREAU", "RÉCAPITULATIF", "RECAPITULATIF",
    "BON", "COMMANDE", "LIVRAISON", "RETOUR",
    "MODE", "PAIEMENT", "CONDITIONS", "GÉNÉRALES", "GENERALES",
    "VENTE", "ACHAT", "CLIENT", "FOURNISSEUR",
}


# ══════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════


def classify_document_type(text: str, filename: str = "") -> str:
    """Heuristic document-type classification (v2)."""
    source = f"{filename}\n{text[:6000]}".lower()

    if any(hint in source for hint in INVOICE_HINTS):
        return "invoice"

    accounting_hints = ("grand livre", "balance", "journal", "écriture", "ecriture",
                        "compte de résultat", "bilan", "pcg", "plan comptable")
    if any(h in source for h in accounting_hints):
        return "accounting"

    legal_hints = ("contrat", "convention", "avenant", "clause", "article",
                   "tribunal", "juridiction", "assignation", "jugement")
    if any(h in source for h in legal_hints):
        return "legal"

    return "generic"


def extract_text_from_file(content: bytes, extension: str) -> str:
    """Extract text from uploaded bytes (PDF first, images later)."""
    extension = extension.lower().strip(".")

    if extension == "pdf":
        text_chunks: list[str] = []
        try:
            with fitz.open(stream=content, filetype="pdf") as doc:
                for page in doc:
                    text_chunks.append(page.get_text("text"))
        except Exception:
            # Corrupt or encrypted PDF — return empty
            return ""
        return "\n".join(text_chunks).strip()

    # Plain text fallback for non-PDF
    try:
        return content.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


def _is_false_positive(value: str) -> bool:
    """Check if an extracted value is a known false positive."""
    clean = value.strip().upper()
    # Exact match
    if clean in FALSE_POSITIVE_WORDS:
        return True
    # All words are false positives
    words = clean.split()
    if words and all(w in FALSE_POSITIVE_WORDS for w in words):
        return True
    # Too short
    if len(clean) < 3:
        return True
    return False


def _detect_entities(
    text: str, profile: str = "moderate", document_type: str = "generic"
) -> list[dict[str, Any]]:
    """Core entity detection engine."""
    matches: list[dict[str, Any]] = []

    # ── Base patterns (always applied) ──
    for entity_type, pattern, replacement in PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(0)
            if _is_false_positive(value):
                continue
            matches.append({
                "entity_type": entity_type,
                "start_index": match.start(),
                "end_index": match.end(),
                "value_excerpt": value,
                "replacement": replacement,
            })

    # ── Label:Value detection (always applied) ──
    for match in LABEL_VALUE_PATTERN.finditer(text):
        value = match.group(1).strip()
        if not value or _is_false_positive(value):
            continue
        matches.append({
            "entity_type": "labeled_sensitive_value",
            "start_index": match.start(1),
            "end_index": match.end(1),
            "value_excerpt": value,
            "replacement": "[REDACTED]",
        })

    # ── Strict-only patterns ──
    is_strict = profile in {"strict", "dataset_strict", "dataset_accounting"}
    if is_strict:
        for entity_type, pattern, replacement in STRICT_ONLY_PATTERNS:
            # Dataset accounting: keep amounts for business utility
            if profile == "dataset_accounting" and entity_type in {"amount_eur", "amount_plain"}:
                continue

            for match in pattern.finditer(text):
                value = match.group(0)
                if _is_false_positive(value):
                    continue

                rep = replacement
                # Bank account: keep code in accounting mode
                if entity_type == "bank_account_code_label":
                    code = match.group(1)
                    rep = f"{code} [REDACTED]" if profile == "dataset_accounting" else "[REDACTED]"

                matches.append({
                    "entity_type": entity_type,
                    "start_index": match.start(),
                    "end_index": match.end(),
                    "value_excerpt": value,
                    "replacement": rep,
                })

        # ── Identity block heuristic (invoice/accounting header zone) ──
        if document_type in {"invoice", "accounting", "generic"}:
            _detect_identity_block(text, matches)

    # ── De-duplicate with longest-match priority ──
    return _deduplicate(matches)


def _detect_identity_block(text: str, matches: list[dict[str, Any]]) -> None:
    """Detect and add identity block lines from invoice/accounting headers."""
    # Find header zone: before "désignation", or first 1200 chars
    desig_idx = text.lower().find("désignation")
    if desig_idx < 0:
        desig_idx = text.lower().find("designation")
    header_zone = text[:desig_idx] if desig_idx > 0 else text[:1200]

    for line in header_zone.splitlines():
        clean = line.strip()
        if not clean or len(clean) < 6:
            continue
        if _is_false_positive(clean):
            continue

        upper_count = sum(c.isupper() for c in clean)
        has_digits = any(ch.isdigit() for ch in clean)

        looks_identity = (
            # Legal form keywords
            any(kw in clean.lower() for kw in ("sci", "sas", "sarl", "eurl", "selarl"))
            # Address keywords
            or any(kw in clean.lower() for kw in ("terrasses", "rue", "avenue", "boulevard", "résidence"))
            # Two+ capitalized words (person name pattern)
            or re.search(
                r"\b[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ''\-]{2,}\s+[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ''\-]{2,}\b",
                clean,
            ) is not None
            # Heavy uppercase non-digit line (likely a name/company)
            or (upper_count >= max(5, int(len(clean) * 0.5)) and not has_digits)
        )

        if not looks_identity:
            continue

        start = text.find(line)
        if start < 0:
            continue
        end = start + len(line)
        matches.append({
            "entity_type": "invoice_identity_block",
            "start_index": start,
            "end_index": end,
            "value_excerpt": line,
            "replacement": "[IDENTITY]",
        })


def _deduplicate(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep longest match first, then left-to-right, remove overlaps."""
    matches.sort(key=lambda m: (m["start_index"], -(m["end_index"] - m["start_index"])))
    kept: list[dict[str, Any]] = []
    for candidate in matches:
        overlap = any(
            not (candidate["end_index"] <= item["start_index"] or candidate["start_index"] >= item["end_index"])
            for item in kept
        )
        if not overlap:
            kept.append(candidate)
    return kept


def anonymize_text(
    text: str,
    profile: str = "moderate",
    document_type: str = "generic",
) -> tuple[str, list[dict[str, Any]]]:
    """Apply regex-based anonymization and return (anonymized_text, detections)."""
    if not text or not text.strip():
        return text, []

    detections = _detect_entities(text, profile=profile, document_type=document_type)
    anonymized = text
    # Apply replacements from end to start to preserve indices
    for match in sorted(detections, key=lambda m: m["start_index"], reverse=True):
        anonymized = anonymized[:match["start_index"]] + match["replacement"] + anonymized[match["end_index"]:]
    return anonymized, detections
