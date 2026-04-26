"""ConfiDoc Backend — Document Classification Service."""

from app.core.logging import get_logger
from app.services.doc_metadata_service import classify_doc_category

logger = get_logger(__name__)

_CATEGORY_TO_DOC_TYPE: dict[str, str] = {
    "bilan": "accounting",
    "liasse_fiscale": "accounting",
    "grand_livre": "accounting",
    "releve_bancaire": "accounting",
    "facture": "invoice",
    "contrat": "legal",
    "autre": "generic",
}


def classify_document_type(text: str, filename: str = "") -> str:
    """Classify document to legacy 4-value type (invoice/accounting/legal/generic)."""
    category = classify_doc_category(text, filename)
    return _CATEGORY_TO_DOC_TYPE.get(category, "generic")
