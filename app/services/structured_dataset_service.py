"""ConfiDoc Backend — Structured datasets by document type (V1)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.services.quality_experience import build_quality_experience


def _contains_any(source: str, keywords: tuple[str, ...]) -> bool:
    return any(k in source for k in keywords)


def _score_hits(source: str, keywords: tuple[str, ...]) -> tuple[int, list[str]]:
    hits = [k for k in keywords if k in source]
    return len(hits), hits


def classify_doc_type_scored(
    text: str, filename: str = ""
) -> tuple[str, float, list[str], dict[str, Any]]:
    """Scored router for a compact high-confidence taxonomy."""
    source = f"{filename}\n{text[:20000]}".lower()

    rules: list[tuple[str, tuple[str, ...], int]] = [
        ("liasse_is_simplifiee", (
            "2065", "2065-sd", "2033-a", "2033-b",
            "bilan simplifié", "bilan simplifie",
            "compte de résultat simplifié", "compte de resultat simplifie",
            "régime simplifié d'imposition", "regime simplifie d'imposition",
        ), 3),
        ("fiscal_2072", (
            "2072", "2072-an1", "2072-an2", "revenus fonciers",
            "associés revenus fonciers", "associes revenus fonciers",
        ), 2),
        ("fiscal_2044", ("2044", "revenu foncier", "déficit foncier", "deficit foncier"), 2),
        ("bilan", ("bilan", "total actif", "total passif", "capitaux propres"), 2),
        ("compte_resultat", ("compte de résultat", "compte de resultat", "résultat net", "resultat net"), 2),
        ("releve_bancaire", ("relevé bancaire", "releve bancaire", "iban", "solde", "virement"), 2),
        ("facture_fournisseur", ("facture fournisseur", "facture", "tva", "ht", "ttc"), 2),
    ]

    best_type = "unknown_other"
    best_score = 0
    best_hits: list[str] = []
    second_type = "unknown_other"
    second_score = 0
    for doc_type, keywords, threshold in rules:
        score, hits = _score_hits(source, keywords)
        if score >= threshold and score > best_score:
            second_type, second_score = best_type, best_score
            best_type = doc_type
            best_score = score
            best_hits = hits
        elif score >= threshold and score > second_score:
            second_type, second_score = doc_type, score

    if best_type.startswith("unknown_"):
        # coarse unknown buckets for safer downstream routing
        if any(k in source for k in ("fiscal", "liasse", "impot", "tva", "2065", "2033", "2044", "2072")):
            best_type = "unknown_tax"
        elif any(k in source for k in ("bilan", "compte", "journal", "écriture", "ecriture", "pcg")):
            best_type = "unknown_accounting"
        else:
            best_type = "unknown_other"

    confidence = min(0.99, 0.45 + (best_score * 0.15)) if not best_type.startswith("unknown_") else 0.35
    reasons = [f"match:{h}" for h in best_hits][:10]
    if not reasons:
        reasons = ["no_strong_marker_match"]
    runner_up = {
        "doc_type": second_type,
        "score": int(second_score),
    }
    return best_type, round(confidence, 3), reasons, runner_up


def detect_specialized_doc_type(text: str, filename: str = "") -> str:
    """Backward-compatible wrapper returning doc_type only."""
    doc_type, _confidence, _reasons, _runner_up = classify_doc_type_scored(text, filename)
    return doc_type


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


def _extract_financial_amount_for_label(text: str, label_regex: str, min_amount: float = 100.0) -> float | None:
    """Financial amount extractor with plausibility threshold (avoid index-like numbers)."""
    value = _extract_amount_for_label(text, label_regex)
    if value is None:
        return None
    return value if abs(value) >= min_amount else None


def _extract_first_amount_from_patterns(text: str, patterns: list[str], min_amount: float = 100.0) -> float | None:
    for pat in patterns:
        val = _extract_financial_amount_for_label(text, pat, min_amount=min_amount)
        if val is not None:
            return val
    return None


def _extract_first_amount_with_source(
    text: str, patterns: list[tuple[str, str]], min_amount: float = 100.0
) -> tuple[float | None, str]:
    for source_hint, pat in patterns:
        val = _extract_financial_amount_for_label(text, pat, min_amount=min_amount)
        if val is not None:
            return val, source_hint
    return None, "missing"


def _extract_amount_from_lines_with_keyword(
    text: str, keyword_regex: str, min_amount: float = 100.0
) -> tuple[float | None, str]:
    pat_kw = re.compile(keyword_regex, re.IGNORECASE)
    for raw in text.splitlines():
        line = raw.strip()
        if not line or not pat_kw.search(line):
            continue
        m = re.search(r"([0-9][0-9\s\u00a0.,]{0,30})\s*$", line)
        if not m:
            continue
        v = _clean_amount_candidate(_to_float_fr(m.group(1)))
        if isinstance(v, float) and abs(v) >= min_amount:
            return v, "fallback:line_keyword"
    return None, "missing"


def _extract_financial_amount_for_label_wide(
    text: str, label_regex: str, *, max_gap: int = 120, min_amount: float = 100.0
) -> float | None:
    """Like _extract_financial_amount_for_label but allows a wider gap (multi-column OCR layouts)."""
    pat = rf"{label_regex}[^0-9\-]{{0,{max_gap}}}([0-9][0-9\s\u00a0.,]{{0,30}})"
    value = _clean_amount_candidate(_to_float_fr(_extract_first(pat, text)))
    if value is None:
        return None
    return value if abs(value) >= min_amount else None


def _extract_amount_after_keyword_multiline(
    text: str, keyword_regex: str, min_amount: float = 50.0, max_lookahead_lines: int = 3
) -> tuple[float | None, str]:
    """Find keyword on a line; take amount at end of that line or the next non-empty lines."""
    lines = text.splitlines()
    pat_kw = re.compile(keyword_regex, re.IGNORECASE)
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line or not pat_kw.search(line):
            continue
        for j in range(0, max_lookahead_lines + 1):
            idx = i + j
            if idx >= len(lines):
                break
            scan = lines[idx].strip()
            if not scan:
                continue
            # Prefer last number on the line (typical table: label ... amount).
            candidates: list[float] = []
            for m in re.finditer(r"([0-9][0-9\s\u00a0.,]{0,30})(?:\s*$|\s*€|\s*EUR)?", scan, re.IGNORECASE):
                v = _clean_amount_candidate(_to_float_fr(m.group(1)))
                if isinstance(v, float) and abs(v) >= min_amount:
                    candidates.append(v)
            if candidates:
                v = candidates[-1]
                src = "fallback:multiline_after_keyword" if j > 0 else "fallback:line_after_keyword"
                return v, src
    return None, "missing"


def _plausible_2072_interets_candidate(value: float, revenus_bruts: float | None) -> bool:
    if abs(value) < 50.0:
        return False
    if revenus_bruts is not None and isinstance(revenus_bruts, (int, float)):
        rb = abs(float(revenus_bruts))
        if rb > 0 and abs(value) > max(rb * 2.0, 5_000_000.0):
            return False
    elif abs(value) > 5_000_000.0:
        return False
    return True


def _sum_accounting_lines_by_prefixes(
    text: str, prefixes: tuple[str, ...], min_total: float = 100.0
) -> tuple[float | None, str]:
    records = _extract_generic_accounting_table(text)
    vals = [
        float(r.get("amount"))
        for r in records
        if isinstance(r.get("amount"), (int, float))
        and str(r.get("code", "")).startswith(prefixes)
        and abs(float(r.get("amount"))) >= 1.0
    ]
    if len(vals) < 2:
        return None, "missing"
    total = sum(vals)
    if abs(total) < min_total:
        return None, "missing"
    return total, "fallback:accounting_prefix_sum"


def _sum_accounting_lines_single_prefix(
    text: str, prefix: str, *, min_total: float = 100.0, min_lines: int = 1
) -> tuple[float | None, str]:
    """Sum PCG lines whose code starts with prefix (e.g. '62' for charges externes)."""
    records = _extract_generic_accounting_table(text)
    vals = [
        float(r.get("amount"))
        for r in records
        if isinstance(r.get("amount"), (int, float))
        and str(r.get("code", "")).startswith(prefix)
        and abs(float(r.get("amount"))) >= 1.0
    ]
    if len(vals) < min_lines:
        return None, "missing"
    total = sum(vals)
    if abs(total) < min_total:
        return None, "missing"
    return total, f"fallback:accounting_prefix_{prefix}_sum"


def _sum_fr_capital_account_lines(text: str) -> tuple[float | None, str]:
    """Sum typical PCG classe-1 capital / réserves lines when present as coded rows."""
    records = _extract_generic_accounting_table(text)
    prefixes = (
        "101",
        "102",
        "104",
        "105",
        "106",
        "107",
        "108",
        "109",
        "110",
        "111",
        "112",
        "118",
        "119",
    )
    vals: list[float] = []
    for r in records:
        c = str(r.get("code", ""))
        if not c or len(c) < 3:
            continue
        if not any(c.startswith(p) for p in prefixes):
            continue
        amt = r.get("amount")
        if not isinstance(amt, (int, float)):
            continue
        vals.append(float(amt))
    if len(vals) < 2:
        return None, "missing"
    total = sum(vals)
    if abs(total) < 100.0:
        return None, "missing"
    return total, "fallback:pcg_capital_lines_sum"


def _extract_first_date_from_patterns(text: str, patterns: list[str]) -> str | None:
    for pat in patterns:
        v = _extract_first(pat, text)
        if v:
            return v
    return None


def _extract_first_int_from_patterns(text: str, patterns: list[str]) -> float | None:
    for pat in patterns:
        v = _extract_first(pat, text)
        if not v:
            continue
        n = _to_float_fr(v)
        if n is not None and 1 <= n <= 200:
            return n
    return None


def _clean_amount_candidate(value: float | None) -> float | None:
    """Reject numeric noise for business amounts (years, form IDs, zip codes, compact dates)."""
    if value is None:
        return None
    iv = int(value)
    if abs(value - iv) < 1e-6:
        if 0 <= iv <= 50:  # likely line index / small marker, not a financial amount
            return None
        if 1900 <= iv <= 2100:  # likely year
            return None
        if iv == 2072:  # form number
            return None
    return value


FORM_LABEL_BLACKLIST = {
    "adresse de la société",
    "adresse de la societe",
    "adresse du siège social",
    "adresse du siege social",
    "dénomination de la société",
    "denomination de la societe",
    "nom marital",
    "au cours de",
    "date de naissance",
    "nom et prénom",
    "nom et prenom",
    "soc5",
    "soc18",
}


def _looks_like_form_label(value: str | None) -> bool:
    if not value:
        return True
    v = _norm_spaces(value).lower()
    if len(v) < 2:
        return True
    if any(lbl in v for lbl in FORM_LABEL_BLACKLIST):
        return True
    # Reject obvious header-only fragments with almost no value signal
    if re.search(r"\b(adresse|dénomination|denomination|nom|date|associ[ée]s?)\b", v) and not re.search(r"\d|_|[a-z]{3,}", v):
        return True
    return False


def _clean_text_candidate(value: str | None) -> str | None:
    if value is None:
        return None
    v = _norm_spaces(value)
    if _looks_like_form_label(v):
        return None
    return v


def _extract_value_near_label(
    text: str,
    label_regex: str,
    value_regex: str,
    *,
    max_next_lines: int = 2,
    flags: int = re.IGNORECASE,
) -> str | None:
    """Extract value near label while avoiding re-capturing the label itself."""
    lines = text.splitlines()
    label_re = re.compile(label_regex, flags)
    value_re = re.compile(value_regex, flags)

    for i, line in enumerate(lines):
        if not label_re.search(line):
            continue
        # 1) same line after label
        tail = label_re.sub("", line, count=1)
        m_same = value_re.search(tail)
        if m_same:
            val = _clean_text_candidate(m_same.group(1) if m_same.lastindex else m_same.group(0))
            if val:
                return val
        # 2) next lines close to label
        for j in range(1, max_next_lines + 1):
            if i + j >= len(lines):
                break
            m_next = value_re.search(lines[i + j])
            if not m_next:
                continue
            val = _clean_text_candidate(m_next.group(1) if m_next.lastindex else m_next.group(0))
            if val:
                return val
    return None


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


@dataclass
class StructuredExtractionResult:
    fields: dict[str, dict[str, Any]]
    tables: dict[str, Any]
    quality: dict[str, Any]
    extractor_name: str


def _field(value: Any, confidence: float, source_hint: str) -> dict[str, Any]:
    is_missing = value in (None, "", [])
    return ExtractedField(
        value=value,
        confidence=0.0 if is_missing else confidence,
        source_hint=source_hint,
        review_required=is_missing,
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
    total_actif, total_actif_src = _extract_first_amount_with_source(
        text,
        [
            ("label:total_actif", r"total\s+actif"),
            ("label:total_general_actif", r"total\s+g[ée]n[ée]ral.{0,12}actif"),
            ("label:total_i_actif", r"total\s+i.{0,15}actif"),
        ],
        min_amount=100.0,
    )
    if total_actif is None:
        total_actif, total_actif_src = _extract_amount_from_lines_with_keyword(
            "\n".join(text.splitlines()[-260:]), r"total.{0,12}actif", min_amount=100.0
        )

    total_passif, total_passif_src = _extract_first_amount_with_source(
        text,
        [
            ("label:total_passif", r"total\s+passif"),
            ("label:total_general_passif", r"total\s+g[ée]n[ée]ral.{0,12}passif"),
            ("label:total_i_passif", r"total\s+i.{0,15}passif"),
        ],
        min_amount=100.0,
    )
    if total_passif is None:
        total_passif, total_passif_src = _extract_amount_from_lines_with_keyword(
            "\n".join(text.splitlines()[-260:]), r"total.{0,12}passif", min_amount=100.0
        )

    capitaux_propres, capitaux_propres_src = _extract_first_amount_with_source(
        text,
        [
            ("label:capitaux_propres", r"capitaux?\s+propres"),
            ("label:capitaux_propres_ensemble", r"total.{0,20}capitaux?\s+propres"),
            ("label:fonds_propres", r"fonds?\s+propres"),
            ("label:ressources_propres", r"ressources?\s+propres"),
            ("label:capitaux_assimiles", r"capitaux?\s+propres\s+et\s+assimil"),
            ("label:total_capitaux", r"total\s+i.{0,18}capitaux"),
        ],
        min_amount=100.0,
    )
    if capitaux_propres is None:
        for src_hint, pat in [
            ("label_wide:capitaux_propres", r"capitaux?\s+propres"),
            ("label_wide:fonds_propres", r"fonds?\s+propres"),
        ]:
            w = _extract_financial_amount_for_label_wide(text, pat, max_gap=140, min_amount=100.0)
            if w is not None:
                capitaux_propres, capitaux_propres_src = w, src_hint
                break
    if capitaux_propres is None:
        capitaux_propres, capitaux_propres_src = _extract_amount_after_keyword_multiline(
            "\n".join(text.splitlines()[-320:]),
            r"capitaux.{0,12}propres|fonds.{0,12}propres|ressources.{0,12}propres",
            min_amount=100.0,
        )
    if capitaux_propres is None:
        capitaux_propres, capitaux_propres_src = _extract_first_amount_with_source(
            text,
            [
                ("label:situation_nette", r"situation\s+nette"),
                ("label:net_comptable", r"net\s+comptable"),
                ("label:total_fonds_propres", r"total.{0,18}fonds?\s+propres"),
                ("label:capitaux_detenus", r"capitaux?\s+d[ée]tenus"),
            ],
            min_amount=100.0,
        )
    if capitaux_propres is None:
        for src_hint, pat in [
            ("label_wide:situation_nette", r"situation\s+nette"),
            ("label_wide:net_comptable", r"net\s+comptable"),
        ]:
            w = _extract_financial_amount_for_label_wide(text, pat, max_gap=160, min_amount=100.0)
            if w is not None:
                capitaux_propres, capitaux_propres_src = w, src_hint
                break

    dettes_fin_val = _extract_financial_amount_for_label(text, r"dettes?\s+financi", min_amount=50.0)
    dettes_four_val = _extract_financial_amount_for_label(text, r"dettes?\s+fournisseurs?", min_amount=50.0)
    # Conservative: small plaquettes sometimes list only equity + two debt lines under passif.
    if capitaux_propres is None and isinstance(total_passif, (int, float)):
        if dettes_fin_val is not None and dettes_four_val is not None:
            cand = float(total_passif) - float(dettes_fin_val) - float(dettes_four_val)
            s = float(dettes_fin_val) + float(dettes_four_val) + cand
            if (
                cand >= 100.0
                and abs(s - float(total_passif)) <= max(500.0, abs(float(total_passif)) * 0.04)
            ):
                capitaux_propres = cand
                capitaux_propres_src = "fallback:passif_minus_dettes_fin_et_fournisseurs"

    if capitaux_propres is None:
        capitaux_propres, capitaux_propres_src = _sum_fr_capital_account_lines(text)

    resultat_exercice, resultat_exercice_src = _extract_first_amount_with_source(
        text,
        [
            ("label:resultat_exercice", r"r[ée]sultat\s+de?\s+l[' ]?exercice"),
            ("label:benefice_perte", r"b[ée]n[ée]fice|perte\s+de\s+l[' ]?exercice"),
        ],
        min_amount=50.0,
    )

    return {
        **_extract_common_fields(text),
        "total_actif": _field(total_actif, 0.87 if total_actif is not None else 0.0, total_actif_src),
        "total_passif": _field(total_passif, 0.87 if total_passif is not None else 0.0, total_passif_src),
        "immobilisations": _field(_extract_amount_for_label(text, r"immobilisations"), 0.78, "label:immobilisations"),
        "creances": _field(_extract_amount_for_label(text, r"créances|creances"), 0.78, "label:creances"),
        "disponibilites": _field(_extract_amount_for_label(text, r"disponibilités|disponibilites"), 0.78, "label:disponibilites"),
        "dettes_financieres": _field(_extract_amount_for_label(text, r"dettes?\s+financi"), 0.76, "label:dettes financieres"),
        "dettes_fournisseurs": _field(_extract_amount_for_label(text, r"dettes?\s+fournisseurs?"), 0.76, "label:dettes fournisseurs"),
        "capitaux_propres": _field(
            capitaux_propres, 0.8 if capitaux_propres is not None else 0.0, capitaux_propres_src
        ),
        "resultat_exercice": _field(
            resultat_exercice, 0.8 if resultat_exercice is not None else 0.0, resultat_exercice_src
        ),
    }


def _extract_compte_resultat(text: str) -> dict[str, dict[str, Any]]:
    scan_cr = text
    charges_externes, charges_externes_src = _extract_first_amount_with_source(
        scan_cr,
        [
            ("label:charges_externes", r"charges?\s+externes"),
            ("label:total_charges_externes", r"total.{0,15}charges?.{0,12}externes"),
            ("label:autres_charges_externes", r"autres?.{0,10}charges?.{0,10}externes"),
            ("label:services_exterieurs", r"services?\s+ext[ée]rieurs"),
        ],
        min_amount=50.0,
    )
    if charges_externes is None:
        for src_hint, pat in [
            ("label_wide:charges_externes", r"charges?\s+externes"),
            ("label_wide:services_exterieurs", r"services?\s+ext[ée]rieurs"),
        ]:
            w = _extract_financial_amount_for_label_wide(scan_cr, pat, max_gap=140, min_amount=50.0)
            if w is not None:
                charges_externes, charges_externes_src = w, src_hint
                break
    if charges_externes is None:
        charges_externes, charges_externes_src = _extract_amount_after_keyword_multiline(
            scan_cr,
            r"charges?.{0,12}externes|services?.{0,12}ext[ée]rieurs",
            min_amount=50.0,
        )
    if charges_externes is None:
        charges_externes, charges_externes_src = _sum_accounting_lines_by_prefixes(
            scan_cr, ("61", "62"), min_total=100.0
        )
    if charges_externes is None:
        charges_externes, charges_externes_src = _sum_accounting_lines_single_prefix(
            scan_cr, "62", min_total=100.0, min_lines=2
        )
    if charges_externes is None:
        charges_externes, charges_externes_src = _sum_accounting_lines_single_prefix(
            scan_cr, "62", min_total=500.0, min_lines=1
        )

    resultat_exploitation, resultat_exploitation_src = _extract_first_amount_with_source(
        text,
        [
            ("label:resultat_exploitation", r"r[ée]sultat\s+d[' ]exploitation"),
            ("label:resultat_exploitation_alt", r"r[ée]sultat\s+exploitation"),
        ],
        min_amount=50.0,
    )
    if resultat_exploitation is None:
        resultat_exploitation, resultat_exploitation_src = _extract_amount_from_lines_with_keyword(
            text, r"r[ée]sultat.{0,12}exploitation", min_amount=50.0
        )

    resultat_courant, resultat_courant_src = _extract_first_amount_with_source(
        text,
        [
            ("label:resultat_courant", r"r[ée]sultat\s+courant"),
            ("label:rcai", r"r[ée]sultat\s+courant\s+avant\s+imp[oô]ts|rcai"),
        ],
        min_amount=50.0,
    )
    if resultat_courant is None:
        resultat_courant, resultat_courant_src = _extract_amount_from_lines_with_keyword(
            text, r"r[ée]sultat.{0,12}courant", min_amount=50.0
        )

    resultat_net, resultat_net_src = _extract_first_amount_with_source(
        scan_cr,
        [
            ("label:resultat_net", r"r[ée]sultat\s+net(?:\s+de\s+l[' ]?exercice)?"),
            ("label:resultat_net_apres_impots", r"r[ée]sultat\s+net.{0,20}imp[oô]ts?"),
            ("label:benefice_perte", r"b[ée]n[ée]fice|perte\s+de\s+l[' ]?exercice"),
        ],
        min_amount=50.0,
    )
    if resultat_net is None:
        for src_hint, pat in [
            ("label_wide:resultat_net", r"r[ée]sultat\s+net"),
            ("label_wide:resultat_exercice", r"r[ée]sultat\s+de\s+l[' ]?exercice"),
        ]:
            w = _extract_financial_amount_for_label_wide(scan_cr, pat, max_gap=160, min_amount=50.0)
            if w is not None:
                resultat_net, resultat_net_src = w, src_hint
                break
    if resultat_net is None:
        resultat_net, resultat_net_src = _extract_amount_from_lines_with_keyword(
            scan_cr, r"r[ée]sultat.{0,12}net", min_amount=50.0
        )
    if resultat_net is None:
        resultat_net, resultat_net_src = _extract_amount_after_keyword_multiline(
            scan_cr,
            r"r[ée]sultat\s+net|r[ée]sultat\s+de\s+l[' ]?exercice|b[ée]n[ée]fice\s+net",
            min_amount=50.0,
        )

    return {
        **_extract_common_fields(text),
        "chiffre_affaires": _field(_extract_amount_for_label(text, r"chiffre\s+d[' ]affaires"), 0.86, "label:chiffre affaires"),
        "autres_produits": _field(_extract_amount_for_label(text, r"autres?\s+produits"), 0.76, "label:autres produits"),
        "charges_externes": _field(
            charges_externes, 0.76 if charges_externes is not None else 0.0, charges_externes_src
        ),
        "impots_taxes": _field(_extract_amount_for_label(text, r"imp[oô]ts?\s+et\s+taxes"), 0.76, "label:impots taxes"),
        "charges_financieres": _field(_extract_amount_for_label(text, r"charges?\s+financi"), 0.76, "label:charges financieres"),
        "resultat_exploitation": _field(
            resultat_exploitation,
            0.82 if resultat_exploitation is not None else 0.0,
            resultat_exploitation_src,
        ),
        "resultat_courant": _field(
            resultat_courant, 0.8 if resultat_courant is not None else 0.0, resultat_courant_src
        ),
        "resultat_net": _field(resultat_net, 0.84 if resultat_net is not None else 0.0, resultat_net_src),
    }


def _extract_liasse_is_simplifiee(text: str) -> dict[str, dict[str, Any]]:
    """Minimal dedicated extractor for 2065/2033 liasse documents."""
    bilan = _extract_bilan(text)
    cr = _extract_compte_resultat(text)
    exercice = _extract_first(r"(?:exercice|clos le)\s*[:\-]?\s*([0-9]{4})", text)
    regime = _extract_first(
        r"(?:r[ée]gime\s+simplifi[ée]\s+d[' ]imposition|regime\s+simplifie\s+d[' ]imposition)",
        text,
    )
    return {
        "liasse_type": _field("2065_2033", 0.9, "liasse:is_simplifiee"),
        "exercice": _field(exercice, 0.85 if exercice else 0.0, "header:exercice"),
        "regime_imposition": _field(regime or "rsi", 0.75 if regime else 0.55, "header:regime"),
        "total_actif": bilan.get("total_actif", _field(None, 0.0, "bilan:total_actif")),
        "total_passif": bilan.get("total_passif", _field(None, 0.0, "bilan:total_passif")),
        "chiffre_affaires": cr.get("chiffre_affaires", _field(None, 0.0, "cr:chiffre_affaires")),
        "resultat_exercice": bilan.get("resultat_exercice", _field(None, 0.0, "bilan:resultat_exercice")),
        "resultat_net": cr.get("resultat_net", _field(None, 0.0, "cr:resultat_net")),
    }


def _extract_2072(text: str) -> dict[str, dict[str, Any]]:
    header_zone = _extract_2072_header_zone(text)
    results_zone = _extract_2072_results_zone(text)
    immeubles = _extract_2072_immeubles_table(text)
    associes = _extract_2072_associes_table(text)

    # V3 focus: reliably fill only critical fields first.
    denom = _extract_value_near_label(
        header_zone,
        r"d[ée]nomination\s+de\s+la\s+soci[ée]t[ée]|d[ée]nomination\s+sci",
        r"([A-Z0-9_][A-Z0-9_.\- ]{2,120})",
    ) or _extract_value_near_label(
        text,
        r"d[ée]nomination\s+de\s+la\s+soci[ée]t[ée]|d[ée]nomination\s+sci",
        r"([A-Z0-9_][A-Z0-9_.\- ]{2,120})",
    )

    date_cloture = _extract_first_date_from_patterns(
        header_zone + "\n" + text,
        [
            r"(?:date\s+de\s+cl[ôo]ture(?:\s+de\s+l[' ]exercice)?)\s*[:\-]?\s*([0-3]?\d[\/\-][0-1]?\d[\/\-][12]\d{3})",
            r"(?:soc5).{0,40}([0-3]?\d[\/\-][0-1]?\d[\/\-][12]\d{3})",
            r"(?:cl[ôo]ture).{0,40}([0-3]?\d[\/\-][0-1]?\d[\/\-][12]\d{3})",
        ],
    )
    nb_associes = _extract_first_int_from_patterns(
        header_zone + "\n" + text,
        [
            r"(?:nombre\s+d[' ]associ[ée]s?)\s*[:\-]?\s*([0-9]{1,3})",
            r"(?:soc18).{0,20}([0-9]{1,3})",
        ],
    )
    revenus_bruts = _extract_first_amount_from_patterns(
        results_zone + "\n" + text,
        [
            r"revenus?\s+bruts?",
            r"montant\s+brut.{0,30}loyers?\s+encaiss",
        ],
        min_amount=100.0,
    )
    frais_hors_interets = _extract_first_amount_from_patterns(
        results_zone + "\n" + text,
        [
            r"frais?\s+et\s+charges?.{0,40}hors.{0,20}int[eé]r[eê]ts?",
            r"frais?\s+et\s+charges?.{0,40}autres?.{0,20}int[eé]r",
            r"frais?\s+de\s+gestion",
        ],
        min_amount=50.0,
    )
    scan_text = results_zone + "\n" + text
    interets, interets_source = _extract_first_amount_with_source(
        scan_text,
        [
            ("label:interets_emprunts", r"int[eé]r[eê]ts?\s+d[' ]emprunts?"),
            ("label:interets_emprunts_alt", r"int[eé]r[eê]ts?\s+des?\s+emprunts?"),
            ("label:interets_emprunt_singulier", r"int[eé]r[eê]t\s+d[' ]emprunt"),
            ("label:charge_interets", r"charges?.{0,10}d[' ]int[eé]r[eê]ts?"),
            ("label:dont_interets", r"dont.{0,20}int[eé]r[eê]ts?"),
            ("label:emprunts_interets", r"emprunts?.{0,15}int[eé]r[eê]ts?"),
        ],
        min_amount=50.0,
    )
    # Wide-gap OCR (amount far to the right of the label).
    if interets is None:
        for src_hint, pat in [
            ("label_wide:interets_emprunts", r"int[eé]r[eê]ts?\s+d[' ]emprunts?"),
            ("label_wide:interets_des_emprunts", r"int[eé]r[eê]ts?\s+des?\s+emprunts?"),
        ]:
            w = _extract_financial_amount_for_label_wide(scan_text, pat, max_gap=140, min_amount=50.0)
            if w is not None:
                interets, interets_source = w, src_hint
                break
    if interets is None:
        interets, interets_source = _extract_amount_from_lines_with_keyword(
            scan_text, r"int[eé]r[eê]t.{0,12}emprunt", min_amount=50.0
        )
    if interets is None:
        interets, interets_source = _extract_amount_after_keyword_multiline(
            scan_text,
            r"int[eé]r[eê]ts?.{0,25}emprunt|emprunt.{0,20}int[eé]r[eê]t",
            min_amount=50.0,
        )
    revenu_net = _extract_first_amount_from_patterns(
        scan_text,
        [
            r"revenu\s+net(?:\s+foncier)?",
            r"d[ée]ficit\s+net",
            r"revenu\s*\(\+\)|d[ée]ficit\s*\(\-\)",
        ],
        min_amount=100.0,
    )
    revenu_net_from_doc = revenu_net is not None

    # Fallbacks from annexes/tables when top-level labels are missing.
    immeubles_frais = sum(
        float((x.get("frais_gestion") or 0.0) + (x.get("assurance") or 0.0) + (x.get("travaux") or 0.0) + (x.get("impositions") or 0.0))
        for x in immeubles
    )
    associes_frais = sum(float(x.get("quote_part_frais_charges") or 0.0) for x in associes)
    if frais_hors_interets is None:
        if immeubles_frais > 0:
            frais_hors_interets = immeubles_frais
        elif associes_frais > 0:
            frais_hors_interets = associes_frais

    immeubles_interets = sum(float(x.get("interets_emprunts") or 0.0) for x in immeubles)
    associes_interets = sum(float(x.get("quote_part_interets_emprunts") or 0.0) for x in associes)
    if interets is None:
        if immeubles_interets > 0:
            interets = immeubles_interets
            interets_source = "fallback:immeubles_interets_sum"
        elif associes_interets > 0:
            interets = associes_interets
            interets_source = "fallback:associes_interets_sum"

    # Algebraic closure (conservative): only when revenu net was read from the document,
    # not when it will be derived from rb - frais - interets (avoids circular reasoning).
    if interets is None and revenu_net_from_doc:
        rb_ok = isinstance(revenus_bruts, (int, float))
        rn_ok = isinstance(revenu_net, (int, float))
        fc_ok = frais_hors_interets is not None and isinstance(frais_hors_interets, (int, float))
        if rb_ok and rn_ok and fc_ok:
            cand = float(revenus_bruts) - float(frais_hors_interets) - float(revenu_net)
            if _plausible_2072_interets_candidate(cand, float(revenus_bruts)):
                interets = cand
                interets_source = "fallback:derived_rb_minus_frais_minus_revenu_net"

    if revenus_bruts is None:
        immeubles_rb = sum(float(x.get("revenus_bruts") or 0.0) for x in immeubles)
        associes_rb = sum(float(x.get("quote_part_revenus_bruts") or 0.0) for x in associes)
        if immeubles_rb > 0:
            revenus_bruts = immeubles_rb
        elif associes_rb > 0:
            revenus_bruts = associes_rb

    if revenu_net is None and isinstance(revenus_bruts, (int, float)):
        fc = float(frais_hors_interets or 0.0)
        ie = float(interets or 0.0)
        revenu_net = revenus_bruts - fc - ie

    return {
        "denomination_sci": _field(denom, 0.92 if denom else 0.0, "header:denomination_societe"),
        "date_cloture_exercice": _field(date_cloture, 0.92 if date_cloture else 0.0, "header:date_cloture_exercice"),
        "nombre_associes": _field(nb_associes, 0.9 if nb_associes is not None else 0.0, "header:nombre_associes"),
        "revenus_bruts": _field(revenus_bruts, 0.9 if revenus_bruts is not None else 0.0, "resultats:revenus_bruts"),
        "frais_charges_hors_interets": _field(frais_hors_interets, 0.88 if frais_hors_interets is not None else 0.0, "resultats:frais_charges_hors_interets"),
        "interets_emprunts": _field(
            interets, 0.88 if interets is not None else 0.0, interets_source
        ),
        "revenu_net_foncier": _field(revenu_net, 0.9 if revenu_net is not None else 0.0, "resultats:revenu_net_foncier"),
        # Keep advanced fields nullable for now; they will be re-enabled once core 5 are stable.
        "adresse_sci": _field(None, 0.0, "deferred:v2.3"),
        "adresse_siege_ouverture": _field(None, 0.0, "deferred:v2.3"),
        "nombre_parts_ouverture": _field(None, 0.0, "deferred:v2.3"),
        "nombre_parts_cloture": _field(None, 0.0, "deferred:v2.3"),
        "montant_nominal_parts": _field(None, 0.0, "deferred:v2.3"),
        "paiements_travaux": _field(None, 0.0, "deferred:v2.3"),
        "resultat_financier": _field(None, 0.0, "deferred:v2.3"),
        "resultat_fiscal": _field(None, 0.0, "deferred:v2.3"),
        "resultat_exploitation": _field(None, 0.0, "deferred:v2.3"),
        "resultat_exceptionnel": _field(None, 0.0, "deferred:v2.3"),
        "montant_produits_financiers": _field(None, 0.0, "deferred:v2.3"),
        "montant_produits_exceptionnels": _field(None, 0.0, "deferred:v2.3"),
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
        ie_im = _extract_amount_for_label(chunk, r"int[eé]r[eê]ts?\s+des?\s+emprunts?")
        if ie_im is None:
            ie_im = _extract_financial_amount_for_label_wide(
                chunk, r"int[eé]r[eê]ts?\s+des?\s+emprunts?", max_gap=140, min_amount=50.0
            )
        if ie_im is None:
            ie_im = _extract_financial_amount_for_label_wide(
                chunk, r"int[eé]r[eê]ts?\s+d[' ]emprunt", max_gap=140, min_amount=50.0
            )
        entry = {
            "immeuble_id": f"IMMEUBLE_{len(entries) + 1}",
            "adresse_immeuble": _extract_value_near_label(
                chunk,
                r"adresse\s+de\s+l[' ]immeuble",
                r"([A-Z0-9_].{6,160})",
            ),
            "nombre_locaux": _to_float_fr(_extract_first(r"(?:nombre\s+de\s+locaux)\s*[:\-]?\s*([0-9]{1,4})", chunk)),
            "revenus_bruts": _extract_amount_for_label(chunk, r"montant\s+brut.{0,25}loyers?\s+encaiss|revenus?\s+bruts?"),
            "frais_gestion": _extract_amount_for_label(chunk, r"frais?\s+de\s+gestion"),
            "assurance": _extract_amount_for_label(chunk, r"primes?\s+d[' ]assurance|assurance"),
            "travaux": _extract_amount_for_label(chunk, r"travaux|d[ée]penses?\s+de\s+r[ée]paration"),
            "impositions": _extract_amount_for_label(chunk, r"impositions?"),
            "interets_emprunts": ie_im,
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
            "nom": _extract_value_near_label(
                chunk,
                r"nom\s+et\s+pr[ée]nom",
                r"([A-Z_][A-Z_.\- ]{2,120})",
            ),
            "date_naissance": _extract_first(r"(?:date\s+de\s+naissance)\s*[:\-]?\s*([0-3]?\d[\/\-][0-1]?\d[\/\-][12]\d{3})", chunk),
            "adresse": _extract_value_near_label(
                chunk,
                r"(?:\badresse\b)",
                r"([A-Z0-9_].{8,140})",
            ),
            "parts_detenues": _to_float_fr(_extract_first(r"(?:parts?\s+d[ée]tenues?)\s*[:\-]?\s*([0-9]{1,10})", chunk)),
            "quote_part_revenus_bruts": _extract_amount_for_label(chunk, r"quote[\- ]part.{0,25}revenus?\s+bruts?"),
            "quote_part_frais_charges": _extract_amount_for_label(chunk, r"quote[\- ]part.{0,25}frais?.{0,25}charges?"),
            "quote_part_interets_emprunts": _extract_amount_for_label(chunk, r"quote[\- ]part.{0,25}int[eé]r[eê]ts?\s+d[' ]emprunts?"),
            "quote_part_amortissement": _extract_amount_for_label(chunk, r"quote[\- ]part.{0,25}amortissement"),
            "quote_part_revenu_net": _extract_amount_for_label(chunk, r"quote[\- ]part.{0,25}revenu\s+net|quote[\- ]part.{0,25}d[ée]ficit"),
        }
        # Anti-label cleanup for text columns
        nom_value = entry.get("nom")
        adresse_value = entry.get("adresse")
        entry["nom"] = _clean_text_candidate(nom_value if isinstance(nom_value, str) else None)
        entry["adresse"] = _clean_text_candidate(
            adresse_value if isinstance(adresse_value, str) else None
        )
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
        "critical_missing_fields": [],
        "needs_review": needs_review,
        "ready_for_ai": coverage >= 0.8,
        "quality_flags": flags,
    }


def _quality_bilan(fields: dict[str, dict[str, Any]]) -> dict[str, Any]:
    base = _quality(fields)
    critical = [
        "total_actif",
        "total_passif",
        "capitaux_propres",
        "dettes_financieres",
        "dettes_fournisseurs",
        "resultat_exercice",
    ]
    critical_missing = [k for k in critical if fields.get(k, {}).get("value") in (None, "", [])]

    actif = fields.get("total_actif", {}).get("value")
    passif = fields.get("total_passif", {}).get("value")
    balance_ok = False
    balance_gap: float | None = None
    # Strict (audit) vs relaxed (OCR / plaquette synthèse): large docs tolerate more rounding noise.
    tol_strict = 0.0
    tol_relaxed = 0.0
    if isinstance(actif, (int, float)) and isinstance(passif, (int, float)):
        fa, fp = float(actif), float(passif)
        balance_gap = abs(fa - fp)
        ref = max(abs(fa), abs(fp), 1.0)
        tol_strict = max(2.0, ref * 0.02)
        tol_relaxed = max(10.0, ref * 0.04)
        balance_ok = balance_gap <= tol_relaxed

    ready_for_ai = (
        base["coverage_ratio"] >= 0.75
        and not critical_missing
        and balance_ok
    )
    needs_review = (not ready_for_ai) or base["needs_review"]

    flags = list(base.get("quality_flags", []))
    if critical_missing:
        flags.append("critical_fields_missing")
    if isinstance(actif, (int, float)) and isinstance(passif, (int, float)) and balance_gap is not None:
        if balance_gap > tol_relaxed:
            flags.append("bilan_balance_mismatch")
        elif balance_gap > tol_strict:
            flags.append("bilan_balance_minor_gap")
    elif "total_actif" not in critical_missing and "total_passif" not in critical_missing:
        # Totaux renseignés mais non comparables numériquement → garder un signal explicite.
        flags.append("bilan_balance_mismatch")

    return {
        **base,
        "critical_missing_fields": critical_missing,
        "needs_review": needs_review,
        "ready_for_ai": ready_for_ai,
        "quality_flags": sorted(set(flags)),
        "bilan_balance_gap": round(balance_gap, 2) if balance_gap is not None else None,
        "bilan_balance_tolerance_used": round(tol_relaxed, 2) if tol_relaxed else None,
    }


def _cr_step_tolerances(anchor_abs: float) -> tuple[float, float]:
    """Seuils strict vs relax pour un pas de chaîne (REX→RC ancré sur |REX|, RC→RN sur |RC|).

    - *relax* : aligné sur l’historique ``max(500k, 2×|ancre|)`` (évite l’effet « triangulaire »
      si l’on prenait ``max(|REX|,|RC|)`` pour les deux côtés).
    - *strict* : bande intérieure pour ``result_chain_minor_gap`` sans bloquer ``ready_for_ai``.
    """
    a = max(abs(float(anchor_abs)), 1.0)
    tol_strict = max(250_000.0, a * 1.5)
    tol_relaxed = max(500_000.0, a * 2.0)
    return tol_strict, tol_relaxed


def _quality_compte_resultat(fields: dict[str, dict[str, Any]]) -> dict[str, Any]:
    base = _quality(fields)
    critical = [
        "chiffre_affaires",
        "charges_externes",
        "resultat_exploitation",
        "resultat_courant",
        "resultat_net",
    ]
    critical_missing = [k for k in critical if fields.get(k, {}).get("value") in (None, "", [])]

    rex = fields.get("resultat_exploitation", {}).get("value")
    rc = fields.get("resultat_courant", {}).get("value")
    rn = fields.get("resultat_net", {}).get("value")
    chain_keys = ("resultat_exploitation", "resultat_courant", "resultat_net")
    results_filled = all(fields.get(k, {}).get("value") not in (None, "", []) for k in chain_keys)

    progression_ok = True
    chain_minor_gap = False
    delta_rex_rc: float | None = None
    delta_rc_rn: float | None = None
    tol_s1 = tol_r1 = tol_s2 = tol_r2 = 0.0

    if isinstance(rex, (int, float)) and isinstance(rc, (int, float)) and isinstance(rn, (int, float)):
        fr, fc, fn = float(rex), float(rc), float(rn)
        delta_rex_rc = abs(fc - fr)
        delta_rc_rn = abs(fn - fc)
        tol_s1, tol_r1 = _cr_step_tolerances(fr)
        tol_s2, tol_r2 = _cr_step_tolerances(fc)
        step1_ok = delta_rex_rc <= tol_r1
        step2_ok = delta_rc_rn <= tol_r2
        progression_ok = step1_ok and step2_ok
        chain_minor_gap = progression_ok and (
            (tol_s1 < delta_rex_rc <= tol_r1) or (tol_s2 < delta_rc_rn <= tol_r2)
        )
    elif results_filled:
        # Totaux de chaîne renseignés mais non comparables numériquement.
        progression_ok = False

    ready_for_ai = (
        base["coverage_ratio"] >= 0.75
        and not critical_missing
        and progression_ok
    )
    needs_review = (not ready_for_ai) or base["needs_review"]

    flags = list(base.get("quality_flags", []))
    if critical_missing:
        flags.append("critical_fields_missing")
    if isinstance(rex, (int, float)) and isinstance(rc, (int, float)) and isinstance(rn, (int, float)):
        if not progression_ok:
            flags.append("result_chain_inconsistent")
        elif chain_minor_gap:
            flags.append("result_chain_minor_gap")
    elif results_filled:
        flags.append("result_chain_inconsistent")

    return {
        **base,
        "critical_missing_fields": critical_missing,
        "needs_review": needs_review,
        "ready_for_ai": ready_for_ai,
        "quality_flags": sorted(set(flags)),
        "cr_chain_delta_rex_rc": round(delta_rex_rc, 2) if delta_rex_rc is not None else None,
        "cr_chain_delta_rc_rn": round(delta_rc_rn, 2) if delta_rc_rn is not None else None,
        "cr_chain_tol_relaxed_rex_rc": round(tol_r1, 2) if tol_r1 else None,
        "cr_chain_tol_relaxed_rc_rn": round(tol_r2, 2) if tol_r2 else None,
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


def _pseudonymize_2072_output(fields: dict[str, dict[str, Any]], tables: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Keep extraction quality from raw while exposing anonymized structured output."""
    out_fields = dict(fields)
    if out_fields.get("denomination_sci", {}).get("value"):
        out_fields["denomination_sci"] = _field("SOCIETE_1", out_fields["denomination_sci"].get("confidence", 0.9), "pseudo:denomination_sci")
    if out_fields.get("adresse_sci", {}).get("value"):
        out_fields["adresse_sci"] = _field("ADRESSE_SOCIETE_1", out_fields["adresse_sci"].get("confidence", 0.85), "pseudo:adresse_sci")
    if out_fields.get("adresse_siege_ouverture", {}).get("value"):
        out_fields["adresse_siege_ouverture"] = _field("ADRESSE_SIEGE_1", out_fields["adresse_siege_ouverture"].get("confidence", 0.8), "pseudo:adresse_siege_ouverture")

    out_tables = dict(tables)
    immeubles = []
    for idx, it in enumerate((tables.get("immeubles") or []), start=1):
        row = dict(it)
        if row.get("adresse_immeuble"):
            row["adresse_immeuble"] = f"BIEN_{idx}"
        immeubles.append(row)
    associes = []
    for idx, it in enumerate((tables.get("associes_revenus_fonciers") or []), start=1):
        row = dict(it)
        if row.get("nom"):
            row["nom"] = f"ASSOCIE_{idx}"
        if row.get("adresse"):
            row["adresse"] = f"ADRESSE_ASSOCIE_{idx}"
        associes.append(row)
    if "immeubles" in out_tables:
        out_tables["immeubles"] = immeubles
    if "associes_revenus_fonciers" in out_tables:
        out_tables["associes_revenus_fonciers"] = associes
    return out_fields, out_tables


