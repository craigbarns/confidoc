"""ConfiDoc Backend — Structured datasets by document type (V1)."""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.logging import get_logger
from app.services.extraction_thresholds import THRESHOLDS
from app.services.quality_experience import build_quality_experience

logger = get_logger(__name__)


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
        (
            "statuts_societe",
            (
                "statuts",
                "société à responsabilité limitée",
                "société par actions simplifiée",
                "forme juridique",
                "capital social",
                "siège social",
                "siege social",
                "objet social",
                "durée",
                "duree",
                "immatriculée au rcs",
                "immatriculee au rcs",
                "greffe",
            ),
            3,
        ),
        (
            "liasse_is_simplifiee",
            (
                "2065",
                "2065-sd",
                "2033-a",
                "2033-b",
                "bilan simplifié",
                "bilan simplifie",
                "compte de résultat simplifié",
                "compte de resultat simplifie",
                "régime simplifié d'imposition",
                "regime simplifie d'imposition",
            ),
            3,
        ),
        (
            "fiscal_2072",
            (
                "2072",
                "2072-an1",
                "2072-an2",
                "revenus fonciers",
                "associés revenus fonciers",
                "associes revenus fonciers",
            ),
            2,
        ),
        (
            "etat_immobilisations",
            (
                "etat des immobilisations",
                "tableau des immobilisations",
                "immobilisations",
                "amortissements",
                "valeur nette comptable",
                "vnc",
            ),
            3,
        ),
        ("fiscal_2044", ("2044", "revenu foncier", "déficit foncier", "deficit foncier"), 2),
        ("bilan", ("bilan", "total actif", "total passif", "capitaux propres"), 2),
        (
            "compte_resultat",
            ("compte de résultat", "compte de resultat", "résultat net", "resultat net"),
            2,
        ),
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
        if any(
            k in source
            for k in ("fiscal", "liasse", "impot", "tva", "2065", "2033", "2044", "2072")
        ):
            best_type = "unknown_tax"
        elif any(
            k in source for k in ("bilan", "compte", "journal", "écriture", "ecriture", "pcg")
        ):
            best_type = "unknown_accounting"
        else:
            best_type = "unknown_other"

    confidence = (
        min(0.99, 0.45 + (best_score * 0.15)) if not best_type.startswith("unknown_") else 0.35
    )
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
    # Anti-bruit OCR sur les chiffres (O/0).
    raw = raw.replace("O", "0").replace("o", "0")
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


def _to_iso_date_fr(text: str | None) -> str | None:
    if not text:
        return None
    s = str(text).strip().replace("-", "/").replace(".", "/")
    m = re.search(r"\b([0-3]?\d)[/ ]([0-1]?\d)[/ ]([12]\d{3})\b", s)
    if not m:
        return None
    try:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        dt = datetime(y, mo, d)
    except ValueError:
        return None
    return dt.strftime("%Y-%m-%d")


def _iso_date_in_range(iso: str | None, start_iso: str | None, end_iso: str | None) -> bool:
    if not iso:
        return False
    try:
        d = datetime.fromisoformat(iso)
        if start_iso and d < datetime.fromisoformat(start_iso):
            return False
        return not (end_iso and d > datetime.fromisoformat(end_iso))
    except ValueError:
        return False


def _extract_amount_for_label(text: str, label_regex: str, max_gap: int = 200) -> float | None:
    pat = rf"{label_regex}[^0-9\-]{{0,{max_gap}}}([0-9Oo][0-9Oo \t\u00a0.,]{{0,30}})"
    return _clean_amount_candidate(_to_float_fr(_extract_first(pat, text)))


def _extract_financial_amount_for_label(
    text: str,
    label_regex: str,
    min_amount: float = THRESHOLDS["amount_min_default"],
    max_gap: int = 200,
) -> float | None:
    """Financial amount extractor with plausibility threshold (avoid index-like numbers)."""
    value = _extract_amount_for_label(text, label_regex, max_gap)
    if value is None:
        return None
    return value if abs(value) >= min_amount else None


def _extract_first_amount_from_patterns(
    text: str,
    patterns: list[str],
    min_amount: float = THRESHOLDS["amount_min_default"],
    max_gap: int = 200,
) -> float | None:
    for pat in patterns:
        val = _extract_financial_amount_for_label(text, pat, min_amount=min_amount, max_gap=max_gap)
        if val is not None:
            return val
    return None


def _extract_first_amount_with_source(
    text: str,
    patterns: list[tuple[str, str]],
    min_amount: float = THRESHOLDS["amount_min_default"],
    max_gap: int = 200,
) -> tuple[float | None, str]:
    for source_hint, pat in patterns:
        val = _extract_financial_amount_for_label(text, pat, min_amount=min_amount, max_gap=max_gap)
        if val is not None:
            return val, source_hint
    return None, "missing"


def _extract_amount_from_lines_with_keyword(
    text: str,
    keyword_regex: str,
    min_amount: float = THRESHOLDS["amount_min_default"],
) -> tuple[float | None, str]:
    pat_kw = re.compile(keyword_regex, re.IGNORECASE)
    for raw in text.splitlines():
        line = raw.strip()
        if not line or not pat_kw.search(line):
            continue
        m = re.search(
            r"([0-9Oo][0-9Oo \t\u00a0.,]{0,30})(?:\s*€|\s*EUR)?\s*$",
            line,
            re.IGNORECASE,
        )
        if not m:
            continue
        v = _clean_amount_candidate(_to_float_fr(m.group(1)))
        if isinstance(v, float) and abs(v) >= min_amount:
            return v, "fallback:line_keyword"
    return None, "missing"


def _extract_line_amount_tokens(line: str) -> list[float]:
    """Extract independent numeric tokens from one OCR line (avoid merged columns)."""
    vals: list[float] = []
    for m in re.finditer(
        (
            r"(-?[0-9Oo]{1,3}(?:[ \u00a0][0-9Oo]{3}){2}(?![ \u00a0][0-9Oo]{3})(?:[.,][0-9Oo]{2})?"
            r"|-?[0-9Oo]{1,3}[ \u00a0][0-9Oo]{3}(?:[.,][0-9Oo]{2})?"
            r"|-?[0-9Oo]{3,}(?:[.,][0-9Oo]{2})?)"
        ),
        line,
        flags=re.IGNORECASE,
    ):
        v = _clean_amount_candidate(_to_float_fr(m.group(1)))
        if isinstance(v, float):
            vals.append(v)
    return vals


def _extract_first_amount_token_from_keyword_line(
    text: str,
    keyword_regex: str,
    *,
    min_amount: float = THRESHOLDS["amount_min_default"],
    max_lines: int = 8,
) -> tuple[float | None, str]:
    """Pick the first plausible amount token on a keyword line (year N before N-1)."""
    pat_kw = re.compile(keyword_regex, re.IGNORECASE)
    seen = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or not pat_kw.search(line):
            continue
        seen += 1
        tokens = [v for v in _extract_line_amount_tokens(line) if abs(v) >= min_amount]
        if tokens:
            return tokens[0], "fallback:line_keyword_first_token"
        if seen >= max_lines:
            break
    return None, "missing"


def _extract_first_amount_token_from_keyword_line_excluding(
    text: str,
    keyword_regex: str,
    *,
    min_amount: float = THRESHOLDS["amount_min_default"],
    exclude_regex: str | None = None,
    max_lines: int = 8,
) -> tuple[float | None, str]:
    """Like line-token extraction, but skipping lines matching exclude_regex."""
    pat_kw = re.compile(keyword_regex, re.IGNORECASE)
    pat_ex = re.compile(exclude_regex, re.IGNORECASE) if exclude_regex else None
    seen = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or not pat_kw.search(line):
            continue
        if pat_ex and pat_ex.search(line):
            continue
        seen += 1
        tokens = [v for v in _extract_line_amount_tokens(line) if abs(v) >= min_amount]
        if tokens:
            return tokens[0], "fallback:line_keyword_first_token_excluding"
        if seen >= max_lines:
            break
    return None, "missing"


def _extract_amount_tokens_for_keyword_lines(
    text: str,
    keyword_regex: str,
    *,
    min_amount: float = THRESHOLDS["amount_min_default"],
    max_lines: int = 5,
) -> list[float]:
    """Collect amount tokens on lines matching a keyword regex."""
    pat_kw = re.compile(keyword_regex, re.IGNORECASE)
    out: list[float] = []
    seen = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or not pat_kw.search(line):
            continue
        seen += 1
        out.extend([v for v in _extract_line_amount_tokens(line) if abs(v) >= min_amount])
        if seen >= max_lines:
            break
    return out


def _pick_total_value_from_tokens(tokens: list[float]) -> float | None:
    """Heuristic for balance lines with multiple columns (N, N-1, and sometimes brut/amort)."""
    if not tokens:
        return None
    if len(tokens) >= 4:
        # Typical actif pattern: brut, amort, net(N), net(N-1).
        return float(tokens[-2])
    if len(tokens) == 3:
        return float(tokens[1])
    # Typical passif pattern: N then N-1.
    return float(tokens[0])


def _extract_total_general_from_line(
    text: str, keyword_regex: str, *, min_amount: float = 100.0
) -> tuple[float | None, str]:
    """Extract total from explicit TOTAL GENERAL line, preferring N-column value."""
    pat_kw = re.compile(keyword_regex, re.IGNORECASE)
    for raw in text.splitlines():
        line = raw.strip()
        if not line or not pat_kw.search(line):
            continue
        tokens = [v for v in _extract_line_amount_tokens(line) if abs(v) >= min_amount]
        picked = _pick_total_value_from_tokens(tokens)
        if isinstance(picked, float):
            return picked, "fallback:total_general_line_token_heuristic"
    return None, "missing"


def _extract_financial_amount_for_label_wide(
    text: str,
    label_regex: str,
    *,
    max_gap: int = 120,
    min_amount: float = THRESHOLDS["amount_min_default"],
) -> float | None:
    """Like _extract_financial_amount_for_label with a wider OCR-tolerant gap."""
    pat = rf"{label_regex}[^0-9\-]{{0,{max_gap}}}([0-9Oo][0-9Oo \t\u00a0.,]{{0,30}})"
    value = _clean_amount_candidate(_to_float_fr(_extract_first(pat, text)))
    if value is None:
        return None
    return value if abs(value) >= min_amount else None


