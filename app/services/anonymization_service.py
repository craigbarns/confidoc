"""ConfiDoc Backend — Text extraction and anonymization service (v3).

v3 changes:
- EntityRegistry for stable, consistent placeholder naming
- Quasi-identifier patterns (cities, lieux-dits, loans, birth, cadastral)
- Post-OCR artifact cleanup
"""

from functools import lru_cache
import re
import unicodedata
from typing import Any

from app.services.entity_registry import EntityRegistry

import fitz

from app.core.logging import get_logger
from app.core.text_sanitize import postgres_safe_text

logger = get_logger(__name__)

try:
    import pytesseract
    from PIL import Image, ImageFilter, ImageOps, ImageEnhance
    from io import BytesIO
    from pdf2image import convert_from_bytes
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import pymupdf4llm
    HAS_MD_EXTRACTOR = True
except ImportError:
    HAS_MD_EXTRACTOR = False

try:
    from doctr.io import DocumentFile as DoctrDocumentFile
    from doctr.models import ocr_predictor as doctr_ocr_predictor

    HAS_DOCTR = True
except ImportError:
    HAS_DOCTR = False


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
        re.compile(r"\b(512\d{5})\s+([A-Z0-9][A-Z0-9\s\&/\\\'\-]{1,40})\b", re.IGNORECASE),
        "[REDACTED]",
    ),
]

# ──────────────────────────────────────────────────────────────────────
# QUASI-IDENTIFIER PATTERNS — catches data that is indirectly identifying
# ──────────────────────────────────────────────────────────────────────

QUASI_IDENTIFIER_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # City names (French cities commonly found in accounting/legal docs)
    ("city_name", re.compile(
        r"\b(?:Marseille|Toulouse|Lyon|Paris|Bordeaux|Nice|Nantes|Montpellier|"
        r"Strasbourg|Lille|Rennes|Toulon|Grenoble|Dijon|Angers|Nîmes|Aix[\-\s]en[\-\s]Provence|"
        r"Saint[\-\s](?:Étienne|Etienne|Denis|Menet|Raphaël|Raphael|Tropez|Malo|Nazaire|Germain|Cloud|Ouen|Priest)|"
        r"Cannes|Perpignan|Amiens|Metz|Besançon|Besancon|Orléans|Orleans|Rouen|"
        r"Mulhouse|Caen|Nancy|Avignon|Clermont[\-\s]Ferrand|Limoges|Pau|Brest)\b",
        re.IGNORECASE,
    ), "[VILLE]"),

    # Lieux-dits, traverses, hameaux (common in southern France docs)
    ("lieu_dit", re.compile(
        r"\b(?:Traverse|Impasse|Hameau|Lotissement|Quartier|Lieu[\-\s]dit)"
        r"\s+(?:du|de|des|la|le|l')?\s*"
        r"[A-ZÀ-ÿ][A-Za-zÀ-ÿ'\-\s]{2,40}\b",
        re.IGNORECASE,
    ), "[LIEU]"),

    # Loan / credit references (6-15 digits after a label)
    ("loan_ref", re.compile(
        r"(?i)(?:emprunt|prêt|pret|crédit|credit|n[°o]\s*(?:de\s+)?(?:prêt|pret|contrat))"
        r"\s*(?:n[°o]?)?\s*[:\-]?\s*(\d{6,15})"
    ), "[EMPRUNT]"),

    # Cadastral / property references (long numeric sequences)
    ("cadastral_ref", re.compile(
        r"\b(?:invariant|référence\s+cadastrale|ref\.?\s+cadastrale|cadastre)"
        r"\s*[:\-]?\s*([A-Z0-9]{8,25})\b",
        re.IGNORECASE,
    ), "[REF_CADASTRALE]"),

    # Birth context: "Né(e) le DD/MM/YYYY à VILLE"
    ("birth_context", re.compile(
        r"(?i)n[ée]+e?\s+(?:le\s+)?\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}"
        r"(?:\s+[àa]\s+[A-ZÀ-ÿ][A-Za-zÀ-ÿ'\-\s]{1,30})?"
    ), "[NAISSANCE]"),

    # Standalone birth date with label
    ("birth_date_labeled", re.compile(
        r"(?i)(?:date\s+de\s+naissance|né(?:e)?\s+le)\s*[:\-]?\s*"
        r"\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}"
    ), "[DATE_NAISSANCE]"),

    # Birth place with label
    ("birth_place_labeled", re.compile(
        r"(?i)(?:lieu\s+de\s+naissance|commune\s+de\s+naissance|n[ée]+e?\s+[àa])"
        r"\s*[:\-]?\s*[A-ZÀ-ÿ][A-Za-zÀ-ÿ'\-\s]{1,40}"
    ), "[LIEU_NAISSANCE]"),

    # APT / apartment numbers in address blocks
    ("apartment_ref", re.compile(
        r"(?i)\b(?:apt|appt|appartement|app)\.?\s*(?:n[°o]?)?\s*\d{1,5}\b"
    ), "[APT]"),
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


