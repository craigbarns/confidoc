"""ConfiDoc — PCG Engine v2.

Suggests French PCG (Plan Comptable Général) accounts for an extracted
``libellé`` + ``nature`` pair. The engine is deliberately *explainable*:

- Each suggestion carries a ``reason`` string and a ``source`` identifier so
  any account proposal can be audited downstream.
- The catalog of rules lives in :mod:`app.services.pcg_rules` as pure data;
  adding a category does not require touching the engine.
- The engine is **deterministic** and **synchronous**: no LLM, no network
  call. It is the safe baseline from which optional historical / semantic /
  LLM layers can be plugged in later (see ``docs/PCG_ENGINE.md``).

Backwards compatibility
-----------------------
The legacy entry point :func:`suggest_pcg_code` still returns a dict that
contains at least ``"code"`` and ``"label"``. Existing callers in
``app/services/llm_extraction_service.py`` keep working unchanged. New
callers should prefer :func:`suggest`, which returns a typed
:class:`PcgSuggestResult` exposing the principal suggestion *and* its
alternatives.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger
from app.services.pcg_rules import (
    FALLBACK_BY_NATURE,
    RULES,
    UNKNOWN_ACCOUNT,
    PcgAccount,
    PcgRule,
)

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Public types
# ─────────────────────────────────────────────────────────────────────────────


class PcgSource:
    """Identifies *why* a suggestion was produced.

    String constants are used (not an enum) to keep JSON payloads stable.
    """

    RULE = "rule"
    HISTORICAL_SIMILARITY = "historical_similarity"
    LLM_ASSISTED = "llm_assisted"
    FALLBACK_NATURE = "fallback_nature"
    FALLBACK_UNKNOWN = "fallback_unknown"


@dataclass(frozen=True)
class PcgSuggestion:
    """A single suggested PCG mapping for a libellé."""

    code: str
    label: str
    confidence: float
    reason: str
    source: str
    matched_keywords: tuple[str, ...] = field(default=())

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "label": self.label,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
            "source": self.source,
            "matched_keywords": list(self.matched_keywords),
        }


@dataclass(frozen=True)
class PcgSuggestResult:
    """Top suggestion + alternatives.

    A caller looking only at ``code`` can ignore ``alternatives`` entirely.
    """

    suggestion: PcgSuggestion
    alternatives: tuple[PcgSuggestion, ...] = field(default=())

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.suggestion.to_dict(),
            "alternatives": [a.to_dict() for a in self.alternatives],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Public, legacy-compatible PCG_ROOTS map
# (kept so any import elsewhere keeps working)
# ─────────────────────────────────────────────────────────────────────────────


PCG_ROOTS: dict[str, str] = {
    "601": "Achats de matières premières",
    "606": "Achats non stockés de matières et fournitures (énergie, fournitures bureau)",
    "607": "Achats de marchandises",
    "611": "Sous-traitance générale",
    "613": "Locations",
    "614": "Charges locatives et de copropriété",
    "615": "Entretien et réparations",
    "616": "Primes d'assurances",
    "621": "Personnel extérieur à l'entreprise",
    "622": "Rémunérations d'intermédiaires et honoraires",
    "623": "Publicité, publications, relations publiques",
    "625": "Déplacements, missions et réceptions",
    "626": "Frais postaux et de télécommunications",
    "627": "Services bancaires et assimilés",
    "628": "Divers (cotisations)",
    "641": "Rémunérations du personnel",
    "651": "Redevances pour concessions, brevets, licences",
    "701": "Ventes de produits finis",
    "706": "Prestations de services",
    "707": "Ventes de marchandises",
    "401": "Fournisseurs",
    "411": "Clients",
    "512": "Banque",
}


# ─────────────────────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────────────────────


def _normalize(text: str) -> str:
    """Lowercase + strip diacritics. Keeps spaces and digits intact."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.lower().strip()


def _rule_matches(rule: PcgRule, normalized: str, nature: str) -> tuple[str, ...]:
    """Return the tuple of keywords from ``rule`` found in ``normalized``.

    An empty tuple means the rule did not match.
    """
    if rule.natures and nature not in rule.natures:
        return ()
    matches: list[str] = []
    for kw in rule.keywords:
        nkw = _normalize(kw)
        if nkw and nkw in normalized:
            matches.append(kw)
    return tuple(matches)


def _score_rule(rule: PcgRule, matched: tuple[str, ...]) -> float:
    """Confidence given a rule and the number of keywords it matched.

    The base confidence is bumped slightly for each *additional* keyword
    matched (specificity bonus), capped at 1.0.
    """
    if not matched:
        return 0.0
    bonus = 0.04 * (len(matched) - 1)
    return min(1.0, rule.base_confidence + bonus)