def _extractor_bilan(source_text: str, anonymized_text: str) -> StructuredExtractionResult:
    fields = _extract_bilan(source_text)
    tables = {"accounting_lines": _extract_generic_accounting_table(anonymized_text)}
    return StructuredExtractionResult(
        fields=fields,
        tables=tables,
        quality=_quality_bilan(fields),
        extractor_name="extractor_bilan",
    )


def _extractor_compte_resultat(source_text: str, anonymized_text: str) -> StructuredExtractionResult:
    fields = _extract_compte_resultat(source_text)
    tables = {"accounting_lines": _extract_generic_accounting_table(anonymized_text)}
    return StructuredExtractionResult(
        fields=fields,
        tables=tables,
        quality=_quality_compte_resultat(fields),
        extractor_name="extractor_compte_resultat",
    )


def _extractor_fiscal_2072(source_text: str, _anonymized_text: str) -> StructuredExtractionResult:
    fields = _extract_2072(source_text)
    tables = {
        "immeubles": _extract_2072_immeubles_table(source_text),
        "associes_revenus_fonciers": _extract_2072_associes_table(source_text),
    }
    quality = _quality_2072(fields, tables, source_text)
    fields, tables = _pseudonymize_2072_output(fields, tables)
    return StructuredExtractionResult(
        fields=fields,
        tables=tables,
        quality=quality,
        extractor_name="extractor_2072",
    )