# ──────────────────────────────────────────────────────────────────────
# OCR IMAGE PREPROCESSING — dramatically improves Tesseract accuracy
# ──────────────────────────────────────────────────────────────────────


def _preprocess_image_for_ocr(img: "Image.Image") -> "Image.Image":
    """Apply a multi-step preprocessing pipeline to boost OCR accuracy.

    Steps:
    1. Convert to grayscale
    2. Up-scale small images (< 300 DPI equivalent)
    3. Denoise with median filter
    4. Enhance contrast (CLAHE-like via adaptive histogram)
    5. Sharpen
    6. Binarize with adaptive threshold (Otsu-style via ImageOps.autocontrast)
    7. Deskew if numpy is available
    """
    # 1. Grayscale
    img = img.convert("L")

    # 2. Up-scale small images — Tesseract works best at 300+ DPI
    width, height = img.size
    if width < 1800 or height < 1800:
        scale = max(2, 2400 // min(width, height))
        scale = min(scale, 4)  # cap at 4x
        img = img.resize((width * scale, height * scale), Image.LANCZOS)

    # 3. Denoise — removes speckles from scans
    img = img.filter(ImageFilter.MedianFilter(size=3))

    # 4. Contrast enhancement
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.8)

    # 5. Sharpen — recover edges after denoise
    img = img.filter(ImageFilter.SHARPEN)

    # 6. Binarize (black & white) — adaptive autocontrast + threshold
    img = ImageOps.autocontrast(img, cutoff=2)

    # 7. Deskew (straighten tilted scans) — requires numpy
    if HAS_NUMPY:
        try:
            img = _deskew_image(img)
        except Exception:
            pass  # deskew is best-effort

    return img


def _deskew_image(img: "Image.Image") -> "Image.Image":
    """Deskew a grayscale image by detecting dominant line angle."""
    arr = np.array(img)
    # Compute horizontal projection profile variance at different angles
    best_angle = 0.0
    best_score = 0.0
    for angle_10x in range(-50, 51, 5):  # -5.0° to +5.0° in 0.5° steps
        angle = angle_10x / 10.0
        rotated = img.rotate(angle, fillcolor=255, expand=False)
        row_sums = np.sum(np.array(rotated) < 128, axis=1)
        score = float(np.var(row_sums))
        if score > best_score:
            best_score = score
            best_angle = angle
    if abs(best_angle) > 0.3:
        img = img.rotate(best_angle, fillcolor=255, expand=True)
        logger.debug("deskew_applied", angle=best_angle)
    return img


def _get_tesseract_config() -> str:
    """Build optimal Tesseract configuration string."""
    # --oem 3: LSTM + legacy combined engine (best accuracy)
    # --psm 6: Assume uniform block of text (best for scanned docs)
    # preserve_interword_spaces: keep spacing for table-heavy docs
    return "--oem 3 --psm 6 -c preserve_interword_spaces=1"


def _ocr_image(img: "Image.Image", lang: str = "fra+eng") -> str:
    """Run Tesseract OCR on a single image with preprocessing and optimal config."""
    processed = _preprocess_image_for_ocr(img)
    config = _get_tesseract_config()
    return str(pytesseract.image_to_string(processed, lang=lang, config=config)).strip()


@lru_cache(maxsize=1)
def _get_doctr_model():
    if not HAS_DOCTR:
        raise RuntimeError("docTR not installed")
    return doctr_ocr_predictor(pretrained=True)


