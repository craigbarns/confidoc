"""ConfiDoc Backend — Text extraction and anonymization service (v2)."""

import re
import unicodedata
from typing import Any

import fitz

from app.core.logging import get_logger

logger = get_logger(__name__)

try:
    import pytesseract
    from PIL import Image
    from io import BytesIO
    from pdf2image import convert_from_bytes
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

try:
    import pymupdf4llm
    HAS_MD_EXTRACTOR = True
except ImportError:
    HAS_MD_EXTRACTOR = False


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

# BIC should be detected only with an explicit label to avoid masking accounting words.
BIC_LABELED_PATTERN = re.compile(
    r"(?im)\bBIC\b\s*[:\-]?\s*([A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b"
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
    # Extra accounting words frequently hit by OCR/NER false positives
    "CHIFFRE", "AFFAIRES", "EXPLOITATION", "EXCEPTIONNEL", "FINANCIERES",
    "NETTES", "COURANT", "ACTIFS", "CREANCES", "PARTICIPATIONS",
    "DISPONIBILITES", "IMMOBILISATIONS", "CAPITAUX", "DETTES",
    "RATTACHEES", "EXERCICE", "CLOS", "VARIATION", "REPORT",
    "NOUVEAU", "COMPTE", "COMPTES", "RÉSULTAT", "RESULTAT",
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
    """Extract text from uploaded bytes (PDF first, images later) preserving structural layout."""
    extension = extension.lower().strip(".")

    if extension == "pdf":
        ext_text = ""
        try:
            if HAS_MD_EXTRACTOR:
                # Use Advanced Layout Extraction (markdown with table preservation)
                with fitz.open(stream=content, filetype="pdf") as doc:
                    ext_text = pymupdf4llm.to_markdown(doc)
            else:
                # Fallback to basic text extraction
                text_chunks = []
                with fitz.open(stream=content, filetype="pdf") as doc:
                    for page in doc:
                        text_chunks.append(page.get_text("text"))
                ext_text = "\n".join(text_chunks)
        except Exception:
            pass

        ext_text = ext_text.strip()

        # If text is very short (< 10 words) or empty, maybe it's a scan — try OCR fallback
        if len(ext_text.split()) < 10 and HAS_OCR:
            try:
                images = convert_from_bytes(content)
                ocr_chunks = [pytesseract.image_to_string(img, lang="fra") for img in images]
                logger.info("document_extraction", method="ocr_tesseract_pdf", extension="pdf")
                return "\n".join(ocr_chunks).strip()
            except Exception:
                logger.info("document_extraction", method="native_pdf_empty_ocr_failed", extension="pdf")
                return ext_text
        
        logger.info("document_extraction", method="native_pdf_pymupdf", extension="pdf")
        return ext_text

    # Image support (PNG, JPG, TIFF) via OCR
    if extension in ["png", "jpg", "jpeg", "tiff", "tif"] and HAS_OCR:
        try:
            img = Image.open(BytesIO(content))
            logger.info("document_extraction", method="ocr_tesseract_image", extension=extension)
            return str(pytesseract.image_to_string(img, lang="fra")).strip()
        except Exception:
            pass

    logger.warning("document_extraction", method="fallback_plain_text_or_error", extension=extension)
    # Plain text fallback
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
    # Typical accounting labels that must stay readable
    accounting_guard_patterns = (
        r"\bCHIFFRE\s+D[’']AFFAIRES\b",
        r"\bCHARGES?\s+D[’']EXPLOITATION\b",
        r"\bPRODUITS?\s+D[’']EXPLOITATION\b",
        r"\bR[ÉE]SULTAT\s+DE\s+L[’']EXERCICE\b",
        r"\bCR[ÉE]ANCES?\s+RATTACH[ÉE]ES?\s+[ÀA]\s+DES?\s+PARTICIPATIONS\b",
        r"\bVALEURS?\s+NETTES?\b",
        r"\bBILAN\b",
        r"\bACTIF\b",
        r"\bPASSIF\b",
    )
    if any(re.search(pat, clean) for pat in accounting_guard_patterns):
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

    # ── BIC detection only when explicitly labeled (avoid false positives) ──
    for match in BIC_LABELED_PATTERN.finditer(text):
        value = match.group(1).strip()
        if not value or _is_false_positive(value):
            continue
        matches.append({
            "entity_type": "bic",
            "start_index": match.start(1),
            "end_index": match.end(1),
            "value_excerpt": value,
            "replacement": "[BIC]",
        })

    # ── Strict-only patterns ──
    is_strict = profile in {"strict", "dataset_strict", "dataset_accounting", "dataset_accounting_pseudo"}
    if is_strict:
        for entity_type, pattern, replacement in STRICT_ONLY_PATTERNS:
            # Dataset accounting: keep amounts for business utility
            if profile in {"dataset_accounting", "dataset_accounting_pseudo"} and entity_type in {"amount_eur", "amount_plain"}:
                continue

            for match in pattern.finditer(text):
                value = match.group(0)
                if _is_false_positive(value):
                    continue

                rep = replacement
                # Bank account: keep code in accounting mode
                if entity_type == "bank_account_code_label":
                    code = match.group(1)
                    rep = f"{code} [REDACTED]" if profile in {"dataset_accounting", "dataset_accounting_pseudo"} else "[REDACTED]"

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


def _normalize_value_key(value: str) -> str:
    """Normalize detected value for stable pseudonym mapping."""
    txt = unicodedata.normalize("NFKD", (value or ""))
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = re.sub(r"\s+", " ", txt.strip().upper())
    return txt


def _infer_business_prefix(
    text: str,
    entity_type: str,
    value_excerpt: str,
    start_index: int,
    end_index: int,
) -> str:
    """Infer business pseudonym prefix from entity + local context."""
    left = max(0, start_index - 80)
    right = min(len(text), end_index + 80)
    ctx = text[left:right].lower()
    line_start = text.rfind("\n", 0, start_index) + 1
    line_end = text.find("\n", end_index)
    if line_end < 0:
        line_end = len(text)
    line = text[line_start:line_end].lower()

    if entity_type in {"person_name", "person_uppercase", "person_title"}:
        if "associe" in ctx or re.search(r"\b455\d{3,6}\b", line):
            return "ASSOCIE"
        if "fournisseur" in ctx:
            return "FOURNISSEUR"
        if "client" in ctx:
            return "CLIENT"
        return "PERSONNE"

    if entity_type in {"company_legal_name", "invoice_identity_block"}:
        if "fournisseur" in ctx:
            return "FOURNISSEUR"
        if "client" in ctx:
            return "CLIENT"
        return "SOCIETE"

    if entity_type in {"address_line", "address_residence"}:
        if any(k in ctx for k in ("loyer", "immeuble", "bien", "locatif", "locat", "residence", "résidence", "batiment", "bâtiment")):
            return "BIEN"
        return "ADRESSE"

    if entity_type == "postal_city":
        return "VILLE"

    if entity_type in {"iban", "iban_compact", "bic"}:
        return "BANQUE"

    if entity_type in {"bank_account_code_label", "siret", "siren", "vat_fr", "invoice_number"}:
        return "COMPTE"

    if entity_type == "nss":
        return "PERSONNE"

    if entity_type in {"date_fr", "date_iso", "date_text_fr"}:
        return "DATE"

    if entity_type == "labeled_sensitive_value":
        v = (value_excerpt or "").lower()
        if "iban" in v or "bic" in v:
            return "BANQUE"
        if "adresse" in v:
            return "ADRESSE"
        if "ville" in v:
            return "VILLE"
        if "siret" in v or "siren" in v:
            return "COMPTE"
        return "DONNEE"

    return "DONNEE"


def _apply_business_pseudonyms(text: str, detections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace generic tokens by stable business pseudonyms inside one document."""
    counters: dict[str, int] = {}
    mapping: dict[tuple[str, str], str] = {}
    out: list[dict[str, Any]] = []
    for d in detections:
        entity_type = str(d.get("entity_type", ""))
        value = str(d.get("value_excerpt", ""))
        prefix = _infer_business_prefix(
            text=text,
            entity_type=entity_type,
            value_excerpt=value,
            start_index=int(d.get("start_index", 0)),
            end_index=int(d.get("end_index", 0)),
        )
        key = (prefix, _normalize_value_key(value))
        if key not in mapping:
            counters[prefix] = counters.get(prefix, 0) + 1
            mapping[key] = f"{prefix}_{counters[prefix]}"
        new_d = dict(d)
        new_d["replacement"] = mapping[key]
        out.append(new_d)
    return out


def anonymize_text(
    text: str,
    profile: str = "moderate",
    document_type: str = "generic",
) -> tuple[str, list[dict[str, Any]]]:
    """Apply regex-based anonymization and return (anonymized_text, detections)."""
    if not text or not text.strip():
        return text, []

    detections = _detect_entities(text, profile=profile, document_type=document_type)
    if profile == "dataset_accounting_pseudo":
        detections = _apply_business_pseudonyms(text, detections)
    anonymized = text
    # Apply replacements from end to start to preserve indices
    for match in sorted(detections, key=lambda m: m["start_index"], reverse=True):
        anonymized = anonymized[:match["start_index"]] + match["replacement"] + anonymized[match["end_index"]:]
    return anonymized, detections