EXTRACTOR_REGISTRY_V1: dict[str, Any] = {
    "bilan": _extractor_bilan,
    "compte_resultat": _extractor_compte_resultat,
    "fiscal_2072": _extractor_fiscal_2072,
}


def _extraction_quality_better(q_new: dict[str, Any], q_old: dict[str, Any]) -> bool:
    """True si la qualité q_new est strictement meilleure que q_old."""
    cm_new = len(q_new.get("critical_missing_fields") or [])
    cm_old = len(q_old.get("critical_missing_fields") or [])
    if cm_new < cm_old:
        return True
    if cm_new > cm_old:
        return False
    cov_new = float(q_new.get("coverage_ratio") or 0.0)
    cov_old = float(q_old.get("coverage_ratio") or 0.0)
    return cov_new > cov_old


def _run_extractor_pipeline(
    doc_type: str,
    source_text: str,
    anonymized_text: str,
) -> StructuredExtractionResult:
    """Extraction structurée selon le type (registre, liasse, fallback)."""
    extractor = EXTRACTOR_REGISTRY_V1.get(doc_type)
    if extractor is not None:
        return extractor(source_text, anonymized_text)
    if doc_type == "liasse_is_simplifiee":
        fields = _extract_liasse_is_simplifiee(source_text)
        return StructuredExtractionResult(
            fields=fields,
            tables={"accounting_lines": _extract_generic_accounting_table(anonymized_text)},
            quality=_quality(fields),
            extractor_name="extractor_liasse_is_simplifiee",
        )
    fields = _extract_common_fields(source_text)
    return StructuredExtractionResult(
        fields=fields,
        tables={"accounting_lines": _extract_generic_accounting_table(anonymized_text)},
        quality=_quality(fields),
        extractor_name="extractor_common_fallback",
    )