def _suggestions_from_rules(libelle: str, nature: str) -> list[PcgSuggestion]:
    """Run every rule, return one ``PcgSuggestion`` per rule that matched.

    The list is sorted by descending confidence; later steps are responsible
    for de-duplicating by account code and slicing alternatives.
    """
    normalized = _normalize(libelle)
    if not normalized:
        return []

    out: list[PcgSuggestion] = []
    for rule in RULES:
        matched = _rule_matches(rule, normalized, nature)
        if not matched:
            continue
        confidence = _score_rule(rule, matched)
        out.append(
            PcgSuggestion(
                code=rule.account.code,
                label=rule.account.label,
                confidence=confidence,
                reason=rule.reason,
                source=PcgSource.RULE,
                matched_keywords=matched,
            )
        )

    out.sort(key=lambda s: s.confidence, reverse=True)
    return out


def _dedupe_by_code(
    suggestions: list[PcgSuggestion],
) -> list[PcgSuggestion]:
    """Keep only the highest-confidence suggestion per account code."""
    best: dict[str, PcgSuggestion] = {}
    for s in suggestions:
        prev = best.get(s.code)
        if prev is None or s.confidence > prev.confidence:
            best[s.code] = s
    return sorted(best.values(), key=lambda s: s.confidence, reverse=True)


def _fallback(libelle: str, nature: str) -> PcgSuggestion:
    """When no rule matched, fall back on nature, then on the unknown bucket."""
    account = FALLBACK_BY_NATURE.get(nature)
    if account is not None:
        return PcgSuggestion(
            code=account.code,
            label=account.label,
            confidence=0.25,
            reason=(
                f"Aucune règle déclenchée — repli sur la nature « {nature} » "
                f"({account.code} {account.label})."
            ),
            source=PcgSource.FALLBACK_NATURE,
        )
    return PcgSuggestion(
        code=UNKNOWN_ACCOUNT.code,
        label=UNKNOWN_ACCOUNT.label,
        confidence=0.05,
        reason=(
            "Aucune règle ni nature exploitable — compte d'attente. "
            "Une revue humaine est nécessaire."
        ),
        source=PcgSource.FALLBACK_UNKNOWN,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


HistoricalLookup = Callable[[str, str], list[PcgSuggestion]]
"""Pluggable lookup signature for the future GoldenCaseDraft / similarity
layer. ``(libelle, nature) -> list[PcgSuggestion]``. Implementations should
set ``source = PcgSource.HISTORICAL_SIMILARITY`` and a sensible confidence.
The engine merges these results with rule-based ones and re-applies
deduplication / sorting.
"""


def suggest(
    libelle: str,
    nature: str = "autre",
    *,
    top_k: int = 3,
    alternative_margin: float = 0.25,
    historical_lookup: HistoricalLookup | None = None,
) -> PcgSuggestResult:
    """Return the principal suggestion + at most ``top_k - 1`` alternatives.

    Parameters
    ----------
    libelle:
        Libellé extrait du document (ex. « Loyer mars 2026 »). Peut être
        accentué, en majuscules, contenir des mots inconnus.
    nature:
        ``"charge"``, ``"produit"`` ou ``"autre"``. Sert au fallback et peut
        restreindre certaines règles.
    top_k:
        Nombre maximum total de suggestions (principale + alternatives).
    alternative_margin:
        Une suggestion alternative n'est conservée que si sa confiance est
        au-dessus de ``top.confidence - alternative_margin``. Empêche
        d'afficher des codes manifestement faux.
    historical_lookup:
        Hook optionnel. Si fourni, ses résultats sont fusionnés avec ceux des
        règles avant tri. Voir :data:`HistoricalLookup`.
    """
    rule_results = _suggestions_from_rules(libelle, nature)
    historical_results: list[PcgSuggestion] = []
    if historical_lookup is not None:
        try:
            historical_results = list(historical_lookup(libelle, nature))
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("pcg_historical_lookup_failed", error=str(exc))
            historical_results = []

    merged = _dedupe_by_code(historical_results + rule_results)

    if not merged:
        return PcgSuggestResult(suggestion=_fallback(libelle, nature))

    top = merged[0]
    cutoff = max(0.0, top.confidence - alternative_margin)
    alternatives = tuple(s for s in merged[1:top_k] if s.confidence >= cutoff)
    return PcgSuggestResult(suggestion=top, alternatives=alternatives)


def suggest_pcg_code(libelle: str, nature: str) -> dict[str, Any]:
    """Backwards-compatible entry point.

    Returns at minimum ``{"code": str, "label": str}`` — the original
    contract used by ``app/services/llm_extraction_service.py``. The dict
    is now also enriched with ``confidence``, ``reason``, ``source``,
    ``matched_keywords`` and ``alternatives`` so newer callers can take
    advantage of the explainability without breaking older ones.
    """
    result = suggest(libelle or "", nature or "autre")
    return result.to_dict()
