"""ConfiDoc Backend — Document Classification Service."""

from app.core.logging import get_logger

logger = get_logger(__name__)

INVOICE_HINTS = (
    "facture",
    "invoice",
    "tva",
    "total ttc",
    "total ht",
    "montant ht",
    "règlement",
    "reglement",
    "avoir",
    "devis",
)

ACCOUNTING_HINTS = (
    "grand livre",
    "balance",
    "journal",
    "écriture",
    "ecriture",
    "compte de résultat",
    "bilan",
    "pcg",
    "plan comptable",
)

LEGAL_HINTS = (
    "contrat",
    "convention",
    "avenant",
    "clause",
    "article",
    "tribunal",
    "juridiction",
    "assignation",
    "jugement",
)


def classify_document_type(text: str, filename: str = "") -> str:
    """Heuristic document-type classification (v2)."""
    source = f"{filename}\n{text[:6000]}".lower()

    if any(hint in source for hint in INVOICE_HINTS):
        return "invoice"

    if any(h in source for h in ACCOUNTING_HINTS):
        return "accounting"

    if any(h in source for h in LEGAL_HINTS):
        return "legal"

    return "generic"
