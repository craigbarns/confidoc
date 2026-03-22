"""Sélection d'une fenêtre texte pertinente pour l'extraction (liasses / plaquettes longues).

Sans dépendre des numéros de page (souvent absents après markdown), on score des
fenêtres glissantes avec des libellés typiques bilan / compte de résultat / 2072.
"""

from __future__ import annotations

import re
from typing import Any

_PAGE_LINE_RE = re.compile(r"^---PAGE (\d+)---\s*$", re.MULTILINE)

# Au-dessous de ce seuil, le document entier est utilisé (pas de découpe).
MIN_CHARS_FOR_SEMANTIC_WINDOW: int = 12_000

# Fenêtre glissante : assez grande pour un tableau de synthèse, pas trop pour rester focalisé.
_WINDOW_CHARS: int = 5_500
_STEP_CHARS: int = 1_400

# Score minimum pour préférer une fenêtre au texte entier (évite faux positifs sur bruit).
_MIN_ABS_SCORE: float = 6.0


def _norm(s: str) -> str:
    return s.lower()


# Patterns (insensible casse) avec poids — conçus pour plaquettes / liasses FR.
_SPECS: dict[str, dict[str, list[tuple[re.Pattern[str], float]]]] = {
    "bilan": {
        "pos": [
            (re.compile(r"\b(?:bilan|situation\s+patrimoniale)\b", re.I), 4.0),
            (re.compile(r"\btotal\s+(?:de\s+l[''])?actif\b", re.I), 5.5),
            (re.compile(r"\btotal\s+(?:du\s+)?passif\b", re.I), 5.5),
            (re.compile(r"\b(?:l[''])?actif\b", re.I), 1.2),
            (re.compile(r"\b(?:le\s+)?passif\b", re.I), 1.2),
            (re.compile(r"\bcapitaux?\s+propres\b", re.I), 3.0),
            (re.compile(r"\bdettes?\s+financ", re.I), 2.0),
            (re.compile(r"\bimmobilisations?\b", re.I), 1.5),
        ],
        "neg": [
            (re.compile(r"\bcompte\s+de\s+r[ée]sultat\b", re.I), -2.5),
            (re.compile(r"\bchiffre\s+d['\s]*affaires\b", re.I), -1.5),
            (re.compile(r"\bproduits?\s+d['\s]*exploitation\b", re.I), -1.0),
        ],
    },
    "compte_resultat": {
        "pos": [
            (re.compile(r"\bcompte\s+de\s+r[ée]sultat\b", re.I), 6.0),
            (re.compile(r"\bchiffre\s+d['\s]*affaires\b", re.I), 4.0),
            (re.compile(r"\br[ée]sultat\s+(?:d['\s]*exploitation|courant|net)\b", re.I), 4.0),
            (re.compile(r"\bcharges?\s+externes\b", re.I), 2.5),
            (re.compile(r"\bproduits?\s+d['\s]*exploitation\b", re.I), 2.0),
        ],
        "neg": [
            (re.compile(r"\btotal\s+(?:de\s+l[''])?actif\b", re.I), -3.0),
            (re.compile(r"\btotal\s+(?:du\s+)?passif\b", re.I), -3.0),
            (re.compile(r"\bcapitaux?\s+propres\b", re.I), -1.0),
        ],
    },
    "fiscal_2072": {
        "pos": [
            (re.compile(r"\b2072\b", re.I), 3.0),
            (re.compile(r"\br[ée]venus?\s+fonciers?\b", re.I), 4.5),
            (re.compile(r"\b(?:revenu|revenus?)\s+net\s+fonci", re.I), 3.5),
            (re.compile(r"\bsci\b", re.I), 2.0),
            (re.compile(r"\bimmeuble", re.I), 2.0),
            (re.compile(r"\bassoci[ée]s?\b", re.I), 1.0),
            (re.compile(r"\bannexe\s*1\b", re.I), 1.5),
        ],
        "neg": [],
    },
}


def _score_window(text_lower: str, doc_type: str) -> float:
    spec = _SPECS.get(doc_type)
    if not spec:
        return 0.0
    score = 0.0
    for pat, w in spec["pos"]:
        score += w * len(pat.findall(text_lower))
    for pat, w in spec["neg"]:
        score += w * len(pat.findall(text_lower))
    return score


def _iter_windows(full: str) -> list[tuple[int, int, str]]:
    n = len(full)
    if n <= _WINDOW_CHARS:
        return [(0, n, full)]
    out: list[tuple[int, int, str]] = []
    start = 0
    while start < n:
        end = min(n, start + _WINDOW_CHARS)
        out.append((start, end, full[start:end]))
        if end >= n:
            break
        start += _STEP_CHARS
    return out


def select_extraction_segment(full_text: str, doc_type: str) -> tuple[str, dict[str, Any]]:
    """Retourne le meilleur segment pour le type cible et des métadonnées d'explicabilité.

    - Texte court ou type non géré : document entier (strategy full_text).
    - Sinon : fenêtre au score lexical maximal si le score dépasse le seuil absolu.
    """
    meta: dict[str, Any] = {
        "strategy": "full_text",
        "reason": "default",
        "char_start": 0,
        "char_end": len(full_text),
        "window_score": 0.0,
        "full_chars": len(full_text),
        "segment_chars": len(full_text),
        "doc_type_target": doc_type,
    }

    if doc_type not in _SPECS:
        meta["reason"] = "doc_type_not_segmented"
        return full_text, meta

    if len(full_text) < MIN_CHARS_FOR_SEMANTIC_WINDOW:
        meta["reason"] = "below_min_chars"
        return full_text, meta

    lower_full = _norm(full_text)
    best: tuple[float, int, int] = (-1e9, 0, len(full_text))

    for start, end, chunk in _iter_windows(full_text):
        sc = _score_window(lower_full[start:end], doc_type)
        if sc > best[0]:
            best = (sc, start, end)

    best_score, bs, be = best
    meta["window_score"] = round(best_score, 2)

    if best_score < _MIN_ABS_SCORE:
        meta["reason"] = "low_score_use_full_text"
        return full_text, meta

    # Légère marge contextuelle autour de la fenêtre gagnante
    pad = 400
    s2 = max(0, bs - pad)
    e2 = min(len(full_text), be + pad)

    segment = full_text[s2:e2]
    meta.update(
        {
            "strategy": "semantic_window",
            "reason": "keyword_window",
            "char_start": s2,
            "char_end": e2,
            "segment_chars": len(segment),
        }
    )
    return segment, meta


def count_pdf_page_markers(text: str) -> int:
    """Nombre de marqueurs ---PAGE N--- dans le texte extrait (PDF natif / OCR)."""
    return len(_PAGE_LINE_RE.findall(text or ""))