def _build_contract_payload(
    *,
    doc_type: str,
    detected_doc_type: str,
    routing_confidence: float,
    routing_confidence_raw: float,
    routing_reasons: list[str],
    routing_runner_up: dict[str, Any],
    fields: dict[str, dict[str, Any]],
    tables: dict[str, Any],
    quality: dict[str, Any],
    original_filename: str,
    extractor_name: str,
    text_segmentation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    extractor_name = (extractor_name or "").strip() or "extractor_unknown_fallback"
    quality_out = dict(quality or {})
    quality_out.setdefault("coverage_ratio", 0.0)
    quality_out.setdefault("filled_fields", 0)
    quality_out.setdefault("total_fields", 0)
    quality_out.setdefault("needs_review", True)
    quality_out.setdefault("ready_for_ai", False)
    quality_out.setdefault("quality_flags", [])
    quality_out.setdefault("critical_missing_fields", [])

    provenance: dict[str, Any] = {
        "extractor_version": "v3-registry",
        "extractor_name": extractor_name,
        "strategy": "registry-specialized",
        "routing_version": "v1.5-scored-router",
        "source_filename": original_filename,
    }
    if text_segmentation:
        provenance["text_segmentation"] = text_segmentation

    experience = build_quality_experience(
        doc_type=doc_type,
        quality=quality_out,
        provenance=provenance,
    )

    return {
        "doc_type": doc_type,
        "detected_doc_type": detected_doc_type,
        "routing_confidence": routing_confidence,
        "routing_confidence_raw": routing_confidence_raw,
        "routing_reasons": routing_reasons,
        "routing_runner_up": routing_runner_up,
        "anonymized": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fields": fields,
        "tables": tables,
        "quality": quality_out,
        "provenance": provenance,
        "experience": experience,
    }


def build_structured_dataset(
    anonymized_text: str,
    original_filename: str = "",
    requested_doc_type: str = "auto",
    extraction_text: str | None = None,
) -> dict[str, Any]:
    """Build normalized structured dataset payload for downstream analytics/AI."""
    from app.services.text_segment_selector import select_extraction_segment

    full_text_for_routing = extraction_text if extraction_text is not None else anonymized_text
    detected_doc_type, routing_confidence, routing_reasons, routing_runner_up = classify_doc_type_scored(
        full_text_for_routing, original_filename
    )
    doc_type = detected_doc_type if requested_doc_type in ("", "auto") else requested_doc_type

    source_text = full_text_for_routing
    text_segmentation: dict[str, Any] = {}
    if extraction_text is not None:
        seg, text_segmentation = select_extraction_segment(extraction_text, doc_type)
        if text_segmentation.get("strategy") == "semantic_window":
            source_text = seg

    extracted = _run_extractor_pipeline(doc_type, source_text, anonymized_text)

    # Si la fenêtre sémantique a rogné les tableaux utiles, le texte entier est souvent meilleur.
    if (
        text_segmentation.get("strategy") == "semantic_window"
        and extraction_text is not None
    ):
        alt = _run_extractor_pipeline(doc_type, full_text_for_routing, anonymized_text)
        if _extraction_quality_better(alt.quality, extracted.quality):
            extracted = alt
            text_segmentation = {
                **text_segmentation,
                "fallback_to_full_text": True,
                "fallback_reason": "full_text_strictly_better_quality",
            }
        else:
            text_segmentation = {**text_segmentation, "fallback_to_full_text": False}

    fields = extracted.fields
    tables = extracted.tables
    quality = extracted.quality

    routing_confidence_raw = routing_confidence
    # Guardrail: if critical 2072 fields are mostly missing, cap routing confidence.
    if doc_type == "fiscal_2072":
        critical6 = [
            "denomination_sci",
            "date_cloture_exercice",
            "nombre_associes",
            "revenus_bruts",
            "interets_emprunts",
            "revenu_net_foncier",
        ]
        critical_present = sum(1 for k in critical6 if (fields.get(k, {}) or {}).get("value") not in (None, "", []))
        if critical_present < 3:
            routing_confidence = min(routing_confidence, 0.6)
    # Global guardrail: confidence shown to users should remain conservative when
    # critical fields are missing, even if router lexical score is high.
    critical_missing = quality.get("critical_missing_fields", []) if isinstance(quality, dict) else []
    if isinstance(critical_missing, list) and critical_missing:
        routing_confidence = min(routing_confidence, 0.85)

    if extraction_text is not None:
        from app.services.text_segment_selector import count_pdf_page_markers

        n_mark = count_pdf_page_markers(extraction_text)
        if n_mark:
            text_segmentation = {**text_segmentation, "pdf_page_markers_in_source": n_mark}

    return _build_contract_payload(
        doc_type=doc_type,
        detected_doc_type=detected_doc_type,
        routing_confidence=routing_confidence,
        routing_confidence_raw=routing_confidence_raw,
        routing_reasons=routing_reasons,
        routing_runner_up=routing_runner_up,
        fields=fields,
        tables=tables,
        quality=quality,
        original_filename=original_filename,
        extractor_name=extracted.extractor_name,
        text_segmentation=text_segmentation,
    )

