"""ConfiDoc Backend — Anonymization Patterns."""

import re

from app.core.tokens import (
    TOKEN_ADRESSE,
    TOKEN_CADASTRE,
    TOKEN_DATE,
    TOKEN_DATE_NAISSANCE,
    TOKEN_EMAIL,
    TOKEN_EMPRUNT,
    TOKEN_IBAN,
    TOKEN_MONTANT,
    TOKEN_NAISSANCE,
    TOKEN_NSS,
    TOKEN_PERSONNE,
    TOKEN_REDACTED,
    TOKEN_REF_FACTURE,
    TOKEN_SIREN,
    TOKEN_SIRET,
    TOKEN_SOCIETE,
    TOKEN_TELEPHONE,
    TOKEN_TVA,
    TOKEN_VILLE,
)

# ──────────────────────────────────────────────────────────────────────
# REGEX PATTERNS — applied in every profile
# ──────────────────────────────────────────────────────────────────────

PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # Identifiers
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), TOKEN_EMAIL),
    ("phone_fr", re.compile(r"\b(?:\+33|0)\s?[1-9](?:[\s.\-]?\d{2}){4}\b"), TOKEN_TELEPHONE),
    ("phone_intl", re.compile(r"\+\d{1,3}[\s.\-]?\d(?:[\s.\-]?\d){6,14}\b"), TOKEN_TELEPHONE),
    (
        "iban",
        re.compile(r"\b[A-Z]{2}\d{2}[\s]?[A-Z0-9]{4}[\s]?(?:[A-Z0-9]{4}[\s]?){2,7}[A-Z0-9]{1,4}\b"),
        TOKEN_IBAN,
    ),
    ("iban_compact", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), TOKEN_IBAN),
    ("siret", re.compile(r"\b\d{3}[\s.\-]?\d{3}[\s.\-]?\d{3}[\s.\-]?\d{5}\b"), TOKEN_SIRET),
    ("siren", re.compile(r"\b\d{3}[\s.\-]?\d{3}[\s.\-]?\d{3}\b"), TOKEN_SIREN),
    ("vat_fr", re.compile(r"\bFR\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{3}\b"), TOKEN_TVA),
    ("nss", re.compile(r"\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b"), TOKEN_NSS),
    # Addresses & locations
    (
        "address_line",
        re.compile(
            r"\b\d{1,4}[\s,]+(?:rue|avenue|av\.?|boulevard|bd\.?|chemin|impasse|allée|allee|"
            r"place|quai|route|passage|cours|square|résidence|residence|lotissement|hameau|"
            r"voie|faubourg|sentier)\s+[^\n,]{3,80}",
            re.IGNORECASE,
        ),
        TOKEN_ADRESSE,
    ),
    ("postal_city", re.compile(r"\b\d{5}\s+[A-Za-zÀ-ÖØ-öø-ÿ''\- ]{2,40}\b"), TOKEN_VILLE),
    # Persons (with title prefix)
    (
        "person_title",
        re.compile(
            r"\b(?:M\.|Mr\.|Monsieur|Mme|Madame|Mlle|Mademoiselle|Dr\.?|Me|Maître|Maitre)"
            r"\s+[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ''\-]+(?:\s+[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ''\-]+){0,2}\b"
        ),
        TOKEN_PERSONNE,
    ),
]

# ──────────────────────────────────────────────────────────────────────
# STRICT-ONLY PATTERNS — applied in strict / dataset profiles
# ──────────────────────────────────────────────────────────────────────