def _ocr_with_doctr_pdf(content: bytes, page_markers: bool) -> str:
    """Run docTR OCR on a PDF and return page-concatenated text."""
    model = _get_doctr_model()
    doc = DoctrDocumentFile.from_pdf(content)
    result = model(doc)
    payload = result.export()
    pages_out: list[str] = []
    for i, page in enumerate(payload.get("pages", []), start=1):
        lines: list[str] = []
        for block in page.get("blocks", []):
            for line in block.get("lines", []):
                words = [w.get("value", "") for w in line.get("words", []) if w.get("value")]
                if words:
                    lines.append(" ".join(words))
        page_text = "\n".join(lines).strip()
        if page_markers:
            pages_out.append(f"---PAGE {i}---\n{page_text}")
        else:
            pages_out.append(page_text)
    return "\n".join(pages_out).strip()


def _score_ocr_text_candidate(text: str) -> int:
    """Simple robustness score to pick better OCR text candidate."""
    if not text:
        return 0
    words = len(text.split())
    digits = len(re.findall(r"\d", text))
    tables = len(re.findall(r"\b(total|résultat|resultat|passif|actif|revenus?)\b", text, re.IGNORECASE))
    return (words * 2) + digits + (tables * 10)


def _extract_pdf_text_via_ocr_engines(
    content: bytes, *, dpi: int, lang: str, page_markers: bool, engine: str
) -> tuple[str, str]:
    """Extract OCR text with selected strategy (tesseract/doctr/auto)."""
    candidates: list[tuple[str, str]] = []

    # Tesseract candidate
    if engine in ("auto", "tesseract") and HAS_OCR:
        try:
            images = convert_from_bytes(content, dpi=dpi)
            chunks: list[str] = []
            for i, img in enumerate(images):
                chunk = _ocr_image(img, lang=lang)
                chunks.append(f"---PAGE {i + 1}---\n{chunk}" if page_markers else chunk)
            candidates.append(("tesseract", "\n".join(chunks).strip()))
        except Exception as exc:
            logger.warning("ocr_tesseract_failed", extension="pdf", error=str(exc))

    # docTR candidate
    if engine in ("auto", "doctr") and HAS_DOCTR:
        try:
            txt = _ocr_with_doctr_pdf(content, page_markers=page_markers)
            candidates.append(("doctr", txt))
        except Exception as exc:
            logger.warning("ocr_doctr_failed", extension="pdf", error=str(exc))

    if not candidates:
        return "", ""

    method, best_text = max(candidates, key=lambda c: _score_ocr_text_candidate(c[1]))
    logger.info("document_extraction", method=f"ocr_{method}_pdf", extension="pdf")
    return best_text, method


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
    text, _meta = extract_text_from_file_with_meta(content, extension)
    return text


def extract_text_from_file_with_meta(content: bytes, extension: str) -> tuple[str, dict[str, Any]]:
    """Extract text + debug metadata about extraction/OCR engine selection."""
    extraction_meta: dict[str, Any] = {
        "extension": extension.lower().strip("."),
        "method": "unknown",
        "ocr_engine": None,
        "ocr_strategy": None,
    }
    text = _extract_text_from_file_raw(content, extension, extraction_meta=extraction_meta)
    return postgres_safe_text(text), extraction_meta