def _extract_amount_after_keyword_multiline(
    text: str,
    keyword_regex: str,
    min_amount: float = THRESHOLDS["amount_min_low"],
    max_lookahead_lines: int = 3,
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
            for m in re.finditer(
                r"([0-9Oo][0-9Oo \t\u00a0.,]{0,30})(?:\s*$|\s*€|\s*EUR)?", scan, re.IGNORECASE
            ):
                v = _clean_amount_candidate(_to_float_fr(m.group(1)))
                if isinstance(v, float) and abs(v) >= min_amount:
                    candidates.append(v)
            if candidates:
                v = candidates[-1]
                src = "fallback:multiline_after_keyword" if j > 0 else "fallback:line_after_keyword"
                return v, src
    return None, "missing"


def _extract_value_from_anchor_window(
    text: str,
    *,
    anchor_regex: str,
    value_regex: str,
    window_lines: int = 5,
    flags: int = re.IGNORECASE,
) -> str | None:
    """Extract a raw value in the next N lines following an anchor label."""
    lines = text.splitlines()
    pat_anchor = re.compile(anchor_regex, flags)
    pat_value = re.compile(value_regex, flags)
    for i, raw in enumerate(lines):
        if not pat_anchor.search(raw):
            continue
        start = i + 1
        end = min(len(lines), start + max(1, window_lines))
        window = "\n".join(lines[start:end])
        m = pat_value.search(window)
        if m:
            return m.group(1)
    return None


def _extract_2072_amount_from_anchor_window(
    text: str,
    *,
    anchor_regex: str,
    window_lines: int = 8,
    min_amount: float = 50.0,
) -> tuple[float | None, str]:
    """
    2072-specific fallback: find first plausible amount token in N lines after anchor.
    Chooses the first token to prefer column N over N-1 on form-like layouts.
    """
    lines = text.splitlines()
    pat_anchor = re.compile(anchor_regex, re.IGNORECASE)
    for i, raw in enumerate(lines):
        if not pat_anchor.search(raw):
            continue
        start = i + 1
        end = min(len(lines), start + max(1, window_lines))
        for scan in lines[start:end]:
            tokens = [v for v in _extract_line_amount_tokens(scan) if abs(v) >= min_amount]
            if tokens:
                picked = _clean_amount_candidate(float(tokens[0]))
                if isinstance(picked, float):
                    return picked, "fallback:2072_anchor_window_first_token"
    return None, "missing"


def _is_2072_arithmetically_coherent(
    revenus_bruts: float | None,
    frais_hors_interets: float | None,
    interets: float | None,
    revenu_net: float | None,
) -> bool:
    """Check RB - frais - intérêts ~= revenu net with pragmatic tolerance."""
    if not all(isinstance(v, (int, float)) for v in [revenus_bruts, frais_hors_interets, interets, revenu_net]):
        return False
    expected = float(revenus_bruts) - float(frais_hors_interets) - float(interets)
    actual = float(revenu_net)
    tol = max(2.0, abs(expected) * 0.05)
    return abs(expected - actual) <= tol


def _normalize_2072_closure_date(value: str | None) -> str | None:
    """Force annual 2072 closure format to 31/12/YYYY when year is known."""
    if not isinstance(value, str) or not value.strip():
        return value
    raw = value.strip()
    if raw.startswith("31/12/"):
        return raw
    year_match = re.search(r"([12]\d{3})$", raw)
    if not year_match:
        return raw
    return f"31/12/{year_match.group(1)}"


def _extract_2072_amount_from_ligne_17_18_line(text: str) -> float | None:
    """Same-line hint for frais (17+18) — avoids grabbing neighbor lines in shifted forms."""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or not re.search(r"\b17\s*\+\s*18\b", line, re.IGNORECASE):
            continue
        tokens = [v for v in _extract_line_amount_tokens(line) if abs(v) >= 1000.0]
        if tokens:
            return float(tokens[-1])
    return None


def _resolve_2072_triplet_permutation(
    revenus_bruts: float | None,
    frais_hors_interets: float | None,
    interets: float | None,
    revenu_net: float | None,
    *,
    annex_ref: dict[str, float] | None = None,
) -> tuple[float | None, float | None, float | None, bool]:
    """
    Disambiguate (frais, interets, revenu_net). Several permutations can satisfy RB-FC-IE=RN.

    - Si le triplet courant est arithmétiquement cohérent et aucune annexe fiable ne le contredit,
      on le garde (évite les régressions type 2072_clean_01 où le RN est le plus grand poste).
    - Sinon on aligne sur les totaux annexe (quote-parts) ou, à défaut, on énumère les permutations.
    """
    if not all(isinstance(v, (int, float)) for v in [revenus_bruts, frais_hors_interets, interets, revenu_net]):
        return frais_hors_interets, interets, revenu_net, False
    rb = float(revenus_bruts)
    fc = float(frais_hors_interets)
    ie = float(interets)
    rn = float(revenu_net)
    tol_arith = 5.0
    tol_fc, tol_ie, tol_rn = 120.0, 25.0, 120.0
    orig = (fc, ie, rn)

    def _arith(a: float, b: float, c: float) -> bool:
        return abs((rb - a - b) - c) <= tol_arith

    def _annex_ok(ref: dict[str, float]) -> tuple[bool, float, float, float, float]:
        fc_a = float(ref.get("frais_charges_hors_interets") or 0.0)
        ie_a = float(ref.get("interets_emprunts") or 0.0)
        rn_a = float(ref.get("revenu_net_foncier") or 0.0)
        rb_a = float(ref.get("revenus_bruts") or 0.0)
        ok = (
            fc_a > 0.0
            and abs(rn_a) > 1e-6
            and ie_a >= 0.0
            and (rb_a <= 0.0 or abs(rb_a - rb) <= max(200.0, abs(rb) * 0.02))
            and _is_2072_arithmetically_coherent(rb, fc_a, ie_a, rn_a)
        )
        return ok, fc_a, ie_a, rn_a, rb_a

    annex_ok, fc_a, ie_a, rn_a, _rb_a = (
        _annex_ok(annex_ref) if annex_ref else (False, 0.0, 0.0, 0.0, 0.0)
    )

    def _matches_annex(a: float, b: float, c: float) -> bool:
        return (
            abs(a - fc_a) <= tol_fc
            and abs(b - ie_a) <= tol_ie
            and abs(c - rn_a) <= tol_rn
        )

    current_arith_ok = _arith(fc, ie, rn)
    if current_arith_ok and annex_ok:
        if _matches_annex(fc, ie, rn):
            return fc, ie, rn, False
        # Annexe contredit le triplet courant malgré équation OK → permuter.
    elif current_arith_ok and not annex_ok:
        # Sans annexe fiable, ne pas permuter : plusieurs assignations peuvent vérifier l'équation.
        return fc, ie, rn, False

    triplets = [
        (float(a), float(b), float(c))
        for a, b, c in itertools.permutations([fc, ie, rn], 3)
        if _arith(a, b, c)
    ]
    if not triplets:
        return fc, ie, rn, False
    uniq = list(dict.fromkeys(triplets))

    if annex_ok:
        scored: list[tuple[float, tuple[float, float, float]]] = []
        for a, b, c in uniq:
            if not _matches_annex(a, b, c):
                continue
            err = (
                abs(a - fc_a) / max(fc_a, 1.0)
                + abs(b - ie_a) / max(ie_a, 1.0)
                + abs(c - rn_a) / max(abs(rn_a), 1.0)
            )
            scored.append((err, (a, b, c)))
        if scored:
            scored.sort(key=lambda x: x[0])
            t = scored[0][1]
            return t[0], t[1], t[2], t != orig

    # Sans annexe : intérêts = plus petit des trois (souvent vrai 2072) si une seule permutation le vérifie
    vals = sorted({round(x, 2) for x in (fc, ie, rn)})
    ie_min_candidates = [tr for tr in uniq if abs(tr[1] - vals[0]) <= 1e-6]
    if len(ie_min_candidates) == 1:
        t = ie_min_candidates[0]
        return t[0], t[1], t[2], t != orig
    if len(uniq) == 1:
        t = uniq[0]
        return t[0], t[1], t[2], t != orig
    t = uniq[0]
    return t[0], t[1], t[2], t != orig


def _extract_2072_totals_from_quote_part_blocks(text: str) -> dict[str, float]:
    """
    Parse 2072 annexe-2 quote-part blocks when table labels/values are vertically shifted.
    Expected sequence per associate: revenus bruts, frais/charges, intérêts, revenu net.
    """
    lines = text.splitlines()
    marker = re.compile(r"dont\s+quote[\- ]part\s+de\s+r[ée]novation", re.IGNORECASE)
    blocks: list[tuple[float, float, float, float]] = []
    for i, raw in enumerate(lines):
        if not marker.search(raw):
            continue
        window = lines[i : min(len(lines), i + 35)]
        amounts: list[float] = []
        for scan in window:
            v = _clean_amount_candidate(_to_float_fr(scan.strip()))
            if isinstance(v, float) and abs(v) >= 1.0:
                amounts.append(v)
        # Drop tiny labels-like noise (13, 31) before the actual 4 financial values.
        amounts = [a for a in amounts if a >= 10.0]
        if len(amounts) < 4:
            continue
        rb = fc = ie = rn = None
        # rb: first large amount
        for a in amounts:
            if a >= 1000.0:
                rb = a
                break
        if rb is None:
            continue
        # fc: next large amount
        started = False
        for a in amounts:
            if not started:
                if a == rb:
                    started = True
                continue
            if a >= 1000.0:
                fc = a
                break
        if fc is None:
            continue
        # rn: first medium amount after fc (often OCR keeps RN but drops IE line value).
        started_fc = False
        for a in amounts:
            if not started_fc:
                if a == fc:
                    started_fc = True
                continue
            if 100.0 <= a <= rb:
                rn = a
                break
        if rn is None:
            continue
        # ie: prefer algebraic closure at associate level (RB - FC - RN), robust when line 20 value is missing.
        ie = rb - fc - rn
        if ie < 0.0:
            continue
        if rb < 100.0 or fc < 100.0:
            continue
        if ie > max(1000.0, rb * 0.25):
            continue
        if rn > rb:
            continue
        blocks.append((rb, fc, ie, rn))
    # Deduplicate repeated OCR echoes of the same associate block.
    uniq = list(dict.fromkeys(blocks))
    if not uniq:
        return {}
    return {
        "revenus_bruts": sum(b[0] for b in uniq),
        "frais_charges_hors_interets": sum(b[1] for b in uniq),
        "interets_emprunts": sum(b[2] for b in uniq),
        "revenu_net_foncier": sum(b[3] for b in uniq),
    }


def _count_2072_quote_part_blocks(text: str) -> int:
    marker = re.compile(r"dont\s+quote[\- ]part\s+de\s+r[ée]novation", re.IGNORECASE)
    return sum(1 for line in text.splitlines() if marker.search(line))


def _plausible_2072_interets_candidate(value: float, revenus_bruts: float | None) -> bool:
    if abs(value) < THRESHOLDS["amount_min_low"]:
        return False
    if revenus_bruts is not None and isinstance(revenus_bruts, (int, float)):
        rb = abs(float(revenus_bruts))
        if rb > 0 and abs(value) > max(rb * 2.0, THRESHOLDS["amount_abs_hard_cap"]):
            return False
    elif abs(value) > THRESHOLDS["amount_abs_hard_cap"]:
        return False
    return True


def _plausible_2072_frais_candidate(value: float, revenus_bruts: float | None) -> bool:
    # Frais hors intérêts peuvent être nuls (case vide légitime), ou positifs.
    # On refuse les valeurs négatives et les montants aberrants.
    if value < 0.0:
        return False
    if revenus_bruts is not None and isinstance(revenus_bruts, (int, float)):
        rb = abs(float(revenus_bruts))
        if rb > 0 and value > max(rb * 2.0, THRESHOLDS["amount_abs_hard_cap"]):
            return False
    elif value > THRESHOLDS["amount_abs_hard_cap"]:
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
    # Hard cap to reject merged multi-column OCR tokens (e.g. "340377359429").
    if abs(value) > THRESHOLDS["amount_abs_hard_cap"]:
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
    return bool(
        re.search(r"\b(adresse|dénomination|denomination|nom|date|associ[ée]s?)\b", v)
        and not re.search(r"\d|_|[a-z]{3,}", v)
    )


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


def _value(field_dict: dict[str, Any]) -> Any:
    """Compat helper: return normalized field value from field dict."""
    if not isinstance(field_dict, dict):
        return None
    return field_dict.get("value")


def _extract_common_fields(text: str) -> dict[str, dict[str, Any]]:
    exercice = _extract_first(r"(?:exercice|exercice clos le)\s*[:\-]?\s*([0-9]{4})", text)
    date_cloture = _extract_first(
        r"(?:clos le|clôture|date de clôture)\s*[:\-]?\s*([0-3]?\d[\/\-][0-1]?\d[\/\-][12]\d{3})",
        text,
    )
    societe_raw = _extract_first(
        r"(?:dénomination|denomination|raison sociale|société|societe)\s*[:\-]?"
        r"\s*([A-Z0-9 _.\-]{3,80})",
        text,
    )
    societe = _clean_company_label(societe_raw)
    return {
        "societe": _field(societe, 0.75 if societe else 0.0, "header:societe"),
        "exercice": _field(exercice, 0.8 if exercice else 0.0, "header:exercice"),
        "date_cloture": _field(date_cloture, 0.82 if date_cloture else 0.0, "header:date_cloture"),
    }


def _clean_company_label(value: str | None) -> str | None:
    """Normalize/reject noisy company labels extracted from OCR headers."""
    if not value:
        return None
    s = _norm_spaces(str(value)).strip(" _-:.")
    if not s:
        return None
    up = s.upper()
    if "A POUR OBJET" in up:
        return None
    generic = {
        "GENERALE",
        "SOCIETE",
        "SOCIÉTÉ",
        "RAISON SOCIALE",
        "ENTREPRISE",
        "COMPAGNIE",
        "DE",
        "DU",
        "DES",
        "DE L",
        "DE LA",
    }
    # Reject too generic/noisy single labels (e.g. "GENERALE_", "DE L")
    if up in generic:
        return None
    if len(up) < 4:
        return None
    return s


def _coerce_component_amount(value: float | None, total_passif: float | None) -> float | None:
    """Reject implausible component amounts (often account-code leakage)."""
    if value is None:
        return None
    v = float(value)
    if v < 0:
        return None
    if isinstance(total_passif, (int, float)) and float(total_passif) > 0:
        # A passif component should not dwarf total passif.
        passif_cap = float(total_passif) * THRESHOLDS["component_vs_passif_ratio_cap"]
        if v > passif_cap:
            return None
    # Hard cap against OCR-account-code confusion (e.g. 40100000, 45510000).
    if v >= THRESHOLDS["component_abs_hard_cap"]:
        return None
    return v


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
    # Strong hint on plaquettes: "TOTAL GENERAL ACTIF/PASSIF" lines.
    tg_actif, tg_actif_src = _extract_total_general_from_line(
        text, r"total\s+g[ée]n[ée]ral.{0,16}actif", min_amount=100.0
    )
    tg_passif, tg_passif_src = _extract_total_general_from_line(
        text, r"total\s+g[ée]n[ée]ral.{0,16}passif", min_amount=100.0
    )
    if isinstance(tg_passif, float):
        total_passif = tg_passif
        total_passif_src = tg_passif_src
    if isinstance(tg_actif, float):
        total_actif = tg_actif
        total_actif_src = tg_actif_src
    # On mixed-column plaquettes, ACTIF total-general line may expose brut/amort/net.
    # PASSIF total-general token is usually the most stable year-N target.
    if isinstance(total_actif, (int, float)) and isinstance(total_passif, (int, float)):
        gap = abs(float(total_actif) - float(total_passif))
        tol = max(500.0, abs(float(total_passif)) * 0.03)
        if gap > tol and isinstance(tg_passif, float):
            total_actif = float(total_passif)
            total_actif_src = "fallback:align_actif_to_total_general_passif"
    # If one side missing and explicit total general exists on the other side, align.
    if total_actif is None and isinstance(total_passif, (int, float)):
        total_actif = float(total_passif)
        total_actif_src = "fallback:total_general_passif_align_actif"
    if total_passif is None and isinstance(total_actif, (int, float)):
        total_passif = float(total_actif)
        total_passif_src = "fallback:total_general_actif_align_passif"
    # Column-aware fallback for plaquettes: keep independent line tokens (avoid N/N-1 concat).
    actif_tokens = _extract_amount_tokens_for_keyword_lines(
        text,
        r"total\s+g[ée]n[ée]ral.{0,14}actif|total.{0,10}actif",
        min_amount=100.0,
    )
    passif_tokens = _extract_amount_tokens_for_keyword_lines(
        text,
        r"total\s+g[ée]n[ée]ral.{0,14}passif|total.{0,10}passif",
        min_amount=100.0,
    )
    actif_picked = _pick_total_value_from_tokens(actif_tokens)
    passif_picked = _pick_total_value_from_tokens(passif_tokens)
    common_totals = sorted({int(round(a)) for a in actif_tokens} & {int(round(p)) for p in passif_tokens})
    if common_totals:
        aligned_total = float(common_totals[-1])
        total_actif = aligned_total
        total_passif = aligned_total
        total_actif_src = "fallback:aligned_total_actif_passif_common_token"
        total_passif_src = "fallback:aligned_total_actif_passif_common_token"
    elif isinstance(actif_picked, float) and isinstance(passif_picked, float):
        # Both lines resolved: prefer explicit N-column values over global regex grabs.
        if abs(actif_picked - passif_picked) <= max(500.0, abs(passif_picked) * 0.03):
            total_actif = actif_picked
            total_passif = passif_picked
            total_actif_src = "fallback:aligned_total_actif_token_heuristic"
            total_passif_src = "fallback:aligned_total_passif_token_heuristic"
    else:
        if total_actif is None:
            if isinstance(actif_picked, float):
                total_actif = actif_picked
                total_actif_src = "fallback:actif_total_token_heuristic"
        if total_passif is None:
            if isinstance(passif_picked, float):
                total_passif = passif_picked
                total_passif_src = "fallback:passif_total_token_heuristic"
    # Plaquettes OCR bruitées: quand les libellés "total actif/passif" sont cassés,
    # le total général apparaît souvent au moins deux fois (actif + passif).
    if total_actif is None or total_passif is None:
        amount_counter: dict[int, int] = {}
        for m in re.findall(
            (
                r"([0-9Oo]{1,3}(?:[ \u00a0][0-9Oo]{3})+(?:[.,][0-9Oo]{2})?"
                r"|[0-9Oo]{4,}(?:[.,][0-9Oo]{2})?)"
            ),
            text,
            flags=re.IGNORECASE,
        ):
            v = _clean_amount_candidate(_to_float_fr(m))
            if not isinstance(v, float):
                continue
            if v < 1000.0 or v > 1_000_000_000.0:
                continue
            key = int(round(v))
            amount_counter[key] = amount_counter.get(key, 0) + 1
        duplicated = [(k, c) for k, c in amount_counter.items() if c >= 2]
        if duplicated:
            duplicated.sort(key=lambda x: (x[1], x[0]), reverse=True)
            candidate = float(duplicated[0][0])
            if total_actif is None:
                total_actif = candidate
                total_actif_src = "fallback:duplicated_total_amount"
            if total_passif is None:
                total_passif = candidate
                total_passif_src = "fallback:duplicated_total_amount"
    if total_actif is None and isinstance(total_passif, (int, float)):
        total_actif = float(total_passif)
        total_actif_src = "fallback:passif_equals_actif"
    if total_passif is None and isinstance(total_actif, (int, float)):
        total_passif = float(total_actif)
        total_passif_src = "fallback:actif_equals_passif"
    # Final safeguard: on plaquette totals, keep bilan balanced when passif total-general is explicit.
    if isinstance(total_actif, (int, float)) and isinstance(total_passif, (int, float)):
        final_gap = abs(float(total_actif) - float(total_passif))
        final_tol = max(500.0, abs(float(total_passif)) * 0.03)
        if final_gap > final_tol and "total_general" in str(total_passif_src):
            total_actif = float(total_passif)
            total_actif_src = "fallback:final_align_actif_to_passif_total_general_src"

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
    # Prefer line-token extraction first for N/N-1 layouts (avoid cross-line capture).
    if capitaux_propres is None:
        capitaux_propres, capitaux_propres_src = _extract_first_amount_token_from_keyword_line_excluding(
            text,
            r"capitaux?\s+propres|situation\s+nette|fonds?\s+propres",
            min_amount=100.0,
            exclude_regex=r"r[ée]sultat|b[ée]n[ée]fice|perte",
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

    # Prefer per-line token extraction to avoid N/N-1 and neighbor-line collisions.
    dettes_fin_val, _ = _extract_first_amount_token_from_keyword_line(
        text,
        r"dettes?\s+financi|emprunts?\s+et\s+dettes?",
        min_amount=50.0,
    )
    if dettes_fin_val is None:
        dettes_fin_val = _extract_financial_amount_for_label(
            text, r"dettes?\s+financi", min_amount=50.0
        )
    if dettes_fin_val is None:
        dettes_fin_val = _extract_first_amount_from_patterns(
            text,
            [
                r"dettes?\s*:\s*.*?emprunts?",
                r"emprunts?\s+[ée]tablissements?\s+de\s+cr[ée]dit",
                r"emprunts?\s+bancaires?",
                r"^\s*emprunts?\s*:",
                r"dettes?\s+aupr[eè]s?\s+des?\s+[ée]tablissements?\s+de\s+cr[ée]dit",
            ],
            min_amount=50.0,
        )
    dettes_four_val, _ = _extract_first_amount_token_from_keyword_line_excluding(
        text,
        r"dettes?\s+fournisseurs?|fournisseurs?",
        min_amount=50.0,
        exclude_regex=r"avances?\s+et\s+acomptes?|acomptes?\s+re[cç]us",
    )
    if dettes_four_val is None:
        dettes_four_val = _extract_financial_amount_for_label(
            text, r"dettes?\s+fournisseurs?", min_amount=50.0
        )
    if dettes_four_val is None:
        dettes_four_val = _extract_first_amount_from_patterns(
            text,
            [
                r"dettes?\s*:\s*.*?fournisseurs?",
                r"fournisseurs?\s*:",
            ],
            min_amount=50.0,
        )
    if dettes_four_val is None:
        dettes_four_val, _ = _extract_amount_from_lines_with_keyword(
            text,
            r"fournisseurs?",
            min_amount=50.0,
        )
    dettes_fin_val = _coerce_component_amount(dettes_fin_val, total_passif)
    dettes_four_val = _coerce_component_amount(dettes_four_val, total_passif)
    # Guardrail: avoid duplicated debt values when supplier line provides a distinct token.
    if (
        isinstance(dettes_fin_val, (int, float))
        and isinstance(dettes_four_val, (int, float))
        and abs(float(dettes_fin_val) - float(dettes_four_val)) < 1e-6
    ):
        fournisseurs_tokens = _extract_amount_tokens_for_keyword_lines(
            text, r"dettes?\s+fournisseurs?|fournisseurs?", min_amount=50.0, max_lines=8
        )
        for tok in fournisseurs_tokens:
            if abs(float(tok) - float(dettes_fin_val)) > 1e-6:
                cand = _coerce_component_amount(float(tok), total_passif)
                if isinstance(cand, float):
                    dettes_four_val = cand
                    break
    # Conservative: small plaquettes sometimes list only equity + two debt lines under passif.
    if (
        capitaux_propres is None
        and isinstance(total_passif, (int, float))
        and dettes_fin_val is not None
        and dettes_four_val is not None
    ):
        cand = float(total_passif) - float(dettes_fin_val) - float(dettes_four_val)
        s = float(dettes_fin_val) + float(dettes_four_val) + cand
        if cand >= 100.0 and abs(s - float(total_passif)) <= max(
            500.0, abs(float(total_passif)) * 0.04
        ):
            capitaux_propres = cand
            capitaux_propres_src = "fallback:passif_minus_dettes_fin_et_fournisseurs"

    if capitaux_propres is None:
        capitaux_propres, capitaux_propres_src = _sum_fr_capital_account_lines(text)
    # Plaquettes: "CAPITAUX PROPRES (I) ... TOTAL (I): X"
    m_cp = re.search(
        (
            r"capitaux?\s+propres.{0,260}?total\s*(?:\(?i\)?)?\s*[:\-]?"
            r"\s*([0-9Oo][0-9Oo \t\u00a0.,]{0,30})"
        ),
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if m_cp:
        cand = _to_float_fr(m_cp.group(1))
        if isinstance(cand, float) and abs(cand) >= 100.0:
            should_replace = capitaux_propres is None or (
                isinstance(capitaux_propres, (int, float))
                and float(cand) > float(capitaux_propres) * 1.5
            )
            # Prefer block total over a single "capital:" line when it is clearly larger.
            if should_replace:
                capitaux_propres = cand
                capitaux_propres_src = "label:block_total_capitaux_propres_i"

    resultat_exercice, resultat_exercice_src = _extract_first_amount_with_source(
        text,
        [
            ("label:resultat_exercice", r"r[ée]sultat\s+de?\s+l[' ]?exercice"),
            ("label:benefice_perte", r"b[ée]n[ée]fice|perte\s+de\s+l[' ]?exercice"),
        ],
        min_amount=50.0,
    )
    if resultat_exercice is None:
        resultat_exercice, resultat_exercice_src = _extract_first_amount_token_from_keyword_line(
            text,
            r"r[ée]sultat\s+de?\s+l[' ]?exercice|b[ée]n[ée]fice\s+ou\s+perte|perte\s+de\s+l[' ]?exercice",
            min_amount=50.0,
        )
    # Anti-collision on noisy "100" lines when totals indicate large company amounts.
    passif_ref = float(total_passif) if isinstance(total_passif, (int, float)) else None
    if isinstance(passif_ref, float) and passif_ref >= 10_000.0:
        if isinstance(capitaux_propres, (int, float)) and abs(float(capitaux_propres)) <= 150.0:
            alt, alt_src = _extract_first_amount_token_from_keyword_line(
                text,
                r"situation\s+nette|capitaux?\s+propres|fonds?\s+propres",
                min_amount=200.0,
            )
            capitaux_propres = alt
            capitaux_propres_src = alt_src if alt is not None else "missing"
        if isinstance(resultat_exercice, (int, float)) and abs(float(resultat_exercice)) <= 150.0:
            alt, alt_src = _extract_first_amount_token_from_keyword_line(
                text,
                r"r[ée]sultat\s+de?\s+l[' ]?exercice|b[ée]n[ée]fice\s+ou\s+perte|perte\s+de\s+l[' ]?exercice",
                min_amount=200.0,
            )
            resultat_exercice = alt
            resultat_exercice_src = alt_src if alt is not None else "missing"
    # Guardrail: if equity and result are identical on large docs, prefer dedicated result line
    # and force equity from explicit equity labels excluding result lines.
    if (
        isinstance(passif_ref, float)
        and passif_ref >= 10_000.0
        and isinstance(capitaux_propres, (int, float))
        and isinstance(resultat_exercice, (int, float))
        and abs(float(capitaux_propres) - float(resultat_exercice)) < 1e-6
    ):
        res_alt, res_alt_src = _extract_first_amount_token_from_keyword_line(
            text,
            r"r[ée]sultat\s+de?\s+l[' ]?exercice|b[ée]n[ée]fice\s+ou\s+perte|perte\s+de\s+l[' ]?exercice",
            min_amount=50.0,
        )
        cp_alt, cp_alt_src = _extract_first_amount_token_from_keyword_line_excluding(
            text,
            r"capitaux?\s+propres|situation\s+nette|fonds?\s+propres",
            min_amount=100.0,
            exclude_regex=r"r[ée]sultat|b[ée]n[ée]fice|perte",
        )
        if isinstance(res_alt, float):
            resultat_exercice = res_alt
            resultat_exercice_src = res_alt_src
        if isinstance(cp_alt, float):
            capitaux_propres = cp_alt
            capitaux_propres_src = cp_alt_src

    immobilisations_val = _extract_amount_for_label(text, r"immobilisations")
    if immobilisations_val is None:
        immobilisations_val, _ = _extract_amount_from_lines_with_keyword(
            text, r"immobilisations?.{0,20}net", min_amount=100.0
        )

    creances_val = _extract_amount_for_label(text, r"créances|creances")
    if creances_val is None:
        creances_val, _ = _extract_amount_from_lines_with_keyword(
            text, r"cr[ée]ances?.{0,20}clients?|clients?.{0,20}cr[ée]ances?", min_amount=100.0
        )

    disponibilites_val = _extract_amount_for_label(text, r"disponibilités|disponibilites")
    if disponibilites_val is None:
        disponibilites_val, _ = _extract_amount_from_lines_with_keyword(
            text, r"disponibilit[ée]s?|banque|caisse", min_amount=100.0
        )

    return {
        **_extract_common_fields(text),
        "total_actif": _field(
            total_actif, 0.87 if total_actif is not None else 0.0, total_actif_src
        ),
        "total_passif": _field(
            total_passif, 0.87 if total_passif is not None else 0.0, total_passif_src
        ),
        "immobilisations": _field(
            immobilisations_val,
            0.78 if immobilisations_val is not None else 0.0,
            "fallback:immobilisations",
        ),
        "creances": _field(
            creances_val,
            0.78 if creances_val is not None else 0.0,
            "fallback:creances",
        ),
        "disponibilites": _field(
            disponibilites_val,
            0.78 if disponibilites_val is not None else 0.0,
            "fallback:disponibilites",
        ),
        "dettes_financieres": _field(
            dettes_fin_val, 0.76 if dettes_fin_val is not None else 0.0, "label:dettes financieres"
        ),
        "dettes_fournisseurs": _field(
            dettes_four_val,
            0.76 if dettes_four_val is not None else 0.0,
            "label:dettes fournisseurs",
        ),
        "capitaux_propres": _field(
            capitaux_propres, 0.8 if capitaux_propres is not None else 0.0, capitaux_propres_src
        ),
        "resultat_exercice": _field(
            resultat_exercice, 0.8 if resultat_exercice is not None else 0.0, resultat_exercice_src
        ),
    }


def _extract_compte_resultat(text: str) -> dict[str, dict[str, Any]]:
    scan_cr = text
    chiffre_affaires = _extract_amount_for_label(text, r"chiffre\s+d[' ]affaires")
    chiffre_affaires_src = "label:chiffre affaires"
    if chiffre_affaires is None:
        ventes = _extract_first_amount_from_patterns(
            scan_cr,
            [
                r"ventes?\s+de\s+marchandises?",
                r"ventes?",
            ],
            min_amount=50.0,
        )
        services = _extract_first_amount_from_patterns(
            scan_cr,
            [
                r"production\s+vendue.{0,20}services?",
                r"prestations?\s+de\s+services?",
            ],
            min_amount=50.0,
        )
        if isinstance(ventes, (int, float)) and isinstance(services, (int, float)):
            chiffre_affaires = float(ventes) + float(services)
            chiffre_affaires_src = "fallback:ventes_plus_services"
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
    if resultat_net is None:
        resultat_net = _extract_financial_amount_for_label(
            scan_cr,
            r"b[ée]n[ée]fice\s+ou\s+perte",
            min_amount=50.0,
        )
        if resultat_net is not None:
            resultat_net_src = "label:benefice_ou_perte"

    return {
        **_extract_common_fields(text),
        "chiffre_affaires": _field(
            chiffre_affaires,
            0.86 if chiffre_affaires is not None else 0.0,
            chiffre_affaires_src if chiffre_affaires is not None else "label:chiffre affaires",
        ),
        "autres_produits": _field(
            _extract_amount_for_label(text, r"autres?\s+produits"), 0.76, "label:autres produits"
        ),
        "charges_externes": _field(
            charges_externes, 0.76 if charges_externes is not None else 0.0, charges_externes_src
        ),
        "impots_taxes": _field(
            _extract_amount_for_label(text, r"imp[oô]ts?\s+et\s+taxes"), 0.76, "label:impots taxes"
        ),
        "charges_financieres": _field(
            _extract_amount_for_label(text, r"charges?\s+financi"),
            0.76,
            "label:charges financieres",
        ),
        "resultat_exploitation": _field(
            resultat_exploitation,
            0.82 if resultat_exploitation is not None else 0.0,
            resultat_exploitation_src,
        ),
        "resultat_courant": _field(
            resultat_courant, 0.8 if resultat_courant is not None else 0.0, resultat_courant_src
        ),
        "resultat_net": _field(
            resultat_net, 0.84 if resultat_net is not None else 0.0, resultat_net_src
        ),
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
    total_actif = _value(bilan.get("total_actif", {}))
    total_passif = _value(bilan.get("total_passif", {}))
    chiffre_affaires = _value(cr.get("chiffre_affaires", {}))
    resultat_exercice = _value(bilan.get("resultat_exercice", {}))
    resultat_net = _value(cr.get("resultat_net", {}))

    if total_actif is None:
        total_actif = _extract_first_amount_from_patterns(
            text,
            [
                r"total\s+g[ée]n[ée]ral\s+actif",
                r"total\s+actif",
                r"actif\s+total",
            ],
            min_amount=100.0,
        )
    if total_passif is None:
        total_passif = _extract_first_amount_from_patterns(
            text,
            [
                r"total\s+g[ée]n[ée]ral\s+passif",
                r"total\s+passif",
                r"passif\s+total",
            ],
            min_amount=100.0,
        )
    if total_actif is None and isinstance(total_passif, (int, float)):
        total_actif = float(total_passif)
    if total_passif is None and isinstance(total_actif, (int, float)):
        total_passif = float(total_actif)

    if chiffre_affaires is None:
        chiffre_affaires = _extract_first_amount_from_patterns(
            text,
            [
                r"chiffre\s+d[' ]affaires",
                r"ventes?\s+de\s+marchandises?",
                r"production\s+vendue.{0,20}services?",
            ],
            min_amount=50.0,
        )
    if resultat_exercice is None:
        resultat_exercice = _extract_first_amount_from_patterns(
            text,
            [
                r"r[ée]sultat\s+de?\s+l[' ]?exercice",
                r"b[ée]n[ée]fice\s+net",
            ],
            min_amount=50.0,
        )
    if resultat_net is None and isinstance(resultat_exercice, (int, float)):
        resultat_net = float(resultat_exercice)

    return {
        "liasse_type": _field("2065_2033", 0.9, "liasse:is_simplifiee"),
        "exercice": _field(exercice, 0.85 if exercice else 0.0, "header:exercice"),
        "regime_imposition": _field(regime or "rsi", 0.75 if regime else 0.55, "header:regime"),
        "total_actif": _field(
            total_actif, 0.84 if total_actif is not None else 0.0, "liasse:total_actif"
        ),
        "total_passif": _field(
            total_passif, 0.84 if total_passif is not None else 0.0, "liasse:total_passif"
        ),
        "chiffre_affaires": _field(
            chiffre_affaires,
            0.82 if chiffre_affaires is not None else 0.0,
            "liasse:chiffre_affaires",
        ),
        "resultat_exercice": _field(
            resultat_exercice,
            0.82 if resultat_exercice is not None else 0.0,
            "liasse:resultat_exercice",
        ),
        "resultat_net": _field(
            resultat_net, 0.82 if resultat_net is not None else 0.0, "liasse:resultat_net"
        ),
    }


def _extract_2072(text: str) -> dict[str, dict[str, Any]]:
    header_zone = _extract_2072_header_zone(text)
    results_zone = _extract_2072_results_zone(text)
    immeubles = _extract_2072_immeubles_table(text)
    associes = _extract_2072_associes_table(text)

    # V3 focus: reliably fill only critical fields first.
    denom = _extract_value_near_label(
        header_zone,
        r"d[ée]n[o0]mination\s+de\s+(?:la|1a|l[4a])\s+s[o0]ci[ée]t[ée]|d[ée]n[o0]mination\s+sci",
        r"([A-Z0-9_][A-Z0-9_.\- ]{2,120})",
    ) or _extract_value_near_label(
        text,
        r"d[ée]n[o0]mination\s+de\s+(?:la|1a|l[4a])\s+s[o0]ci[ée]t[ée]|d[ée]n[o0]mination\s+sci",
        r"([A-Z0-9_][A-Z0-9_.\- ]{2,120})",
    )
    if not denom:
        sci_line = _extract_first(
            r"^\s*(SCI\s+[A-Z0-9_.\- ]{2,120})\s*$", text, flags=re.IGNORECASE | re.MULTILINE
        )
        if sci_line:
            denom = _norm_spaces(sci_line)

    date_cloture = _extract_first_date_from_patterns(
        header_zone + "\n" + text,
        [
            r"(?:date\s+de\s+cl[ôo]ture(?:\s+de\s+l[' ]exercice)?)\s*[:\-]?"
            r"\s*([0-3]?\d[\/\-][0-1]?\d[\/\-][12]\d{3})",
            r"(?:exercice\s+clos\s+le)\s*[:\-]?\s*([0-3]?\d[\/\-][0-1]?\d[\/\-][12]\d{3})",
            r"(?:soc5).{0,40}([0-3]?\d[\/\-][0-1]?\d[\/\-][12]\d{3})",
            r"(?:cl[ôo]ture).{0,40}([0-3]?\d[\/\-][0-1]?\d[\/\-][12]\d{3})",
        ],
    )
    if not date_cloture:
        year = _extract_first(
            r"(?:exercice)\s*clos\s*le\s*[:\-]?\s*[0-3]?\d[\/\-][0-1]?\d[\/\-]([12]\d{3})", text
        )
        if year:
            date_cloture = f"31/12/{year}"
    if not date_cloture:
        date_cloture = _extract_value_from_anchor_window(
            text,
            anchor_regex=r"(?:soc5|date\s+de\s+cl[ôo]ture\s+de\s+l[' ]exercice)",
            value_regex=r"\b([0-3]?\d[\/\-][0-1]?\d[\/\-][12]\d{3})\b",
            window_lines=5,
        )
    date_cloture = _normalize_2072_closure_date(date_cloture)
    nb_associes = _extract_first_int_from_patterns(
        header_zone + "\n" + text,
        [
            r"(?:n[o0]mbre\s+d[' ]ass[o0]ci[ée]s?)\s*[:\-]?\s*([0-9]{1,3})",
            r"(?:soc18).{0,20}([0-9]{1,3})",
        ],
    )
    if nb_associes is None:
        nb_associes_raw = _extract_value_from_anchor_window(
            text,
            anchor_regex=r"(?:soc18|nombre\s+d[' ]associ[ée]s?)",
            value_regex=r"\b([0-9]{1,3})\b",
            window_lines=3,
        )
        if nb_associes_raw:
            nb_candidate = _to_float_fr(nb_associes_raw)
            # Guardrail: ignore obvious address numbers accidentally captured in shifted OCR.
            if isinstance(nb_candidate, float) and 1.0 <= nb_candidate <= 50.0:
                nb_associes = nb_candidate
    if nb_associes is None:
        nb_associes_raw_wide = _extract_value_from_anchor_window(
            text,
            anchor_regex=r"(?:soc18|nombre\s+d[' ]associ[ée]s?)",
            value_regex=r"\b([1-9][0-9]?)\b",
            window_lines=80,
        )
        if nb_associes_raw_wide:
            nb_candidate_wide = _to_float_fr(nb_associes_raw_wide)
            if isinstance(nb_candidate_wide, float) and 1.0 <= nb_candidate_wide <= 50.0:
                nb_associes = nb_candidate_wide
    if not isinstance(nb_associes, (int, float)) or float(nb_associes) > 10.0:
        blocks_count = _count_2072_quote_part_blocks(text)
        if 1 <= blocks_count <= 50:
            nb_associes = float(blocks_count)
    revenus_bruts = _extract_first_amount_from_patterns(
        results_zone + "\n" + text,
        [
            r"revenus?\s+bruts?",
            r"montant\s+brut.{0,30}[lI!1]oyers?\s+encaiss",
        ],
        min_amount=100.0,
    )
    if revenus_bruts is None:
        revenus_bruts, _ = _extract_amount_from_lines_with_keyword(
            results_zone + "\n" + text,
            r"revenus?\s+bruts?|montant\s+brut.{0,40}[lI!1]oyers?\s+encaiss",
            min_amount=100.0,
        )
    scan_text = results_zone + "\n" + text
    if revenus_bruts is None:
        revenus_bruts, _ = _extract_2072_amount_from_anchor_window(
            scan_text,
            anchor_regex=r"revenus?\s+bruts?|total\s+des\s+lignes?.{0,15}5\s*\+\s*22",
            window_lines=10,
            min_amount=100.0,
        )
    frais_hors_interets = _extract_first_amount_from_patterns(
        results_zone + "\n" + text,
        [
            r"frais?\s+et\s+char[gq]es?.{0,40}hors.{0,20}[i1l]nt[eé]r[eéê]ts?",
            r"frais?\s+et\s+char[gq]es?.{0,40}autres?.{0,20}[i1l]nt[eé]r",
            r"frais?\s+de\s+gestion",
        ],
        min_amount=50.0,
    )
    if frais_hors_interets is None:
        frais_hors_interets, _ = _extract_2072_amount_from_anchor_window(
            scan_text,
            anchor_regex=r"frais?\s+et\s+char[gq]es?.{0,60}(?:autres?.{0,20}qu[' ]?int[eé]r[eéê]ts?|ligne\s*17\+18)",
            window_lines=10,
            min_amount=50.0,
        )
    strict_fc_17_18 = _extract_2072_amount_from_ligne_17_18_line(scan_text)
    if strict_fc_17_18 is not None:
        if frais_hors_interets is None or (
            isinstance(frais_hors_interets, (int, float))
            and isinstance(revenus_bruts, (int, float))
            and float(frais_hors_interets) < float(revenus_bruts) * 0.25
        ):
            frais_hors_interets = strict_fc_17_18
    interets = None
    interets_source = "missing"
    # Priorité aux lignes qui commencent explicitement par "Intérêts d'emprunts"
    strict_lines = []
    for raw in scan_text.splitlines():
        line = raw.strip()
        if re.search(r"^\s*[i1l]nt[eé]r[eéê]ts?\s+d[' ]emprun[tf]s?", line, re.IGNORECASE):
            strict_lines.append(line)
    for line in strict_lines:
        m_amt = re.search(
            r"([0-9Oo][0-9Oo \t\u00a0.,]{0,30})(?:\s*€|\s*EUR)?\s*$", line, re.IGNORECASE
        )
        if not m_amt:
            continue
        v = _clean_amount_candidate(_to_float_fr(m_amt.group(1)))
        if isinstance(v, float) and _plausible_2072_interets_candidate(
            v, float(revenus_bruts) if isinstance(revenus_bruts, (int, float)) else None
        ):
            interets = v
            interets_source = "label:interets_emprunts_strict_line"
            break
    if interets is None:
        interets, interets_source = _extract_first_amount_with_source(
            scan_text,
            [
                ("label:interets_emprunts", r"[i1l]nt[eé]r[eéê]ts?\s+d[' ]emprun[tf]s?"),
                ("label:interets_emprunts_alt", r"[i1l]nt[eé]r[eéê]ts?\s+des?\s+emprun[tf]s?"),
                ("label:interets_emprunt_singulier", r"[i1l]nt[eé]r[eéê]t\s+d[' ]emprun[tf]"),
                ("label:charge_interets", r"char[gq]es?.{0,10}d[' ][i1l]nt[eé]r[eéê]ts?"),
                ("label:dont_interets", r"dont.{0,20}[i1l]nt[eé]r[eéê]ts?"),
                ("label:emprunts_interets", r"emprun[tf]s?.{0,15}[i1l]nt[eé]r[eéê]ts?"),
            ],
            min_amount=50.0,
        )
    # Wide-gap OCR (amount far to the right of the label).
    if interets is None:
        for src_hint, pat in [
            ("label_wide:interets_emprunts", r"[i1l]nt[eé]r[eéê]ts?\s+d[' ]emprun[tf]s?"),
            ("label_wide:interets_des_emprunts", r"[i1l]nt[eé]r[eéê]ts?\s+des?\s+emprun[tf]s?"),
        ]:
            w = _extract_financial_amount_for_label_wide(
                scan_text, pat, max_gap=140, min_amount=50.0
            )
            if w is not None:
                interets, interets_source = w, src_hint
                break
    if interets is None:
        interets, interets_source = _extract_amount_from_lines_with_keyword(
            scan_text, r"[i1l]nt[eé]r[eéê]t.{0,12}emprun[tf]", min_amount=50.0
        )
    if interets is None:
        interets, interets_source = _extract_amount_after_keyword_multiline(
            scan_text,
            r"[i1l]nt[eé]r[eéê]ts?.{0,25}emprun[tf]|emprun[tf].{0,20}[i1l]nt[eé]r[eéê]t",
            min_amount=50.0,
        )
    if interets is None:
        interets, interets_source = _extract_2072_amount_from_anchor_window(
            scan_text,
            anchor_regex=r"(?:[i1l]nt[eé]r[eéê]ts?\s+d[' ]emprun[tf]s?|ligne\s*20)",
            window_lines=10,
            min_amount=1.0,
        )
    revenu_net = _extract_first_amount_from_patterns(
        scan_text,
        [
            r"revenu\s+net(?:\s+foncier)?",
            r"d[ée]f[i1]cit\s+net",
            r"revenu\s*\(\+\)|d[ée]f[i1]cit\s*\(\-\)",
        ],
        min_amount=100.0,
    )
    if revenu_net is None:
        revenu_net, _ = _extract_amount_from_lines_with_keyword(
            scan_text,
            r"revenu\s+net|d[ée]f[i1]cit|revenu\s*\(\+\)|d[ée]f[i1]cit\s*\(\-\)",
            min_amount=100.0,
        )
    if revenu_net is None:
        revenu_net, _ = _extract_2072_amount_from_anchor_window(
            scan_text,
            anchor_regex=r"(?:revenu\s+net.{0,30}r[ée]partir|revenu.*a\s*repartir|ligne\s*26)",
            window_lines=10,
            min_amount=100.0,
        )
    revenu_net_from_doc = revenu_net is not None

    # Fallbacks from annexes/tables when top-level labels are missing.
    immeubles_frais = sum(
        float(
            (x.get("frais_gestion") or 0.0)
            + (x.get("assurance") or 0.0)
            + (x.get("travaux") or 0.0)
            + (x.get("impositions") or 0.0)
        )
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
    rb_ok = isinstance(revenus_bruts, (int, float))
    rn_ok = isinstance(revenu_net, (int, float))
    rb_val = float(revenus_bruts) if rb_ok else None
    rn_val = float(revenu_net) if rn_ok else None

    if revenu_net_from_doc and rb_val is not None and rn_val is not None:
        # 1) Deduce missing frais_hors_interets when RB, RN, and interests are known.
        if frais_hors_interets is None:
            ie_val = float(interets) if isinstance(interets, (int, float)) else 0.0
            cand_frais = rb_val - ie_val - rn_val
            # Tolerance to absorb OCR rounding noise around zero.
            if abs(cand_frais) <= 1.0:
                cand_frais = 0.0
            if _plausible_2072_frais_candidate(cand_frais, rb_val):
                frais_hors_interets = cand_frais

        # 2) Deduce missing interests when RB, RN, and frais_hors_interets are known.
        if interets is None and isinstance(frais_hors_interets, (int, float)):
            cand_interets = rb_val - float(frais_hors_interets) - rn_val
            if abs(cand_interets) <= 1.0:
                cand_interets = 0.0
            if _plausible_2072_interets_candidate(cand_interets, rb_val):
                interets = cand_interets
                interets_source = "fallback:derived_rb_minus_frais_minus_revenu_net"

    if revenus_bruts is None:
        immeubles_rb = sum(float(x.get("revenus_bruts") or 0.0) for x in immeubles)
        associes_rb = sum(float(x.get("quote_part_revenus_bruts") or 0.0) for x in associes)
        if immeubles_rb > 0:
            revenus_bruts = immeubles_rb
        elif associes_rb > 0:
            revenus_bruts = associes_rb

    # Annex associates fallback (strict): use only if arithmetic remains coherent.
    associes_totals = {
        "revenus_bruts": sum(float(x.get("quote_part_revenus_bruts") or 0.0) for x in associes),
        "frais_charges_hors_interets": sum(float(x.get("quote_part_frais_charges") or 0.0) for x in associes),
        "interets_emprunts": sum(float(x.get("quote_part_interets_emprunts") or 0.0) for x in associes),
        "revenu_net_foncier": sum(float(x.get("quote_part_revenu_net") or 0.0) for x in associes),
    }
    if any(v <= 0.0 for v in associes_totals.values()):
        quote_part_block_totals = _extract_2072_totals_from_quote_part_blocks(text)
        for k, v in quote_part_block_totals.items():
            if associes_totals.get(k, 0.0) <= 0.0 and v > 0.0:
                associes_totals[k] = v
    associes_blocks_are_coherent = _is_2072_arithmetically_coherent(
        associes_totals.get("revenus_bruts"),
        associes_totals.get("frais_charges_hors_interets"),
        associes_totals.get("interets_emprunts"),
        associes_totals.get("revenu_net_foncier"),
    )

    if associes and (
        revenus_bruts is None
        or frais_hors_interets is None
        or interets is None
        or revenu_net is None
    ):
        rb_fb = float(revenus_bruts) if isinstance(revenus_bruts, (int, float)) else associes_totals["revenus_bruts"]
        fc_fb = (
            float(frais_hors_interets)
            if isinstance(frais_hors_interets, (int, float))
            else associes_totals["frais_charges_hors_interets"]
        )
        ie_fb = float(interets) if isinstance(interets, (int, float)) else associes_totals["interets_emprunts"]
        rn_fb = float(revenu_net) if isinstance(revenu_net, (int, float)) else associes_totals["revenu_net_foncier"]
        if _is_2072_arithmetically_coherent(rb_fb, fc_fb, ie_fb, rn_fb):
            if revenus_bruts is None and associes_totals["revenus_bruts"] > 0:
                revenus_bruts = associes_totals["revenus_bruts"]
            if frais_hors_interets is None and associes_totals["frais_charges_hors_interets"] > 0:
                frais_hors_interets = associes_totals["frais_charges_hors_interets"]
            if interets is None and associes_totals["interets_emprunts"] > 0:
                interets = associes_totals["interets_emprunts"]
                interets_source = "fallback:associes_interets_sum_validated"
            if revenu_net is None and associes_totals["revenu_net_foncier"] != 0:
                revenu_net = associes_totals["revenu_net_foncier"]
        elif associes_blocks_are_coherent:
            # If top-level RN is a likely collision artifact, prefer coherent annexe totals.
            if revenus_bruts is None and associes_totals["revenus_bruts"] > 0:
                revenus_bruts = associes_totals["revenus_bruts"]
            if frais_hors_interets is None and associes_totals["frais_charges_hors_interets"] > 0:
                frais_hors_interets = associes_totals["frais_charges_hors_interets"]
            if interets is None and associes_totals["interets_emprunts"] > 0:
                interets = associes_totals["interets_emprunts"]
                interets_source = "fallback:associes_interets_sum_validated"
            if isinstance(revenu_net, (int, float)) and isinstance(revenus_bruts, (int, float)):
                if abs(float(revenu_net) - float(revenus_bruts)) <= 1.0:
                    revenu_net = associes_totals["revenu_net_foncier"]
            elif revenu_net is None and associes_totals["revenu_net_foncier"] != 0:
                revenu_net = associes_totals["revenu_net_foncier"]

    # Anti-permutation: arithmetic alone is ambiguous; prefer annex totals, else FC=max / IE=min.
    annex_for_resolver: dict[str, float] | None = None
    if associes_blocks_are_coherent:
        annex_for_resolver = {
            **associes_totals,
            "revenus_bruts": float(revenus_bruts)
            if isinstance(revenus_bruts, (int, float))
            else float(associes_totals.get("revenus_bruts") or 0.0),
        }
    fixed_fc, fixed_ie, fixed_rn, perm_fixed = _resolve_2072_triplet_permutation(
        float(revenus_bruts) if isinstance(revenus_bruts, (int, float)) else None,
        float(frais_hors_interets) if isinstance(frais_hors_interets, (int, float)) else None,
        float(interets) if isinstance(interets, (int, float)) else None,
        float(revenu_net) if isinstance(revenu_net, (int, float)) else None,
        annex_ref=annex_for_resolver,
    )
    if perm_fixed:
        logger.warning(
            "extract_2072_triplet_permutation_corrected",
            revenus_bruts=revenus_bruts,
            old_frais=frais_hors_interets,
            old_interets=interets,
            old_revenu_net=revenu_net,
            new_frais=fixed_fc,
            new_interets=fixed_ie,
            new_revenu_net=fixed_rn,
        )
        frais_hors_interets = fixed_fc
        interets = fixed_ie
        revenu_net = fixed_rn
        interets_source = "fallback:permutation_corrected"

    if revenu_net is None and isinstance(revenus_bruts, (int, float)):
        fc = float(frais_hors_interets or 0.0)
        ie = float(interets or 0.0)
        revenu_net = revenus_bruts - fc - ie

    return {
        "denomination_sci": _field(denom, 0.92 if denom else 0.0, "header:denomination_societe"),
        "date_cloture_exercice": _field(
            date_cloture, 0.92 if date_cloture else 0.0, "header:date_cloture_exercice"
        ),
        "nombre_associes": _field(
            nb_associes, 0.9 if nb_associes is not None else 0.0, "header:nombre_associes"
        ),
        "revenus_bruts": _field(
            revenus_bruts, 0.9 if revenus_bruts is not None else 0.0, "resultats:revenus_bruts"
        ),
        "frais_charges_hors_interets": _field(
            frais_hors_interets,
            0.88 if frais_hors_interets is not None else 0.0,
            "resultats:frais_charges_hors_interets",
        ),
        "interets_emprunts": _field(
            interets, 0.88 if interets is not None else 0.0, interets_source
        ),
        "revenu_net_foncier": _field(
            revenu_net, 0.9 if revenu_net is not None else 0.0, "resultats:revenu_net_foncier"
        ),
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
        "presence_annexes_immeubles": _field(
            len(immeubles) > 0
            or bool(re.search(r"annexe\s*1|adresse\s+de\s+l[' ]immeuble", text, re.IGNORECASE)),
            0.84,
            "annexe:immeubles",
        ),
        "presence_annexes_associes_rf": _field(
            len(associes) > 0 or bool(re.search(r"annexe\s*2|quote[\- ]part", text, re.IGNORECASE)),
            0.84,
            "annexe:associes_revenus_fonciers",
        ),
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
        if (
            "revenus bruts" in low
            or "intérêts d'emprunt".lower() in low
            or "interets d'emprunt" in low
        ):
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
            "nombre_locaux": _to_float_fr(
                _extract_first(r"(?:nombre\s+de\s+locaux)\s*[:\-]?\s*([0-9]{1,4})", chunk)
            ),
            "revenus_bruts": _extract_amount_for_label(
                chunk, r"montant\s+brut.{0,25}loyers?\s+encaiss|revenus?\s+bruts?"
            ),
            "frais_gestion": _extract_amount_for_label(chunk, r"frais?\s+de\s+gestion"),
            "assurance": _extract_amount_for_label(chunk, r"primes?\s+d[' ]assurance|assurance"),
            "travaux": _extract_amount_for_label(
                chunk, r"travaux|d[ée]penses?\s+de\s+r[ée]paration"
            ),
            "impositions": _extract_amount_for_label(chunk, r"impositions?"),
            "interets_emprunts": ie_im,
            "amortissement": _extract_amount_for_label(chunk, r"amortissement"),
            "revenu_ou_deficit": _extract_amount_for_label(
                chunk, r"revenu\s*\(\+\)|d[ée]ficit\s*\(\-\)|revenu\s+net"
            ),
        }
        if any(v not in (None, "", 0.0) for k, v in entry.items() if k != "immeuble_id"):
            entries.append(entry)

    # Fallback: try to create entries from repeated addresses if chunk split failed.
    if not entries:
        zone = "\n".join(zone_lines)
        addrs = re.findall(
            r"(?:adresse\s+de\s+l[' ]immeuble)\s*[:\-]?\s*([^\n]{6,160})", zone, re.IGNORECASE
        )
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
    zone_lines = lines[start : min(len(lines), start + 420)]
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
            "date_naissance": _extract_first(
                r"(?:date\s+de\s+naissance)\s*[:\-]?\s*([0-3]?\d[\/\-][0-1]?\d[\/\-][12]\d{3})",
                chunk,
            ),
            "adresse": _extract_value_near_label(
                chunk,
                r"(?:\badresse\b)",
                r"([A-Z0-9_].{8,140})",
            ),
            "parts_detenues": _to_float_fr(
                _extract_first(r"(?:parts?\s+d[ée]tenues?)\s*[:\-]?\s*([0-9]{1,10})", chunk)
            ),
            "quote_part_revenus_bruts": _extract_amount_for_label(
                chunk, r"quote[\- ]part.{0,25}revenus?\s+bruts?"
            ),
            "quote_part_frais_charges": _extract_amount_for_label(
                chunk, r"quote[\- ]part.{0,25}frais?.{0,25}charges?"
            ),
            "quote_part_interets_emprunts": _extract_amount_for_label(
                chunk, r"quote[\- ]part.{0,25}int[eé]r[eê]ts?\s+d[' ]emprunts?"
            ),
            "quote_part_amortissement": _extract_amount_for_label(
                chunk, r"quote[\- ]part.{0,25}amortissement"
            ),
            "quote_part_revenu_net": _extract_amount_for_label(
                chunk, r"quote[\- ]part.{0,25}revenu\s+net|quote[\- ]part.{0,25}d[ée]ficit"
            ),
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


def _extract_releve_bancaire_fields(text: str) -> dict[str, dict[str, Any]]:
    bank = _extract_first(
        r"\b(BNP\s*PARIBAS|SOCIETE\s*GENERALE|CR[ÉE]DIT\s*AGRICOLE|LCL|CIC|"
        r"CAISSE\s+D[’' ]EPARGNE|BANQUE\s+POPULAIRE|HELLO\s+BANK|BOURSORAMA)\b",
        text,
    )
    titulaire = _extract_first(
        r"(?:titulaire|intitul[ée]\s+du\s+compte|nom\s+du\s+compte)\s*[:\-]?"
        r"\s*([A-Z][A-Z0-9 .'\-]{2,80})",
        text,
    )
    account_hint = _extract_first(
        r"(?:compte|n[°o]|num[ée]ro)\s*[:\-]?\s*([A-Z0-9]{4,34})",
        text,
    )
    period_start = _to_iso_date_fr(
        _extract_first(
            r"(?:p[ée]riode|du)\s*[:\-]?\s*([0-3]?\d[\/\-.][0-1]?\d[\/\-.][12]\d{3})\s*(?:au|\-)",
            text,
        )
    )
    period_end = _to_iso_date_fr(
        _extract_first(r"(?:au|jusqu[' ]au)\s*([0-3]?\d[\/\-.][0-1]?\d[\/\-.][12]\d{3})", text)
    )
    solde_initial = _extract_first_amount_from_patterns(
        text,
        [
            r"solde\s+initial",
            r"solde\s+au\s+d[ée]but",
            r"ancien\s+solde",
        ],
        min_amount=1.0,
    )
    solde_final = _extract_first_amount_from_patterns(
        text,
        [
            r"nouveau\s+solde",
            r"solde\s+final",
            r"solde\s+de\s+cl[oô]ture",
            r"solde\s+au\s+[0-3]?\d[\/\-.][0-1]?\d[\/\-.][12]\d{3}",
        ],
        min_amount=1.0,
    )
    titulaire_pseudo = "TITULAIRE_1" if titulaire else None
    compte_pseudo = "COMPTE_1" if account_hint else None
    return {
        "banque": _field(
            _norm_spaces(bank) if bank else None, 0.84 if bank else 0.0, "header:banque"
        ),
        "titulaire_compte_pseudo": _field(
            titulaire_pseudo, 0.8 if titulaire_pseudo else 0.0, "pseudo:titulaire"
        ),
        "compte_reference_pseudo": _field(
            compte_pseudo, 0.78 if compte_pseudo else 0.0, "pseudo:compte_reference"
        ),
        "periode_debut": _field(
            period_start, 0.82 if period_start else 0.0, "header:periode_debut"
        ),
        "periode_fin": _field(period_end, 0.82 if period_end else 0.0, "header:periode_fin"),
        "solde_initial": _field(
            solde_initial, 0.88 if solde_initial is not None else 0.0, "header:solde_initial"
        ),
        "solde_final": _field(
            solde_final, 0.88 if solde_final is not None else 0.0, "header:solde_final"
        ),
    }


def _extract_etat_immobilisations(text: str) -> dict[str, dict[str, Any]]:
    total_brut, total_brut_src = _extract_first_amount_with_source(
        text,
        [
            ("label:total_brut", r"total.{0,12}brut"),
            ("label:valeur_brute", r"valeur.{0,12}brute"),
            ("label:immobilisations_brutes", r"immobilisations?.{0,12}brutes?"),
        ],
        min_amount=100.0,
    )
    total_amort, total_amort_src = _extract_first_amount_with_source(
        text,
        [
            ("label:total_amortissements", r"total.{0,12}amortissements?"),
            ("label:amortissements_cumules", r"amortissements?.{0,15}cumul"),
            ("label:depreciations", r"d[ée]pr[ée]ciations?"),
        ],
        min_amount=100.0,
    )
    if total_amort is None:
        amort_candidates: list[float] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not re.search(r"total\s+amortissement", line, re.IGNORECASE):
                continue
            nums = _extract_line_amount_tokens(line)
            for n in nums:
                if abs(float(n)) >= 100.0:
                    amort_candidates.append(float(n))
        if amort_candidates:
            total_amort = max(amort_candidates)
            total_amort_src = "fallback:max_total_amortissement_line"
    total_net, total_net_src = _extract_first_amount_with_source(
        text,
        [
            ("label:total_net", r"total.{0,12}net"),
            ("label:valeur_nette_comptable", r"valeur.{0,12}nette.{0,12}comptable"),
            ("label:vnc", r"\bvnc\b"),
        ],
        min_amount=100.0,
    )
    if total_brut is None or total_net is None:
        lines = text.splitlines()
        for i, raw in enumerate(lines):
            if "total tous comptes" not in raw.lower():
                continue
            vals: list[float] = []
            for j in range(i + 1, min(len(lines), i + 9)):
                v = _to_float_fr(lines[j].strip())
                if isinstance(v, float) and abs(v) >= 1.0:
                    vals.append(float(v))
            if vals:
                if total_brut is None:
                    total_brut = vals[0]
                    total_brut_src = "fallback:total_tous_comptes_first_value"
                if total_net is None:
                    # Last numeric value is often the closing VNC on these exports.
                    total_net = vals[-1]
                    total_net_src = "fallback:total_tous_comptes_last_value"
                break
    if total_net is None and isinstance(total_brut, (int, float)) and isinstance(total_amort, (int, float)):
        cand = float(total_brut) - float(total_amort)
        if cand >= 0:
            total_net = cand
            total_net_src = "fallback:brut_minus_amortissements"
    return {
        **_extract_common_fields(text),
        "total_brut_immobilisations": _field(
            total_brut, 0.84 if total_brut is not None else 0.0, total_brut_src
        ),
        "total_amortissements": _field(
            total_amort, 0.84 if total_amort is not None else 0.0, total_amort_src
        ),
        "total_net_immobilisations": _field(
            total_net, 0.84 if total_net is not None else 0.0, total_net_src
        ),
    }


def _extract_releve_bancaire_operations(text: str) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Typical line: "02/01/2025 VIREMENT CLIENT X 0,00 1 200,00"
        m = re.match(r"^([0-3]?\d[\/\-.][0-1]?\d[\/\-.][12]\d{3})\s+(.+)$", line, re.IGNORECASE)
        if not m:
            continue
        op_iso = _to_iso_date_fr(m.group(1))
        if not op_iso:
            continue
        tail = m.group(2).strip()
        amount_matches = list(
            re.finditer(
                r"-?(?:[0-9Oo]{1,3}(?:[ \u00a0][0-9Oo]{3})+|[0-9Oo]+)(?:[.,][0-9Oo]{2})?",
                tail,
                re.IGNORECASE,
            )
        )
        if not amount_matches:
            continue
        # Keep parsed numeric candidates only and use the last one(s) as amount columns.
        candidates: list[tuple[float, tuple[int, int]]] = []
        for am in amount_matches:
            v = _to_float_fr(am.group(0))
            if isinstance(v, float):
                candidates.append((v, am.span()))
        if not candidates:
            continue

        a1 = candidates[-2][0] if len(candidates) >= 2 else candidates[-1][0]
        a2 = candidates[-1][0] if len(candidates) >= 2 else None
        first_amount_start = candidates[-2][1][0] if len(candidates) >= 2 else candidates[-1][1][0]
        label = _norm_spaces(tail[:first_amount_start]) or "OPERATION"

        debit = None
        credit = None
        if isinstance(a2, float):
            # Assume "debit credit" ordering when two amount columns are present.
            debit = max(0.0, float(a1 or 0.0))
            credit = max(0.0, float(a2 or 0.0))
        else:
            amt = float(a1 or 0.0)
            if amt < 0:
                debit = abs(amt)
                credit = 0.0
            else:
                debit = 0.0
                credit = amt
        if debit is None or credit is None:
            continue
        ops.append(
            {
                "date_operation": op_iso,
                "libelle": label,
                "debit": round(float(debit), 2),
                "credit": round(float(credit), 2),
                "contrepartie": None,
            }
        )
    return ops[:1000]


def _extract_generic_accounting_table(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Accept code at start or embedded in OCR-fragmented lines.
        code_match = re.search(r"\b(\d{3,8})\b", line)
        if not code_match:
            continue
        amount_match = re.search(
            r"([0-9][0-9\s\u00a0.,]{1,40}(?:€|EUR)?)\s*$", line, re.IGNORECASE
        )
        if not amount_match:
            continue
        records.append(
            {
                "code": code_match.group(1),
                "label": _norm_spaces(re.sub(r"\b\d{3,8}\b", "", line, count=1)),
                "amount": _to_float_fr(amount_match.group(1)),
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

    ready_for_ai_core = not critical_missing and balance_ok
    ready_for_ai = base["coverage_ratio"] >= 0.75 and ready_for_ai_core
    # Pragmatique produit: si le noyau métier est cohérent, le document est exploitable
    # même avec une couverture secondaire incomplète.
    needs_review = not ready_for_ai_core

    flags = list(base.get("quality_flags", []))
    if critical_missing:
        flags.append("critical_fields_missing")
    if (
        isinstance(actif, (int, float))
        and isinstance(passif, (int, float))
        and balance_gap is not None
    ):
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
        "ready_for_ai_core": ready_for_ai_core,
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

    if (
        isinstance(rex, (int, float))
        and isinstance(rc, (int, float))
        and isinstance(rn, (int, float))
    ):
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

    ready_for_ai_core = not critical_missing and progression_ok
    ready_for_ai = base["coverage_ratio"] >= 0.75 and ready_for_ai_core
    needs_review = not ready_for_ai_core

    flags = list(base.get("quality_flags", []))
    if critical_missing:
        flags.append("critical_fields_missing")
    if (
        isinstance(rex, (int, float))
        and isinstance(rc, (int, float))
        and isinstance(rn, (int, float))
    ):
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
        "ready_for_ai_core": ready_for_ai_core,
        "quality_flags": sorted(set(flags)),
        "cr_chain_delta_rex_rc": round(delta_rex_rc, 2) if delta_rex_rc is not None else None,
        "cr_chain_delta_rc_rn": round(delta_rc_rn, 2) if delta_rc_rn is not None else None,
        "cr_chain_tol_relaxed_rex_rc": round(tol_r1, 2) if tol_r1 else None,
        "cr_chain_tol_relaxed_rc_rn": round(tol_r2, 2) if tol_r2 else None,
    }


def _quality_liasse_is_simplifiee(fields: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Quality gate dédié 2065/2033 : champs clés obligatoires."""
    base = _quality(fields)
    critical = [
        "total_actif",
        "total_passif",
        "chiffre_affaires",
        "resultat_exercice",
    ]
    critical_missing = [k for k in critical if fields.get(k, {}).get("value") in (None, "", [])]

    # Cohérence minimale bilan.
    actif = fields.get("total_actif", {}).get("value")
    passif = fields.get("total_passif", {}).get("value")
    balance_ok = False
    balance_gap: float | None = None
    if isinstance(actif, (int, float)) and isinstance(passif, (int, float)):
        fa, fp = float(actif), float(passif)
        balance_gap = abs(fa - fp)
        ref = max(abs(fa), abs(fp), 1.0)
        tol = max(10.0, ref * 0.04)
        balance_ok = balance_gap <= tol

    flags = list(base.get("quality_flags", []))
    if critical_missing:
        flags.append("critical_fields_missing")
        flags.append("liasse_critical_fields_missing")
    if (
        not balance_ok
        and "total_actif" not in critical_missing
        and "total_passif" not in critical_missing
    ):
        flags.append("bilan_balance_mismatch")

    ready_for_ai_core = (not critical_missing) and balance_ok
    ready_for_ai = ready_for_ai_core and base["coverage_ratio"] >= 0.75
    needs_review = not ready_for_ai_core
    return {
        **base,
        "critical_missing_fields": critical_missing,
        "needs_review": needs_review,
        "ready_for_ai": ready_for_ai,
        "ready_for_ai_core": ready_for_ai_core,
        "quality_flags": sorted(set(flags)),
        "liasse_balance_gap": round(balance_gap, 2) if balance_gap is not None else None,
    }


def _quality_etat_immobilisations(fields: dict[str, dict[str, Any]]) -> dict[str, Any]:
    base = _quality(fields)
    critical = [
        "total_brut_immobilisations",
        "total_amortissements",
        "total_net_immobilisations",
    ]
    critical_missing = [k for k in critical if fields.get(k, {}).get("value") in (None, "", [])]
    brut = fields.get("total_brut_immobilisations", {}).get("value")
    amort = fields.get("total_amortissements", {}).get("value")
    net = fields.get("total_net_immobilisations", {}).get("value")
    coh_ok = False
    if isinstance(brut, (int, float)) and isinstance(amort, (int, float)) and isinstance(net, (int, float)):
        expected = float(brut) - float(amort)
        gap = abs(float(net) - expected)
        tol = max(500.0, abs(float(net)) * 0.04)
        coh_ok = gap <= tol
    # Pragmatic core: either coherent full triplet, or at least amortissements + one global total.
    has_min_pair = (
        fields.get("total_amortissements", {}).get("value") not in (None, "", [])
        and (
            fields.get("total_brut_immobilisations", {}).get("value") not in (None, "", [])
            or fields.get("total_net_immobilisations", {}).get("value") not in (None, "", [])
        )
    )
    ready_for_ai_core = (not critical_missing and coh_ok) or has_min_pair
    ready_for_ai = ready_for_ai_core and base["coverage_ratio"] >= 0.7
    flags = list(base.get("quality_flags", []))
    if critical_missing:
        flags.append("critical_fields_missing")
    if not critical_missing and not coh_ok:
        flags.append("immobilisations_balance_mismatch")
    return {
        **base,
        "critical_missing_fields": critical_missing,
        "needs_review": not ready_for_ai_core,
        "ready_for_ai": ready_for_ai,
        "ready_for_ai_core": ready_for_ai_core,
        "quality_flags": sorted(set(flags)),
    }


def _quality_2072(
    fields: dict[str, dict[str, Any]], tables: dict[str, Any], text: str
) -> dict[str, Any]:
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
    arithmetic_consistency_ok = False
    if isinstance(rb, (int, float)) and isinstance(rn, (int, float)):
        expected = rb - pt - fc - ie
        arithmetic_consistency_ok = abs(expected - rn) <= 5.0
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
    immeubles_fc = sum(
        float(
            (x.get("frais_gestion") or 0.0)
            + (x.get("assurance") or 0.0)
            + (x.get("travaux") or 0.0)
            + (x.get("impositions") or 0.0)
        )
        for x in immeubles
    )
    immeubles_ie = sum(float(x.get("interets_emprunts") or 0.0) for x in immeubles)

    agg_checks = 0
    agg_ok = 0
    if isinstance(rb, (int, float)) and associes_rb > 0:
        agg_checks += 1
        if abs(rb - associes_rb) <= max(
            THRESHOLDS["aggregate_abs_tolerance_min"],
            abs(rb) * THRESHOLDS["aggregate_rel_tolerance"],
        ):
            agg_ok += 1
    if isinstance(rb, (int, float)) and immeubles_rb > 0:
        agg_checks += 1
        if abs(rb - immeubles_rb) <= max(
            THRESHOLDS["aggregate_abs_tolerance_min"],
            abs(rb) * THRESHOLDS["aggregate_rel_tolerance"],
        ):
            agg_ok += 1
    if isinstance(fc, (int, float)) and associes_fc > 0:
        agg_checks += 1
        if abs(fc - associes_fc) <= max(
            THRESHOLDS["aggregate_abs_tolerance_min"],
            abs(fc) * THRESHOLDS["aggregate_rel_tolerance"],
        ):
            agg_ok += 1
    if isinstance(fc, (int, float)) and immeubles_fc > 0:
        agg_checks += 1
        if abs(fc - immeubles_fc) <= max(
            THRESHOLDS["aggregate_abs_tolerance_min"],
            abs(fc) * THRESHOLDS["aggregate_rel_tolerance"],
        ):
            agg_ok += 1
    if isinstance(ie, (int, float)) and associes_ie > 0:
        agg_checks += 1
        if abs(ie - associes_ie) <= max(
            THRESHOLDS["aggregate_abs_tolerance_min"],
            abs(ie) * THRESHOLDS["aggregate_rel_tolerance"],
        ):
            agg_ok += 1
    if isinstance(ie, (int, float)) and immeubles_ie > 0:
        agg_checks += 1
        if abs(ie - immeubles_ie) <= max(
            THRESHOLDS["aggregate_abs_tolerance_min"],
            abs(ie) * THRESHOLDS["aggregate_rel_tolerance"],
        ):
            agg_ok += 1
    aggregate_consistency_score = (agg_ok / agg_checks) if agg_checks else 0.7

    consistency = (
        numeric_consistency_score + annex_consistency_score + aggregate_consistency_score
    ) / 3
    ready_for_ai = (
        base["coverage_ratio"] >= THRESHOLDS["quality_ready_coverage_min"]
        and consistency >= THRESHOLDS["quality_ready_consistency_min"]
        and ann1_ok
        and ann2_ok
        and not critical_missing
    )
    ready_for_ai_core = (
        not critical_missing
        and numeric_consistency_score >= THRESHOLDS["quality_core_numeric_min"]
        and arithmetic_consistency_ok
        and (
            agg_checks == 0
            or aggregate_consistency_score >= THRESHOLDS["quality_core_aggregate_min"]
        )
    )
    needs_review = not ready_for_ai_core
    flags = list(base.get("quality_flags", []))
    if critical_missing:
        flags.append("critical_fields_missing")
    if not ann1_ok or not ann2_ok:
        flags.append("annex_consistency_failed")
    if numeric_consistency_score < THRESHOLDS["quality_core_numeric_min"]:
        flags.append("numeric_consistency_low")
    if not arithmetic_consistency_ok:
        flags.append("arithmetic_inconsistency_detected")
    if agg_checks > 0 and aggregate_consistency_score < THRESHOLDS["quality_core_aggregate_min"]:
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
        "ready_for_ai_core": ready_for_ai_core,
        "quality_flags": sorted(set(flags)),
    }


def _quality_releve_bancaire(
    fields: dict[str, dict[str, Any]], tables: dict[str, Any], text: str
) -> dict[str, Any]:
    base = _quality(fields)
    critical = [
        "periode_debut",
        "periode_fin",
        "solde_initial",
        "solde_final",
    ]
    critical_missing = [k for k in critical if fields.get(k, {}).get("value") in (None, "", [])]

    ops = tables.get("operations") if isinstance(tables, dict) else None
    ops_list = ops if isinstance(ops, list) else []
    sum_debit = sum(float(op.get("debit") or 0.0) for op in ops_list)
    sum_credit = sum(float(op.get("credit") or 0.0) for op in ops_list)
    lines_total = len(
        [
            ln
            for ln in text.splitlines()
            if re.search(r"\b[0-3]?\d[\/\-.][0-1]?\d[\/\-.][12]\d{3}\b", ln)
        ]
    )
    parsed_lines = len(ops_list)
    parsed_ratio = (parsed_lines / lines_total) if lines_total > 0 else 0.0

    s0 = fields.get("solde_initial", {}).get("value")
    s1 = fields.get("solde_final", {}).get("value")
    balance_gap: float | None = None
    balance_ok = False
    if isinstance(s0, (int, float)) and isinstance(s1, (int, float)):
        expected = float(s0) + float(sum_credit) - float(sum_debit)
        balance_gap = abs(expected - float(s1))
        ref = max(abs(float(s1)), abs(expected), 1.0)
        tol = max(1.0, ref * 0.02)
        balance_ok = balance_gap <= tol

    start_iso = fields.get("periode_debut", {}).get("value")
    end_iso = fields.get("periode_fin", {}).get("value")
    out_of_range = 0
    if isinstance(start_iso, str) and isinstance(end_iso, str):
        for op in ops_list:
            if not _iso_date_in_range(op.get("date_operation"), start_iso, end_iso):
                out_of_range += 1
    dates_ok = out_of_range == 0

    flags = list(base.get("quality_flags", []))
    if critical_missing:
        flags.append("critical_fields_missing")
    if not balance_ok and not {"solde_initial", "solde_final"} & set(critical_missing):
        flags.append("balance_mismatch")
    if parsed_ratio < 0.6:
        flags.append("low_line_parse_ratio")
    if not dates_ok:
        flags.append("date_out_of_range")

    ready_for_ai_core = not critical_missing and balance_ok
    ready_for_ai = ready_for_ai_core and parsed_ratio >= 0.7 and dates_ok
    needs_review = (not ready_for_ai) or base.get("needs_review", False)
    return {
        **base,
        "critical_missing_fields": critical_missing,
        "needs_review": needs_review,
        "ready_for_ai": ready_for_ai,
        "ready_for_ai_core": ready_for_ai_core,
        "quality_flags": sorted(set(flags)),
        "balance_gap": round(balance_gap, 2) if balance_gap is not None else None,
        "operations_parsed_count": int(parsed_lines),
        "operations_candidate_lines_count": int(lines_total),
        "parsed_lines_ratio": round(parsed_ratio, 3),
        "out_of_period_operations_count": int(out_of_range),
    }


def _pseudonymize_2072_output(
    fields: dict[str, dict[str, Any]], tables: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Keep extraction quality from raw while exposing anonymized structured output."""
    out_fields = dict(fields)
    if out_fields.get("denomination_sci", {}).get("value"):
        out_fields["denomination_sci"] = _field(
            "SOCIETE_1",
            out_fields["denomination_sci"].get("confidence", 0.9),
            "pseudo:denomination_sci",
        )
    if out_fields.get("adresse_sci", {}).get("value"):
        out_fields["adresse_sci"] = _field(
            "ADRESSE_SOCIETE_1",
            out_fields["adresse_sci"].get("confidence", 0.85),
            "pseudo:adresse_sci",
        )
    if out_fields.get("adresse_siege_ouverture", {}).get("value"):
        out_fields["adresse_siege_ouverture"] = _field(
            "ADRESSE_SIEGE_1",
            out_fields["adresse_siege_ouverture"].get("confidence", 0.8),
            "pseudo:adresse_siege_ouverture",
        )

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


def _extractor_compte_resultat(
    source_text: str, anonymized_text: str
) -> StructuredExtractionResult:
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


def _extractor_statuts_societe(
    source_text: str, anonymized_text: str
) -> StructuredExtractionResult:
    fields = _extract_common_fields(source_text)
    quality = _quality(fields)
    flags = set(quality.get("quality_flags") or [])
    flags.add("doc_type_not_supported_yet")
    quality["quality_flags"] = sorted(flags)
    quality["needs_review"] = True
    quality["ready_for_ai"] = False
    quality["ready_for_ai_core"] = False
    return StructuredExtractionResult(
        fields=fields,
        tables={"accounting_lines": _extract_generic_accounting_table(anonymized_text)},
        quality=quality,
        extractor_name="extractor_statuts_societe_stub",
    )


def _extractor_releve_bancaire(
    source_text: str, _anonymized_text: str
) -> StructuredExtractionResult:
    fields = _extract_releve_bancaire_fields(source_text)
    tables = {"operations": _extract_releve_bancaire_operations(source_text)}
    return StructuredExtractionResult(
        fields=fields,
        tables=tables,
        quality=_quality_releve_bancaire(fields, tables, source_text),
        extractor_name="extractor_releve_bancaire",
    )


def _extractor_etat_immobilisations(
    source_text: str, anonymized_text: str
) -> StructuredExtractionResult:
    fields = _extract_etat_immobilisations(source_text)
    tables = {"accounting_lines": _extract_generic_accounting_table(anonymized_text)}
    return StructuredExtractionResult(
        fields=fields,
        tables=tables,
        quality=_quality_etat_immobilisations(fields),
        extractor_name="extractor_etat_immobilisations",
    )


EXTRACTOR_REGISTRY_V1: dict[str, Any] = {
    "bilan": _extractor_bilan,
    "compte_resultat": _extractor_compte_resultat,
    "fiscal_2072": _extractor_fiscal_2072,
    "releve_bancaire": _extractor_releve_bancaire,
    "etat_immobilisations": _extractor_etat_immobilisations,
    "statuts_societe": _extractor_statuts_societe,
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
            quality=_quality_liasse_is_simplifiee(fields),
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
        "generated_at": datetime.now(UTC).isoformat(),
        "fields": fields,
        "tables": tables,
        "quality": quality_out,
        "provenance": provenance,
        "experience": experience,
    }


def _fallback_source_stats(fields: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Count source families to observe extractor behavior in production."""
    stats: dict[str, int] = {}
    for item in (fields or {}).values():
        if not isinstance(item, dict):
            continue
        src = str(item.get("source_hint") or "")
        family = "missing"
        if src:
            family = src.split(":", 1)[0]
        stats[family] = stats.get(family, 0) + 1
    return stats


def build_structured_dataset(
    anonymized_text: str,
    original_filename: str = "",
    requested_doc_type: str = "auto",
    extraction_text: str | None = None,
) -> dict[str, Any]:
    """Build normalized structured dataset payload for downstream analytics/AI."""
    from app.services.text_segment_selector import select_extraction_segment, select_section_block

    full_text_for_routing = extraction_text if extraction_text is not None else anonymized_text
    detected_doc_type, routing_confidence, routing_reasons, routing_runner_up = (
        classify_doc_type_scored(full_text_for_routing, original_filename)
    )
    doc_type = detected_doc_type if requested_doc_type in ("", "auto") else requested_doc_type
    # Backward compatibility with older naming used in draft golden cases.
    if doc_type == "immobilisations":
        doc_type = "etat_immobilisations"

    source_text = full_text_for_routing
    text_segmentation: dict[str, Any] = {}
    extracted: StructuredExtractionResult | None = None
    if extraction_text is not None:
        sem_seg, sem_meta = select_extraction_segment(extraction_text, doc_type)
        sec_seg, sec_meta = select_section_block(extraction_text, doc_type)
        candidates: list[tuple[str, dict[str, Any], StructuredExtractionResult]] = []
        # Candidate 1: semantic window/full_text from existing selector.
        cand_sem = _run_extractor_pipeline(doc_type, sem_seg, anonymized_text)
        candidates.append(("semantic_or_full", sem_meta, cand_sem))
        # Candidate 2: section block for supported doc types.
        if sec_meta and sec_seg:
            cand_sec = _run_extractor_pipeline(doc_type, sec_seg, anonymized_text)
            candidates.append(("section_block", sec_meta, cand_sec))
        # Candidate 3: explicit full text baseline.
        full_meta: dict[str, Any] = {
            "strategy": "full_text",
            "reason": "quality_comparison_baseline",
            "char_start": 0,
            "char_end": len(extraction_text),
            "window_score": 0.0,
            "full_chars": len(extraction_text),
            "segment_chars": len(extraction_text),
            "doc_type_target": doc_type,
        }
        cand_full = _run_extractor_pipeline(doc_type, extraction_text, anonymized_text)
        candidates.append(("full_text", full_meta, cand_full))

        best_label, best_meta, best_res = candidates[0]
        for label, meta, res in candidates[1:]:
            if _extraction_quality_better(res.quality, best_res.quality):
                best_label, best_meta, best_res = label, meta, res
        extracted = best_res
        text_segmentation = {
            **best_meta,
            "candidate_count": len(candidates),
            "selected_candidate": best_label,
        }
        source_text = extraction_text if text_segmentation.get("strategy") == "full_text" else (
            sec_seg if text_segmentation.get("strategy") == "section_block" else sem_seg
        )

    if extracted is None:
        extracted = _run_extractor_pipeline(doc_type, source_text, anonymized_text)

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
        critical_present = sum(
            1 for k in critical6 if (fields.get(k, {}) or {}).get("value") not in (None, "", [])
        )
        if critical_present < 3:
            routing_confidence = min(routing_confidence, 0.6)
    # Global guardrail: confidence shown to users should remain conservative when
    # critical fields are missing, even if router lexical score is high.
    critical_missing = (
        quality.get("critical_missing_fields", []) if isinstance(quality, dict) else []
    )
    if isinstance(critical_missing, list) and critical_missing:
        routing_confidence = min(routing_confidence, 0.85)

    if extraction_text is not None:
        from app.services.text_segment_selector import count_pdf_page_markers

        n_mark = count_pdf_page_markers(extraction_text)
        if n_mark:
            text_segmentation = {**text_segmentation, "pdf_page_markers_in_source": n_mark}

    payload = _build_contract_payload(
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
    quality = payload.get("quality") if isinstance(payload, dict) else {}
    critical_missing = (
        quality.get("critical_missing_fields", []) if isinstance(quality, dict) else []
    )
    fallback_stats = (
        _fallback_source_stats(payload.get("fields", {})) if isinstance(payload, dict) else {}
    )
    logger.info(
        "structured_dataset_built",
        requested_doc_type=requested_doc_type,
        doc_type=payload.get("doc_type") if isinstance(payload, dict) else doc_type,
        detected_doc_type=payload.get("detected_doc_type")
        if isinstance(payload, dict)
        else detected_doc_type,
        extractor_name=payload.get("provenance", {}).get("extractor_name")
        if isinstance(payload, dict)
        else extracted.extractor_name,
        routing_confidence=payload.get("routing_confidence")
        if isinstance(payload, dict)
        else routing_confidence,
        coverage_ratio=(quality or {}).get("coverage_ratio") if isinstance(quality, dict) else None,
        ready_for_ai=(quality or {}).get("ready_for_ai") if isinstance(quality, dict) else False,
        ready_for_ai_core=(quality or {}).get("ready_for_ai_core")
        if isinstance(quality, dict)
        else False,
        needs_review=(quality or {}).get("needs_review") if isinstance(quality, dict) else True,
        critical_missing_count=len(critical_missing) if isinstance(critical_missing, list) else 0,
        quality_flags=(quality or {}).get("quality_flags") if isinstance(quality, dict) else [],
        fallback_source_stats=fallback_stats,
    )
    return payload