STRICT_ONLY_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # Dates
    (
        "date_fr",
        re.compile(r"\b(?:0?[1-9]|[12]\d|3[01])[/\-.](?:0?[1-9]|1[0-2])[/\-.](?:19|20)\d{2}\b"),
        TOKEN_DATE,
    ),
    (
        "date_iso",
        re.compile(r"\b(?:19|20)\d{2}[\-/](?:0?[1-9]|1[0-2])[\-/](?:0?[1-9]|[12]\d|3[01])\b"),
        TOKEN_DATE,
    ),
    (
        "date_text_fr",
        re.compile(
            r"\b(?:0?[1-9]|[12]\d|3[01])\s+(?:janvier|février|fevrier|mars|avril|mai|juin|"
            r"juillet|août|aout|septembre|octobre|novembre|décembre|decembre)\s+(?:19|20)\d{2}\b",
            re.IGNORECASE,
        ),
        TOKEN_DATE,
    ),
    # Monetary amounts
    (
        "amount_eur",
        re.compile(
            r"\b\d{1,3}(?:[\s\u00a0]?\d{3})*(?:[.,]\d{2})?\s?(?:€|EUR|euros?)\b", re.IGNORECASE
        ),
        TOKEN_MONTANT,
    ),
    ("amount_plain", re.compile(r"\b\d{1,3}(?:[\s\u00a0]?\d{3})*,\d{2}\b"), TOKEN_MONTANT),
    # Invoice references
    (
        "invoice_number",
        re.compile(
            r"(?i)\b(?:facture|invoice|fact|fa|fac|avoir|devis|bon\sde\scommande|bdc|bl)"
            r"\s*(?:n[°o]|#|num(?:é|e)ro)?\s*[:\-]?\s*[A-Z0-9\-/]{2,20}\b"
        ),
        TOKEN_REF_FACTURE,
    ),
    # Company names (legal forms)
    (
        "company_legal_name",
        re.compile(
            r"\b(?:SAS|SARL|EURL|SCI|SELARL|SCP|SA|SNC|EI|EIRL|SASU|SEL|GIE)"
            r"\s+[A-Z0-9][A-Z0-9\s\-'&]{1,60}\b"
        ),
        TOKEN_SOCIETE,
    ),
    (
        "company_legal_suffix",
        re.compile(
            r"\b[A-Z0-9][A-Z0-9 \t\-'&]{1,60}"
            r"\s+(?:SAS|SARL|EURL|SCI|SELARL|SCP|SA|SNC|EI|EIRL|SASU|SEL|GIE)\b"
        ),
        TOKEN_SOCIETE,
    ),
    # Person names (two+ capitalized words)
    (
        "person_name",
        re.compile(
            r"\b[A-ZÀ-ÖØ-Ý][a-zà-öø-ÿ''\-]{2,}"
            r"\s+[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ''\-]{2,}\b"
        ),
        TOKEN_PERSONNE,
    ),
    # All-caps person names (e.g. "DUPONT ALICE")
    (
        "person_uppercase",
        re.compile(r"\b[A-ZÀ-ÖØ-Ý]{2,}(?:[ \t]+[A-ZÀ-ÖØ-Ý]{2,}){1,3}\b"),
        TOKEN_PERSONNE,
    ),
    # Country
    ("country", re.compile(r"\bFrance\b", re.IGNORECASE), "[PAYS]"),
    # Residence/address block patterns
    (
        "address_residence",
        re.compile(
            r"\b[A-Z]?\s?\d{1,4}\s+(?:LES\s+TERRASSES|TERRASSES|R[eé]sidence|RESIDENCE|Bâtiment|BATIMENT|B[âa]t\.?)"
            r"\s+(?:DE|DU|DES)?\s*[A-Za-zÀ-ÖØ-öø-ÿ''\- ]{3,50}\b",
            re.IGNORECASE,
        ),
        TOKEN_ADRESSE,
    ),
    # Bank account code + label  (e.g. "51210000 QONTO")
    (
        "bank_account_code_label",
        re.compile(
            r"\b(512\d{5})[^\S\r\n]+([A-Z0-9][A-Z0-9 \t\&/\\\'\-]{1,40})\b",
            re.IGNORECASE,
        ),
        TOKEN_REDACTED,
    ),
]

# ──────────────────────────────────────────────────────────────────────
# QUASI-IDENTIFIER PATTERNS — catches data that is indirectly identifying
# ──────────────────────────────────────────────────────────────────────

QUASI_IDENTIFIER_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # City names (French cities commonly found in accounting/legal docs)
    (
        "city_name",
        re.compile(
            r"\b(?:Marseille|Toulouse|Lyon|Paris|Bordeaux|Nice|Nantes|Montpellier|"
            r"Strasbourg|Lille|Rennes|Toulon|Grenoble|Dijon|Angers|Nîmes|Aix[\-\s]en[\-\s]Provence|"
            r"Saint[\-\s](?:Étienne|Etienne|Denis|Menet|Raphaël|Raphael|Tropez|Malo|Nazaire|Germain|Cloud|Ouen|Priest)|"
            r"Cannes|Perpignan|Amiens|Metz|Besançon|Besancon|Orléans|Orleans|Rouen|"
            r"Mulhouse|Caen|Nancy|Avignon|Clermont[\-\s]Ferrand|Limoges|Pau|Brest)\b",
            re.IGNORECASE,
        ),
        TOKEN_VILLE,
    ),
    # Lieux-dits, traverses, hameaux (common in southern France docs)
    (
        "lieu_dit",
        re.compile(
            r"\b(?:Traverse|Impasse|Hameau|Lotissement|Quartier|Lieu[\-\s]dit)"
            r"\s+(?:du|de|des|la|le|l')?\s*"
            r"[A-ZÀ-ÿ][A-Za-zÀ-ÿ'\-\s]{2,40}\b",
            re.IGNORECASE,
        ),
        TOKEN_ADRESSE,
    ),
    # Loan / credit references (6-15 digits after a label)
    (
        "loan_ref",
        re.compile(
            r"(?i)(?:emprunt|prêt|pret|crédit|credit|n[°o]\s*(?:de\s+)?(?:prêt|pret|contrat))"
            r"\s*(?:n[°o]?)?\s*[:\-]?\s*(\d{6,15})"
        ),
        TOKEN_EMPRUNT,
    ),
    # Cadastral / property references (long numeric sequences)
    (
        "cadastral_ref",
        re.compile(
            r"\b(?:invariant|référence\s+cadastrale|ref\.?\s+cadastrale|cadastre)"
            r"\s*[:\-]?\s*([A-Z0-9]{8,25})\b",
            re.IGNORECASE,
        ),
        TOKEN_CADASTRE,
    ),
    # Birth context: "Né(e) le DD/MM/YYYY à VILLE"
    (
        "birth_context",
        re.compile(
            r"(?i)n[ée]+e?\s+(?:le\s+)?\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}"
            r"(?:\s+[àa]\s+[A-ZÀ-ÿ][A-Za-zÀ-ÿ'\-\s]{1,30})?"
        ),
        TOKEN_NAISSANCE,
    ),
    # Standalone birth date with label
    (
        "birth_date_labeled",
        re.compile(
            r"(?i)(?:date\s+de\s+naissance|né(?:e)?\s+le)\s*[:\-]?\s*"
            r"\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}"
        ),
        TOKEN_DATE_NAISSANCE,
    ),
    # Birth place with label
    (
        "birth_place_labeled",
        re.compile(
            r"(?i)(?:lieu\s+de\s+naissance|commune\s+de\s+naissance|n[ée]+e?\s+[àa])"
            r"\s*[:\-]?\s*[A-ZÀ-ÿ][A-Za-zÀ-ÿ'\-\s]{1,40}"
        ),
        TOKEN_NAISSANCE,
    ),
    # APT / apartment numbers in address blocks
    (
        "apartment_ref",
        re.compile(r"(?i)\b(?:apt|appt|appartement|app)\.?\s*(?:n[°o]?)?\s*\d{1,5}\b"),
        TOKEN_ADRESSE,
    ),
]