def _extract_text_from_file_raw(
    content: bytes, extension: str, extraction_meta: dict[str, Any] | None = None
) -> str:
    extension = extension.lower().strip(".")
    meta = extraction_meta if isinstance(extraction_meta, dict) else {}

    if extension == "pdf":
        ext_text = ""
        # 1. Tentative d'extraction structurée (Markdown + Tableaux)
        if HAS_MD_EXTRACTOR:
            import tempfile
            import os
            # pymupdf4llm est plus robuste sur un fichier physique que sur un stream en mémoire
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                ext_text = pymupdf4llm.to_markdown(tmp_path)
            except Exception as e:
                logger.error("pymupdf4llm_failed", error=str(e))
                ext_text = ""
            finally:
                os.unlink(tmp_path)
        
        # 2. Fallback d'extraction de texte native (si markdown a échoué)
        if not ext_text or not str(ext_text).strip():
            try:
                from app.config import get_settings

                page_markers = bool(get_settings().PDF_PAGE_MARKERS)
                text_chunks = []
                with fitz.open(stream=content, filetype="pdf") as doc:
                    for i, page in enumerate(doc):
                        raw = page.get_text("text")
                        if page_markers:
                            text_chunks.append(f"---PAGE {i + 1}---\n{raw}")
                        else:
                            text_chunks.append(raw)
                ext_text = "\n".join(text_chunks)
            except Exception as e:
                logger.warning("native_pdf_text_extraction_failed", error=str(e))
                ext_text = ""

        ext_text = str(ext_text).strip()

        # Sortie markdown (pymupdf4llm) : pas de ---PAGE--- dans le corps → préfixe nombre de pages.
        if ext_text and "---PAGE " not in ext_text[:4000]:
            try:
                from app.config import get_settings

                if bool(get_settings().PDF_PAGE_MARKERS):
                    with fitz.open(stream=content, filetype="pdf") as doc:
                        npages = len(doc)
                    if npages > 0:
                        ext_text = f"---PDF {npages} PAGES---\n\n" + ext_text
            except Exception:
                pass

        # If text is very short (< 10 words) or empty, maybe it's a scan — try OCR fallback
        if len(ext_text.split()) < 10:
            try:
                from app.config import get_settings

                settings = get_settings()
                page_markers = bool(settings.PDF_PAGE_MARKERS)
                ocr_dpi = getattr(settings, "OCR_DPI", 300)
                ocr_lang = getattr(settings, "OCR_LANG", "fra+eng")
                ocr_engine = getattr(settings, "OCR_ENGINE", "auto")
                ocr_text, selected_engine = _extract_pdf_text_via_ocr_engines(
                    content,
                    dpi=ocr_dpi,
                    lang=ocr_lang,
                    page_markers=page_markers,
                    engine=str(ocr_engine),
                )
                if ocr_text:
                    meta["method"] = "ocr_pdf_fallback"
                    meta["ocr_strategy"] = str(ocr_engine)
                    meta["ocr_engine"] = selected_engine
                    return ocr_text
            except Exception as exc:
                logger.warning(
                    "document_extraction",
                    method="native_pdf_empty_ocr_failed",
                    extension="pdf",
                    error=str(exc),
                )
                return ext_text
        
        meta["method"] = "native_pdf_pymupdf"
        logger.info("document_extraction", method="native_pdf_pymupdf", extension="pdf")
        return ext_text

    # Image support (PNG, JPG, TIFF) via OCR with full preprocessing
    if extension in ["png", "jpg", "jpeg", "tiff", "tif"] and HAS_OCR:
        try:
            from app.config import get_settings
            settings = get_settings()
            ocr_lang = getattr(settings, "OCR_LANG", "fra+eng")
            img = Image.open(BytesIO(content))

            # For multi-page TIFF, process all frames
            if extension in ["tiff", "tif"]:
                ocr_chunks = []
                frame_idx = 0
                try:
                    while True:
                        img.seek(frame_idx)
                        chunk = _ocr_image(img.copy(), lang=ocr_lang)
                        if chunk:
                            ocr_chunks.append(f"---PAGE {frame_idx + 1}---\n{chunk}")
                        frame_idx += 1
                except EOFError:
                    pass
                if ocr_chunks:
                    meta["method"] = "ocr_tesseract_tiff_enhanced"
                    meta["ocr_engine"] = "tesseract"
                    logger.info(
                        "document_extraction",
                        method="ocr_tesseract_tiff_enhanced",
                        extension=extension,
                        pages=frame_idx,
                    )
                    return "\n".join(ocr_chunks).strip()

            result = _ocr_image(img, lang=ocr_lang)
            meta["method"] = "ocr_tesseract_image_enhanced"
            meta["ocr_engine"] = "tesseract"
            logger.info(
                "document_extraction",
                method="ocr_tesseract_image_enhanced",
                extension=extension,
            )
            return result
        except Exception as exc:
            logger.warning("ocr_image_failed", extension=extension, error=str(exc))

    meta["method"] = "fallback_plain_text_or_error"
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

    # ── Quasi-identifier patterns (always applied in strict, optional in moderate) ──
    if is_strict or profile == "moderate":
        for entity_type, pattern, replacement in QUASI_IDENTIFIER_PATTERNS:
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


