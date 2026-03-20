"""ConfiDoc Backend — Structured datasets by document type (V1)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def detect_specialized_doc_type(text: str, filename: str = "") -> str:
    """Detect specialized accounting/tax document type (heuristic V1)."""
    source = f"{filename}\n{text[:20000]}".lower()

    if any(k in source for k in ("2072", "sci", "revenus fonciers", "quote-part", "associé")):
        return "fiscal_2072"
    if any(k in source for k in ("2044", "revenu foncier", "déficit foncier", "deficit foncier")):
        return "fiscal_2044"
    if any(k in source for k in ("compte de résultat", "compte de resultat", "résultat d'exploitation", "resultat net")):
        return "compte_resultat"
    if any(k in source for k in ("bilan", "total actif", "total passif", "capitaux propres")):
        return "bilan"
    if any(k in source for k in ("relevé bancaire", "releve bancaire", "iban", "solde", "virement")):
        return "releve_bancaire"
    if any(k in source for k in ("facture", "tva", "ht", "ttc")):
        return "facture"
    return "autre"


def _norm_spaces(v: str) -> str:
    return re.sub(r"\s+", " ", (v or "")).strip()


def _to_float_fr(num_text: str | None) -> float | None:
    if not num_text:
        return None
    raw = num_text.replace("\u00a0", " ")
    raw = raw.replace("€", "").replace("eur", "").replace("EUR", "")
    raw = raw.strip()
    raw = re.sub(r"[ ]+", "", raw)
    raw = raw.replace(",", ".")
    raw = re.sub(r"[^0-9.\-]", "", raw)
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _extract_first(pattern: str, text: str, flags: int = re.IGNORECASE) -> str | None:
    m = re.search(pattern, text, flags)
    if not m:
        return None
    if m.lastindex:
        return _norm_spaces(m.group(1))
    return _norm_spaces(m.group(0))


def _extract_amount_for_label(text: str, label_regex: str) -> float | None:
    pat = rf"{label_regex}[^0-9\-]{{0,40}}([0-9][0-9\s\u00a0.,]{{0,30}})"
    return _to_float_fr(_extract_first(pat, text))


@dataclass
class ExtractedField:
    value: Any
    confidence: float
    source_hint: str
    review_required: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "confidence": round(float(self.confidence), 3),
            "source_hint": self.source_hint,
            "review_required": bool(self.review_required),
        }


def _field(value: Any, confidence: float, source_hint: str) -> dict[str, Any]:
    return ExtractedField(
        value=value,
        confidence=confidence,
        source_hint=source_hint,
        review_required=value in (None, "", []),
    ).as_dict()


def _extract_common_fields(text: str) -> dict[str, dict[str, Any]]:
    exercice = _extract_first(r"(?:exercice|exercice clos le)\s*[:\-]?\s*([0-9]{4})", text)
    date_cloture = _extract_first(
        r"(?:clos le|clôture|date de clôture)\s*[:\-]?\s*([0-3]?\d[\/\-][0-1]?\d[\/\-][12]\d{3})",
        text,
    )
    societe = _extract_first(
        r"(?:dénomination|denomination|raison sociale|société|societe)\s*[:\-]?\s*([A-Z0-9 _.\-]{3,80})",
        text,
    )
    return {
        "societe": _field(societe, 0.75 if societe else 0.0, "header:societe"),
        "exercice": _field(exercice, 0.8 if exercice else 0.0, "header:exercice"),
        "date_cloture": _field(date_cloture, 0.82 if date_cloture else 0.0, "header:date_cloture"),
    }


def _extract_bilan(text: str) -> dict[str, dict[str, Any]]:
    return {
        **_extract_common_fields(text),
        "total_actif": _field(_extract_amount_for_label(text, r"total\s+actif"), 0.87, "label:total actif"),
        "total_passif": _field(_extract_amount_for_label(text, r"total\s+passif"), 0.87, "label:total passif"),
        "immobilisations": _field(_extract_amount_for_label(text, r"immobilisations"), 0.78, "label:immobilisations"),
        "creances": _field(_extract_amount_for_label(text, r"créances|creances"), 0.78, "label:creances"),
        "disponibilites": _field(_extract_amount_for_label(text, r"disponibilités|disponibilites"), 0.78, "label:disponibilites"),
        "dettes_financieres": _field(_extract_amount_for_label(text, r"dettes?\s+financi"), 0.76, "label:dettes financieres"),
        "dettes_fournisseurs": _field(_extract_amount_for_label(text, r"dettes?\s+fournisseurs?"), 0.76, "label:dettes fournisseurs"),
        "capitaux_propres": _field(_extract_amount_for_label(text, r"capitaux?\s+propres"), 0.8, "label:capitaux propres"),
        "resultat_exercice": _field(_extract_amount_for_label(text, r"résultat\s+de?\s+l[' ]?exercice|resultat\s+de?\s+l[' ]?exercice"), 0.8, "label:resultat exercice"),
    }


def _extract_compte_resultat(text: str) -> dict[str, dict[str, Any]]:
    return {
        **_extract_common_fields(text),
        "chiffre_affaires": _field(_extract_amount_for_label(text, r"chiffre\s+d[' ]affaires"), 0.86, "label:chiffre affaires"),
        "autres_produits": _field(_extract_amount_for_label(text, r"autres?\s+produits"), 0.76, "label:autres produits"),
        "charges_externes": _field(_extract_amount_for_label(text, r"charges?\s+externes"), 0.76, "label:charges externes"),
        "impots_taxes": _field(_extract_amount_for_label(text, r"imp[oô]ts?\s+et\s+taxes"), 0.76, "label:impots taxes"),
        "charges_financieres": _field(_extract_amount_for_label(text, r"charges?\s+financi"), 0.76, "label:charges financieres"),
        "resultat_exploitation": _field(_extract_amount_for_label(text, r"résultat\s+d[' ]exploitation|resultat\s+d[' ]exploitation"), 0.82, "label:resultat exploitation"),
        "resultat_courant": _field(_extract_amount_for_label(text, r"résultat\s+courant|resultat\s+courant"), 0.8, "label:resultat courant"),
        "resultat_net": _field(_extract_amount_for_label(text, r"résultat\s+net|resultat\s+net"), 0.84, "label:resultat net"),
    }


def _extract_2072(text: str) -> dict[str, dict[str, Any]]:
    return {
        **_extract_common_fields(text),
        "denomination_sci": _field(_extract_first(r"(?:dénomination|denomination)\s+sci\s*[:\-]?\s*([A-Z0-9 _.\-]{3,80})", text), 0.82, "header:denomination sci"),
        "nombre_associes": _field(_to_float_fr(_extract_first(r"(?:nombre d[' ]associés|nombre d[' ]associes)\s*[:\-]?\s*([0-9]{1,3})", text)), 0.8, "header:nombre associes"),
        "adresse_immeuble": _field(_extract_first(r"(?:adresse\s+immeuble|adresse du bien)\s*[:\-]?\s*([^\n]{8,120})", text), 0.74, "header:adresse immeuble"),
        "revenus_bruts": _field(_extract_amount_for_label(text, r"revenus?\s+bruts?"), 0.82, "label:revenus bruts"),
        "interets_emprunt": _field(_extract_amount_for_label(text, r"int[eé]r[eê]ts?\s+d[' ]emprunt"), 0.8, "label:interets emprunt"),
        "frais_charges": _field(_extract_amount_for_label(text, r"frais?\s+et\s+charges?"), 0.78, "label:frais et charges"),
        "amortissement": _field(_extract_amount_for_label(text, r"amortissement"), 0.74, "label:amortissement"),
        "revenu_net_foncier": _field(_extract_amount_for_label(text, r"revenu\s+net\s+foncier"), 0.84, "label:revenu net foncier"),
        "resultat_fiscal": _field(_extract_amount_for_label(text, r"résultat\s+fiscal|resultat\s+fiscal"), 0.82, "label:resultat fiscal"),
        "quote_part_associe": _field(_extract_amount_for_label(text, r"quote[\- ]part"), 0.72, "label:quote-part"),
        "gerant": _field(_extract_first(r"(?:g[ée]rant)\s*[:\-]?\s*([A-Z][^\n]{2,60})", text), 0.72, "header:gerant"),
        "co_gerant": _field(_extract_first(r"(?:co[\- ]g[ée]rant)\s*[:\-]?\s*([A-Z][^\n]{2,60})", text), 0.68, "header:co-gerant"),
        "presence_annexes": _field(bool(re.search(r"\bannexe(s)?\b", text, re.IGNORECASE)), 0.7, "keyword:annexes"),
    }


def _extract_generic_accounting_table(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        code_match = re.search(r"^\s*(\d{3,8})\b", line)
        if not code_match:
            continue
        amount_match = re.search(r"([0-9][0-9\s\u00a0.,]{1,30}(?:€|EUR)?)\s*$", line, re.IGNORECASE)
        records.append(
            {
                "code": code_match.group(1),
                "label": _norm_spaces(re.sub(r"^\s*\d{3,8}\s*", "", line)),
                "amount": _to_float_fr(amount_match.group(1) if amount_match else None),
            }
        )
    return records[:500]


def _quality(fields: dict[str, dict[str, Any]]) -> dict[str, Any]:
    total = len(fields)
    filled = sum(1 for f in fields.values() if f.get("value") not in (None, "", []))
    coverage = (filled / total) if total else 0.0
    needs_review = coverage < 0.7
    flags: list[str] = []
    if coverage < 0.5:
        flags.append("low_field_coverage")
    if coverage < 0.7:
        flags.append("manual_review_recommended")
    return {
        "coverage_ratio": round(coverage, 3),
        "filled_fields": int(filled),
        "total_fields": int(total),
        "needs_review": needs_review,
        "quality_flags": flags,
    }


def build_structured_dataset(
    anonymized_text: str,
    original_filename: str = "",
    requested_doc_type: str = "auto",
) -> dict[str, Any]:
    """Build normalized structured dataset payload for downstream analytics/AI."""
    detected_doc_type = detect_specialized_doc_type(anonymized_text, original_filename)
    doc_type = detected_doc_type if requested_doc_type in ("", "auto") else requested_doc_type

    if doc_type == "bilan":
        fields = _extract_bilan(anonymized_text)
    elif doc_type == "compte_resultat":
        fields = _extract_compte_resultat(anonymized_text)
    elif doc_type == "fiscal_2072":
        fields = _extract_2072(anonymized_text)
    else:
        fields = _extract_common_fields(anonymized_text)

    payload = {
        "doc_type": doc_type,
        "detected_doc_type": detected_doc_type,
        "anonymized": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fields": fields,
        "tables": {
            "accounting_lines": _extract_generic_accounting_table(anonymized_text),
        },
        "quality": _quality(fields),
        "provenance": {
            "extractor_version": "v1-specialized",
            "strategy": "heuristic-specialized",
            "source_filename": original_filename,
        },
    }
    return payload

