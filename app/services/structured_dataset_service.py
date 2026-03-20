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
    return _clean_amount_candidate(_to_float_fr(_extract_first(pat, text)))


def _clean_amount_candidate(value: float | None) -> float | None:
    """Reject numeric noise for business amounts (years, form IDs, zip codes, compact dates)."""
    if value is None:
        return None
    iv = int(value)
    if abs(value - iv) < 1e-6:
        if 1900 <= iv <= 2100:  # likely year
            return None
        if iv == 2072:  # form number
            return None
        if 10000 <= iv <= 99999:  # likely zip code
            return None
    return value


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
    header_zone = _extract_2072_header_zone(text)
    results_zone = _extract_2072_results_zone(text)
    immeubles = _extract_2072_immeubles_table(text)
    associes = _extract_2072_associes_table(text)

    return {
        "denomination_sci": _field(_extract_first(r"(?:d[ée]nomination\s+de\s+la\s+soci[ée]t[ée]|d[ée]nomination\s+sci)\s*[:\-]?\s*([^\n]{3,120})", header_zone), 0.9, "header:denomination_societe"),
        "adresse_sci": _field(_extract_first(r"(?:adresse\s+de\s+la\s+soci[ée]t[ée])\s*[:\-]?\s*([^\n]{8,160})", header_zone), 0.86, "header:adresse_societe"),
        "adresse_siege_ouverture": _field(_extract_first(r"(?:adresse\s+du\s+si[eè]ge(?:\s+a\s+l[' ]ouverture)?)\s*[:\-]?\s*([^\n]{8,160})", header_zone), 0.78, "header:adresse_siege_ouverture"),
        "date_cloture_exercice": _field(_extract_first(r"(?:date\s+de\s+cl[ôo]ture(?:\s+de\s+l[' ]exercice)?)\s*[:\-]?\s*([0-3]?\d[\/\-][0-1]?\d[\/\-][12]\d{3})", header_zone), 0.92, "header:date_cloture_exercice"),
        "nombre_associes": _field(_to_float_fr(_extract_first(r"(?:nombre\s+d[' ]associ[ée]s?)\s*[:\-]?\s*([0-9]{1,3})", header_zone)), 0.88, "header:nombre_associes"),
        "nombre_parts_ouverture": _field(_to_float_fr(_extract_first(r"(?:nombre\s+de\s+parts?.{0,20}ouverture)\s*[:\-]?\s*([0-9]{1,10})", header_zone)), 0.78, "header:nombre_parts_ouverture"),
        "nombre_parts_cloture": _field(_to_float_fr(_extract_first(r"(?:nombre\s+de\s+parts?.{0,20}cl[ôo]ture)\s*[:\-]?\s*([0-9]{1,10})", header_zone)), 0.78, "header:nombre_parts_cloture"),
        "montant_nominal_parts": _field(_extract_amount_for_label(header_zone, r"montant\s+nominal\s+des?\s+parts?"), 0.76, "header:montant_nominal_parts"),
        "revenus_bruts": _field(_extract_amount_for_label(results_zone, r"revenus?\s+bruts?"), 0.9, "resultats:revenus_bruts"),
        "paiements_travaux": _field(_extract_amount_for_label(results_zone, r"paiements?\s+sur\s+travaux"), 0.84, "resultats:paiements_travaux"),
        "frais_charges_hors_interets": _field(_extract_amount_for_label(results_zone, r"frais?\s+et\s+charges?.{0,30}autres?.{0,30}int[eé]r"), 0.88, "resultats:frais_charges_hors_interets"),
        "interets_emprunts": _field(_extract_amount_for_label(results_zone, r"int[eé]r[eê]ts?\s+d[' ]emprunts?"), 0.88, "resultats:interets_emprunts"),
        "revenu_net_foncier": _field(_extract_amount_for_label(results_zone, r"revenu\s+net(?:\s+foncier)?|d[ée]ficit\s+net"), 0.9, "resultats:revenu_net_foncier"),
        "resultat_financier": _field(_extract_amount_for_label(results_zone, r"r[ée]sultat\s+financier"), 0.84, "resultats:resultat_financier"),
        "resultat_fiscal": _field(_extract_amount_for_label(results_zone, r"r[ée]sultat\s+fiscal"), 0.86, "resultats:resultat_fiscal"),
        "resultat_exploitation": _field(_extract_amount_for_label(results_zone, r"r[ée]sultat\s+d[' ]exploitation"), 0.84, "resultats:resultat_exploitation"),
        "resultat_exceptionnel": _field(_extract_amount_for_label(results_zone, r"r[ée]sultat\s+exceptionnel"), 0.82, "resultats:resultat_exceptionnel"),
        "montant_produits_financiers": _field(_extract_amount_for_label(results_zone, r"produits?\s+financiers"), 0.8, "resultats:montant_produits_financiers"),
        "montant_produits_exceptionnels": _field(_extract_amount_for_label(results_zone, r"produits?\s+exceptionnels"), 0.8, "resultats:montant_produits_exceptionnels"),
        "presence_annexes_immeubles": _field(len(immeubles) > 0 or bool(re.search(r"annexe\s*1|adresse\s+de\s+l[' ]immeuble", text, re.IGNORECASE)), 0.84, "annexe:immeubles"),
        "presence_annexes_associes_rf": _field(len(associes) > 0 or bool(re.search(r"annexe\s*2|quote[\- ]part", text, re.IGNORECASE)), 0.84, "annexe:associes_revenus_fonciers"),
    }