def _apply_business_pseudonyms(
    text: str,
    detections: list[dict[str, Any]],
    registry: EntityRegistry | None = None,
) -> list[dict[str, Any]]:
    """Replace generic tokens by stable business pseudonyms using EntityRegistry.

    Same value → same placeholder everywhere in the document.
    """
    if registry is None:
        registry = EntityRegistry()

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
        placeholder = registry.get_or_create(value, prefix)
        new_d = dict(d)
        new_d["replacement"] = placeholder
        out.append(new_d)
    return out


# ──────────────────────────────────────────────────────────────────────
# POST-OCR CLEANUP — fix artifacts after anonymization
# ──────────────────────────────────────────────────────────────────────

# Common OCR typos in French accounting documents
_OCR_FIXES: dict[str, str] = {
    "TELEGÉLISATION": "TÉLÉGESTION",
    "TELEGESTION": "TÉLÉGESTION",
    "TELEBEC": "TÉLÉDEC",
    "TELEDEC": "TÉLÉDEC",
    "DGPIP": "DGFiP",
    "Dérivations": "Déclarations",
    "DERIVATIONS": "DÉCLARATIONS",
    "EXRCICE": "EXERCICE",
    "RESUTLAT": "RÉSULTAT",
    "RESUTAT": "RÉSULTAT",
    "RESULAT": "RÉSULTAT",
    "BIIAN": "BILAN",
    "BLLAN": "BILAN",
    "PASSIE": "PASSIF",
    "PRODUTIS": "PRODUITS",
    "CHAGRES": "CHARGES",
    "CHARCES": "CHARGES",
}


def clean_ocr_artifacts(text: str) -> str:
    """Clean OCR artifacts from anonymized text.

    Fixes:
    1. Broken tokens: [SOCIETE_1]É → [SOCIETE_1]
    2. Duplicate adjacent tokens: [PERSONNE_1] [PERSONNE_1] → [PERSONNE_1]
    3. Excessive blank lines → max 2
    4. Common accounting OCR typos
    5. Orphan brackets from partial replacements
    """
    if not text:
        return text

    # 1. Broken tokens: [TOKEN]TrailingChars → [TOKEN]
    text = re.sub(r"(\[[A-Z_]+\d*\])[A-ZÀ-ÿa-zà-ÿ]{1,3}\b", r"\1", text)

    # 2. Duplicate adjacent tokens (with optional whitespace between)
    text = re.sub(r"(\[[A-Z_]+\d*\])\s*\1", r"\1", text)

    # 3. Excessive blank lines → max 2 consecutive
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    # 4. Fix common OCR typos in accounting terms
    for wrong, correct in _OCR_FIXES.items():
        text = text.replace(wrong, correct)

    # 5. Clean orphan closing brackets after tokens
    text = re.sub(r"(\[[A-Z_]+\d*\])\]", r"\1", text)

    # 6. Clean up spaces before punctuation
    text = re.sub(r"\s+([.,;:])", r"\1", text)

    return text


def anonymize_text(
    text: str,
    profile: str = "moderate",
    document_type: str = "generic",
    registry: EntityRegistry | None = None,
) -> tuple[str, list[dict[str, Any]], EntityRegistry]:
    """Apply regex-based anonymization and return (anonymized_text, detections, registry).

    Args:
        text: Raw text to anonymize
        profile: Anonymization profile (moderate/strict/dataset_*)
        document_type: Document type hint (invoice/accounting/legal/generic)
        registry: Optional pre-seeded EntityRegistry for consistent naming

    Returns:
        Tuple of (anonymized_text, detections_list, entity_registry)
    """
    if not text or not text.strip():
        return text, [], registry or EntityRegistry()

    if registry is None:
        registry = EntityRegistry()

    detections = _detect_entities(text, profile=profile, document_type=document_type)
    if profile == "dataset_accounting_pseudo":
        detections = _apply_business_pseudonyms(text, detections, registry)
    anonymized = text
    # Apply replacements from end to start to preserve indices
    for match in sorted(detections, key=lambda m: m["start_index"], reverse=True):
        anonymized = anonymized[:match["start_index"]] + match["replacement"] + anonymized[match["end_index"]:]

    # Post-OCR cleanup
    anonymized = clean_ocr_artifacts(anonymized)

    return anonymized, detections, registry
