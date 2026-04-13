"""ConfiDoc — Tokens d'anonymisation centralisés.

Source unique de vérité pour tous les placeholders PII utilisés
par le pipeline regex ET le pipeline LLM. Toute modification ici
se propage automatiquement aux deux moteurs.
"""

# ── Identifiants personnels ────────────────────────────────────────────
TOKEN_PERSONNE = "[PERSONNE]"
TOKEN_EMAIL = "[EMAIL]"
TOKEN_TELEPHONE = "[TELEPHONE]"
TOKEN_NSS = "[NSS]"          # Numéro de sécurité sociale
TOKEN_DATE = "[DATE]"
TOKEN_DATE_NAISSANCE = "[DATE_NAISSANCE]"

# ── Entités légales & financières ─────────────────────────────────────
TOKEN_SOCIETE = "[SOCIETE]"
TOKEN_SIRET = "[SIRET]"
TOKEN_SIREN = "[SIREN]"
TOKEN_TVA = "[TVA]"
TOKEN_IBAN = "[IBAN]"
TOKEN_MONTANT = "[MONTANT]"
TOKEN_REF_FACTURE = "[REF_FACTURE]"

# ── Adresses & lieux ───────────────────────────────────────────────────
TOKEN_ADRESSE = "[ADRESSE]"
TOKEN_VILLE = "[VILLE]"

# ── Références spécialisées (quasi-identifiants) ───────────────────────
TOKEN_EMPRUNT = "[EMPRUNT]"
TOKEN_CADASTRE = "[CADASTRE]"
TOKEN_NAISSANCE = "[NAISSANCE]"     # Lieu ou info naissance (hors date)

# ── Divers ─────────────────────────────────────────────────────────────
TOKEN_ID = "[ID]"
TOKEN_REDACTED = "[REDACTED]"

# ── Mapping sémantique → token (utilisé par _infer_semantic_type) ─────
SEMANTIC_MAP: dict[str, str] = {
    "PERSONNE": TOKEN_PERSONNE,
    "PERSON": TOKEN_PERSONNE,
    "EMAIL": TOKEN_EMAIL,
    "TELEPHONE": TOKEN_TELEPHONE,
    "PHONE": TOKEN_TELEPHONE,
    "NSS": TOKEN_NSS,
    "NUMERO_SECU": TOKEN_NSS,
    "DATE": TOKEN_DATE,
    "DATE_NAISSANCE": TOKEN_DATE_NAISSANCE,
    "SOCIETE": TOKEN_SOCIETE,
    "COMPANY": TOKEN_SOCIETE,
    "SIRET": TOKEN_SIRET,
    "SIREN": TOKEN_SIREN,
    "TVA": TOKEN_TVA,
    "VAT": TOKEN_TVA,
    "IBAN": TOKEN_IBAN,
    "MONTANT": TOKEN_MONTANT,
    "AMOUNT": TOKEN_MONTANT,
    "REF_FACTURE": TOKEN_REF_FACTURE,
    "INVOICE_REF": TOKEN_REF_FACTURE,
    "ADRESSE": TOKEN_ADRESSE,
    "ADDRESS": TOKEN_ADRESSE,
    "VILLE": TOKEN_VILLE,
    "CITY": TOKEN_VILLE,
    "EMPRUNT": TOKEN_EMPRUNT,
    "LOAN": TOKEN_EMPRUNT,
    "CADASTRE": TOKEN_CADASTRE,
    "ID": TOKEN_ID,
}