def _extract_2072_header_zone(text: str) -> str:
    lines = text.splitlines()
    start, end = 0, min(len(lines), 140)
    for i, line in enumerate(lines):
        low = line.lower()
        if "dénomination de la société".lower() in low or "denomination de la societe" in low:
            start = max(0, i - 5)
            break
    for j in range(start, min(len(lines), start + 220)):
        low = lines[j].lower()
        if "intérêts d'emprunt".lower() in low or "interets d'emprunt" in low:
            end = j
            break
    return "\n".join(lines[start:end])


def _extract_2072_results_zone(text: str) -> str:
    lines = text.splitlines()
    start, end = 0, len(lines)
    for i, line in enumerate(lines):
        low = line.lower()
        if "revenus bruts" in low or "intérêts d'emprunt".lower() in low or "interets d'emprunt" in low:
            start = max(0, i - 8)
            break
    for j in range(start, min(len(lines), start + 320)):
        low = lines[j].lower()
        if "annexe 1" in low or "adresse de l'immeuble" in low:
            end = j
            break
    return "\n".join(lines[start:end])


def _extract_2072_immeubles_table(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    start = -1
    for i, line in enumerate(lines):
        low = line.lower()
        if "annexe 1" in low or "adresse de l'immeuble" in low:
            start = i
            break
    if start < 0:
        return []
    end = min(len(lines), start + 260)
    for j in range(start + 1, min(len(lines), start + 360)):
        if "annexe 2" in lines[j].lower():
            end = j
            break
    zone_lines = lines[start:end]
    entries: list[dict[str, Any]] = []

    # Multi-immeubles: split by explicit "Annexe 1" markers or repeated "adresse de l'immeuble".
    chunk_starts: list[int] = []
    for idx, line in enumerate(zone_lines):
        low = line.lower()
        if "annexe 1" in low or "adresse de l'immeuble" in low:
            chunk_starts.append(idx)
    if not chunk_starts:
        chunk_starts = [0]
    chunk_starts = sorted(set(chunk_starts))
    chunk_starts.append(len(zone_lines))

    for i in range(len(chunk_starts) - 1):
        a, b = chunk_starts[i], chunk_starts[i + 1]
        if b - a < 2:
            continue
        chunk = "\n".join(zone_lines[a:b])
        entry = {
            "immeuble_id": f"IMMEUBLE_{len(entries) + 1}",
            "adresse_immeuble": _extract_first(r"(?:adresse\s+de\s+l[' ]immeuble)\s*[:\-]?\s*([^\n]{6,160})", chunk),
            "nombre_locaux": _to_float_fr(_extract_first(r"(?:nombre\s+de\s+locaux)\s*[:\-]?\s*([0-9]{1,4})", chunk)),
            "revenus_bruts": _extract_amount_for_label(chunk, r"montant\s+brut.{0,25}loyers?\s+encaiss|revenus?\s+bruts?"),
            "frais_gestion": _extract_amount_for_label(chunk, r"frais?\s+de\s+gestion"),
            "assurance": _extract_amount_for_label(chunk, r"primes?\s+d[' ]assurance|assurance"),
            "travaux": _extract_amount_for_label(chunk, r"travaux|d[ée]penses?\s+de\s+r[ée]paration"),
            "impositions": _extract_amount_for_label(chunk, r"impositions?"),
            "interets_emprunts": _extract_amount_for_label(chunk, r"int[eé]r[eê]ts?\s+des?\s+emprunts?"),
            "amortissement": _extract_amount_for_label(chunk, r"amortissement"),
            "revenu_ou_deficit": _extract_amount_for_label(chunk, r"revenu\s*\(\+\)|d[ée]ficit\s*\(\-\)|revenu\s+net"),
        }
        if any(v not in (None, "", 0.0) for k, v in entry.items() if k != "immeuble_id"):
            entries.append(entry)

    # Fallback: try to create entries from repeated addresses if chunk split failed.
    if not entries:
        zone = "\n".join(zone_lines)
        addrs = re.findall(r"(?:adresse\s+de\s+l[' ]immeuble)\s*[:\-]?\s*([^\n]{6,160})", zone, re.IGNORECASE)
        for idx, addr in enumerate(addrs[:10], start=1):
            entries.append(
                {
                    "immeuble_id": f"IMMEUBLE_{idx}",
                    "adresse_immeuble": _norm_spaces(addr),
                    "nombre_locaux": None,
                    "revenus_bruts": None,
                    "frais_gestion": None,
                    "assurance": None,
                    "travaux": None,
                    "impositions": None,
                    "interets_emprunts": None,
                    "amortissement": None,
                    "revenu_ou_deficit": None,
                }
            )

    return entries


def _extract_2072_associes_table(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    start = -1
    for i, line in enumerate(lines):
        low = line.lower()
        if "annexe 2" in low or "nom et prénom".lower() in low:
            start = i
            break
    if start < 0:
        return []
    zone_lines = lines[start:min(len(lines), start + 420)]
    zone = "\n".join(zone_lines)
    entries: list[dict[str, Any]] = []

    # Build associated chunks from repeated date-of-birth lines or "Nom et prénom" labels.
    starts: list[int] = []
    for idx, line in enumerate(zone_lines):
        low = line.lower()
        if "nom et prénom".lower() in low or "nom et prenom" in low or "date de naissance" in low:
            starts.append(idx)
    starts = sorted(set(starts))
    if not starts:
        starts = [0]
    starts.append(len(zone_lines))

    for i in range(len(starts) - 1):
        a, b = starts[i], starts[i + 1]
        if b - a < 2:
            continue
        chunk = "\n".join(zone_lines[a:b])
        entry = {
            "associe_id": f"ASSOCIE_{len(entries) + 1}",
            "nom": _extract_first(r"(?:nom\s+et\s+pr[ée]nom)\s*[:\-]?\s*([^\n]{3,120})", chunk),
            "date_naissance": _extract_first(r"(?:date\s+de\s+naissance)\s*[:\-]?\s*([0-3]?\d[\/\-][0-1]?\d[\/\-][12]\d{3})", chunk),
            "adresse": _extract_first(r"(?:adresse)\s*[:\-]?\s*([^\n]{8,140})", chunk),
            "parts_detenues": _to_float_fr(_extract_first(r"(?:parts?\s+d[ée]tenues?)\s*[:\-]?\s*([0-9]{1,10})", chunk)),
            "quote_part_revenus_bruts": _extract_amount_for_label(chunk, r"quote[\- ]part.{0,25}revenus?\s+bruts?"),
            "quote_part_frais_charges": _extract_amount_for_label(chunk, r"quote[\- ]part.{0,25}frais?.{0,25}charges?"),
            "quote_part_interets_emprunts": _extract_amount_for_label(chunk, r"quote[\- ]part.{0,25}int[eé]r[eê]ts?\s+d[' ]emprunts?"),
            "quote_part_amortissement": _extract_amount_for_label(chunk, r"quote[\- ]part.{0,25}amortissement"),
            "quote_part_revenu_net": _extract_amount_for_label(chunk, r"quote[\- ]part.{0,25}revenu\s+net|quote[\- ]part.{0,25}d[ée]ficit"),
        }
        if any(v not in (None, "", 0.0) for k, v in entry.items() if k != "associe_id"):
            entries.append(entry)

    # Fallback from global zone using repeated dates of birth patterns.
    if not entries:
        birth_dates = re.findall(r"\b([0-3]?\d[\/\-][0-1]?\d[\/\-][12]\d{3})\b", zone)
        for idx, dt in enumerate(birth_dates[:10], start=1):
            entries.append(
                {
                    "associe_id": f"ASSOCIE_{idx}",
                    "nom": None,
                    "date_naissance": dt,
                    "adresse": None,
                    "parts_detenues": None,
                    "quote_part_revenus_bruts": None,
                    "quote_part_frais_charges": None,
                    "quote_part_interets_emprunts": None,
                    "quote_part_amortissement": None,
                    "quote_part_revenu_net": None,
                }
            )

    return entries


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


def _quality_2072(fields: dict[str, dict[str, Any]], tables: dict[str, Any], text: str) -> dict[str, Any]:
    base = _quality(fields)
    critical = [
        "denomination_sci",
        "date_cloture_exercice",
        "nombre_associes",
        "revenus_bruts",
        "frais_charges_hors_interets",
        "interets_emprunts",
        "revenu_net_foncier",
    ]
    critical_missing = [k for k in critical if fields.get(k, {}).get("value") in (None, "", [])]

    zone_detection_score = 1.0 if fields.get("date_cloture_exercice", {}).get("value") else 0.7

    rb = fields.get("revenus_bruts", {}).get("value")
    pt = fields.get("paiements_travaux", {}).get("value") or 0.0
    fc = fields.get("frais_charges_hors_interets", {}).get("value") or 0.0
    ie = fields.get("interets_emprunts", {}).get("value") or 0.0
    rn = fields.get("revenu_net_foncier", {}).get("value")
    numeric_consistency_score = 0.6
    if isinstance(rb, (int, float)) and isinstance(rn, (int, float)):
        expected = rb - pt - fc - ie
        numeric_consistency_score = 1.0 if abs(expected - rn) <= 2 else 0.7

    ann1_declared = bool(re.search(r"annexe\s*1", text, re.IGNORECASE))
    ann2_declared = bool(re.search(r"annexe\s*2", text, re.IGNORECASE))
    ann1_ok = (not ann1_declared) or len(tables.get("immeubles", [])) >= 1
    ann2_ok = (not ann2_declared) or len(tables.get("associes_revenus_fonciers", [])) >= 1
    annex_consistency_score = 1.0 if (ann1_ok and ann2_ok) else 0.5

    # Aggregated consistency: sums of tables vs top-level totals.
    associes = tables.get("associes_revenus_fonciers", []) or []
    immeubles = tables.get("immeubles", []) or []
    associes_rb = sum(float(x.get("quote_part_revenus_bruts") or 0.0) for x in associes)
    associes_fc = sum(float(x.get("quote_part_frais_charges") or 0.0) for x in associes)
    associes_ie = sum(float(x.get("quote_part_interets_emprunts") or 0.0) for x in associes)
    immeubles_rb = sum(float(x.get("revenus_bruts") or 0.0) for x in immeubles)
    immeubles_fc = sum(float((x.get("frais_gestion") or 0.0) + (x.get("assurance") or 0.0) + (x.get("travaux") or 0.0) + (x.get("impositions") or 0.0)) for x in immeubles)
    immeubles_ie = sum(float(x.get("interets_emprunts") or 0.0) for x in immeubles)

    agg_checks = 0
    agg_ok = 0
    if isinstance(rb, (int, float)) and associes_rb > 0:
        agg_checks += 1
        if abs(rb - associes_rb) <= max(2.0, abs(rb) * 0.03):
            agg_ok += 1
    if isinstance(rb, (int, float)) and immeubles_rb > 0:
        agg_checks += 1
        if abs(rb - immeubles_rb) <= max(2.0, abs(rb) * 0.03):
            agg_ok += 1
    if isinstance(fc, (int, float)) and associes_fc > 0:
        agg_checks += 1
        if abs(fc - associes_fc) <= max(2.0, abs(fc) * 0.03):
            agg_ok += 1
    if isinstance(fc, (int, float)) and immeubles_fc > 0:
        agg_checks += 1
        if abs(fc - immeubles_fc) <= max(2.0, abs(fc) * 0.03):
            agg_ok += 1
    if isinstance(ie, (int, float)) and associes_ie > 0:
        agg_checks += 1
        if abs(ie - associes_ie) <= max(2.0, abs(ie) * 0.03):
            agg_ok += 1
    if isinstance(ie, (int, float)) and immeubles_ie > 0:
        agg_checks += 1
        if abs(ie - immeubles_ie) <= max(2.0, abs(ie) * 0.03):
            agg_ok += 1
    aggregate_consistency_score = (agg_ok / agg_checks) if agg_checks else 0.7

    consistency = (numeric_consistency_score + annex_consistency_score + aggregate_consistency_score) / 3
    ready_for_ai = (
        base["coverage_ratio"] >= 0.8
        and consistency >= 0.85
        and ann1_ok
        and ann2_ok
        and not critical_missing
    )
    needs_review = (not ready_for_ai) or base["needs_review"]
    flags = list(base.get("quality_flags", []))
    if critical_missing:
        flags.append("critical_fields_missing")
    if not ann1_ok or not ann2_ok:
        flags.append("annex_consistency_failed")
    if numeric_consistency_score < 0.85:
        flags.append("numeric_consistency_low")
    if aggregate_consistency_score < 0.85:
        flags.append("aggregate_consistency_low")

    return {
        **base,
        "zone_detection_score": round(zone_detection_score, 3),
        "numeric_consistency_score": round(numeric_consistency_score, 3),
        "annex_consistency_score": round(annex_consistency_score, 3),
        "aggregate_consistency_score": round(aggregate_consistency_score, 3),
        "ocr_readability_score": 0.75,
        "critical_missing_fields": critical_missing,
        "needs_review": needs_review,
        "ready_for_ai": ready_for_ai,
        "quality_flags": sorted(set(flags)),
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
        tables = {"accounting_lines": _extract_generic_accounting_table(anonymized_text)}
        quality = _quality(fields)
    elif doc_type == "compte_resultat":
        fields = _extract_compte_resultat(anonymized_text)
        tables = {"accounting_lines": _extract_generic_accounting_table(anonymized_text)}
        quality = _quality(fields)
    elif doc_type == "fiscal_2072":
        fields = _extract_2072(anonymized_text)
        tables = {
            "immeubles": _extract_2072_immeubles_table(anonymized_text),
            "associes_revenus_fonciers": _extract_2072_associes_table(anonymized_text),
        }
        quality = _quality_2072(fields, tables, anonymized_text)
    else:
        fields = _extract_common_fields(anonymized_text)
        tables = {"accounting_lines": _extract_generic_accounting_table(anonymized_text)}
        quality = _quality(fields)

    payload = {
        "doc_type": doc_type,
        "detected_doc_type": detected_doc_type,
        "anonymized": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fields": fields,
        "tables": tables,
        "quality": quality,
        "provenance": {
            "extractor_version": "v2-specialized",
            "strategy": "zone-based-specialized",
            "source_filename": original_filename,
        },
    }
    return payload

