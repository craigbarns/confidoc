"""ConfiDoc Backend — Business Pseudonymization Logic."""

import re
from typing import Any

from app.services.entity_registry import EntityRegistry


def infer_business_prefix(
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

    if entity_type == "invoice_identity_block":
        if any(k in value_excerpt.lower() for k in ("dirigeant", "contact", "gérant", "gerant")):
            return "PERSONNE"
        if "adresse" in value_excerpt.lower():
            return "ADRESSE"
        if any(k in value_excerpt.lower() for k in ("societe", "société", "entreprise")):
            return "SOCIETE"
        return "SOCIETE"

    if entity_type in {"company_legal_name", "company_legal_suffix"}:
        if "fournisseur" in ctx:
            return "FOURNISSEUR"
        if "client" in ctx:
            return "CLIENT"
        return "SOCIETE"

    if entity_type in {"address_line", "address_residence"}:
        if any(
            k in ctx
            for k in (
                "loyer",
                "immeuble",
                "bien",
                "locatif",
                "locat",
                "residence",
                "résidence",
                "batiment",
                "bâtiment",
            )
        ):
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


def apply_business_pseudonyms(
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
        prefix = infer_business_prefix(
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