# ──────────────────────────────────────────────────────────────────────
# LABEL : VALUE  detection  (e.g. "Nom : Baranes")
# ──────────────────────────────────────────────────────────────────────

LABEL_VALUE_PATTERN = re.compile(
    r"(?im)^(?:nom|prénom|prenom|raison\s+sociale|société|societe|"
    r"expert[\-\s]?comptable|cabinet|comptable|prestataire\s+ecf|"
    r"d[ée]nomination(?:\s+de\s+l[’']?entreprise)?|d[ée]signation\s+de\s+l[’']?entreprise|"
    r"client|destinataire|titulaire|bénéficiaire|beneficiaire|"
    r"adresse|email|e[\-]?mail|téléphone|telephone|tel|tél|mobile|portable|"
    r"iban|bic|siret|siren|tva(?:\s+intracom)?|"
    r"n[°o]\s*(?:client|compte|dossier|contrat))"
    r"\s*[:\-]\s*(.+)$"
)

# BIC should be detected only with an explicit label to avoid masking accounting words.
BIC_LABELED_PATTERN = re.compile(r"(?im)\bBIC\b\s*[:\-]?\s*([A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b")


# ──────────────────────────────────────────────────────────────────────
# FALSE-POSITIVE FILTER — words that look like entities but aren't
# ──────────────────────────────────────────────────────────────────────

FALSE_POSITIVE_WORDS: set[str] = {
    # Common uppercase header words in French accounting/invoices
    "FACTURE", "AVOIR", "DEVIS", "TOTAL", "MONTANT", "DESIGNATION", "DÉSIGNATION",
    "DESCRIPTION", "QUANTITÉ", "QUANTITE", "PRIX", "UNITAIRE", "HT", "TTC", "TVA",
    "SOLDE", "REPORT", "SOUS", "DATE", "NUMERO", "NUMÉRO", "RÉFÉRENCE", "REFERENCE",
    "PAGE", "OBJET", "NOTE", "COMPTE", "DÉBIT", "DEBIT", "CRÉDIT", "CREDIT", "PIÈCE",
    "PIECE", "LIBELLÉ", "LIBELLE", "JOURNAL", "EXERCICE", "PÉRIODE", "PERIODE",
    "BILAN", "ACTIF", "PASSIF", "CHARGES", "PRODUITS", "RÉSULTAT", "RESULTAT",
    "BRUT", "NET", "BALANCE", "GÉNÉRALE", "GENERALE", "ANALYTIQUE", "AUXILIAIRE",
    "GRAND", "LIVRE", "BORDEREAU", "RÉCAPITULATIF", "RECAPITULATIF", "BON",
    "COMMANDE", "LIVRAISON", "RETOUR", "MODE", "PAIEMENT", "CONDITIONS",
    "GÉNÉRALES", "GENERALES", "VENTE", "ACHAT", "CLIENT", "FOURNISSEUR",
    "CHIFFRE", "AFFAIRES", "EXPLOITATION", "EXCEPTIONNEL", "FINANCIERES",
    "NETTES", "COURANT", "ACTIFS", "CREANCES", "PARTICIPATIONS", "DISPONIBILITES",
    "IMMOBILISATIONS", "CAPITAUX", "DETTES", "RATTACHEES", "CLOS", "VARIATION",
    "NOUVEAU", "COMPTES",
}

ACCOUNTING_GUARD_PATTERNS = (
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
