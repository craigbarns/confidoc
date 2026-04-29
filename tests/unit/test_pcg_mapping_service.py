"""Tests for the rule-based PCG engine v2."""

from __future__ import annotations

import pytest

from app.services.pcg_mapping_service import (
    PCG_ROOTS,
    PcgSource,
    PcgSuggestion,
    PcgSuggestResult,
    suggest,
    suggest_pcg_code,
)
from app.services.pcg_rules import RULES


# ──────────────────────────────────────────────────────────────────────
# Backward compatibility: existing callers (llm_extraction_service)
# only rely on suggest_pcg_code(libelle, nature) returning {"code", "label"}.
# ──────────────────────────────────────────────────────────────────────


class TestBackwardCompatibility:
    def test_returns_dict_with_code_and_label(self):
        out = suggest_pcg_code("Loyer mars 2026", "charge")
        assert isinstance(out, dict)
        assert "code" in out
        assert "label" in out
        assert isinstance(out["code"], str)
        assert isinstance(out["label"], str)

    def test_existing_extracted_libelle_keeps_returning_a_real_account(self):
        # This is exactly how llm_extraction_service uses the function.
        out = suggest_pcg_code("Honoraires comptable Q1", "charge")
        assert out["code"] == "622600"

    def test_no_match_returns_a_safe_fallback_dict_shape(self):
        out = suggest_pcg_code("Random gibberish xyz", "autre")
        assert "code" in out and "label" in out
        # Should be the unknown bucket because nature is "autre".
        assert out["code"] == "471000"

    def test_empty_libelle_does_not_raise(self):
        out = suggest_pcg_code("", "autre")
        assert out["code"] == "471000"


# ──────────────────────────────────────────────────────────────────────
# Single-rule matches → confident, well-explained suggestions
# ──────────────────────────────────────────────────────────────────────


class TestSimpleRuleMatches:
    @pytest.mark.parametrize(
        "libelle,expected_code",
        [
            ("Loyer du local commercial avril 2026", "613100"),
            ("Charges locatives copropriété", "614000"),
            ("Prime d'assurance AXA", "616000"),
            ("Honoraires expert-comptable", "622600"),
            ("Honoraires d'avocat - consultation", "622600"),
            ("Frais bancaires - tenue de compte", "627000"),
            ("Fournitures de bureau (papeterie)", "606400"),
            ("Abonnement Internet fibre Orange Pro", "626100"),
            ("La Poste - affranchissement courrier", "626100"),
            ("Billet train SNCF Paris-Lyon", "625100"),
            ("Péage autoroute A7", "625100"),
            ("Restaurant Le Train Bleu - réception client", "625700"),
            ("Maintenance climatisation bureau", "615000"),
            ("Sous-traitance développement freelance", "611000"),
            ("Achats marchandises pour revente", "607000"),
            ("Abonnement SaaS Notion équipe", "651100"),
            ("Campagne publicité Google Ads", "623000"),
            ("Carburant Total Energies véhicule", "606140"),
            ("Cotisation ordre des avocats 2026", "628100"),
        ],
    )
    def test_rule_yields_expected_account(self, libelle, expected_code):
        result = suggest(libelle, "charge")
        assert result.suggestion.code == expected_code, (
            f"libelle={libelle!r} → got {result.suggestion.code} "
            f"(reason={result.suggestion.reason})"
        )

    def test_rule_match_carries_reason_and_keywords(self):
        result = suggest("Loyer mars 2026", "charge")
        assert result.suggestion.source == PcgSource.RULE
        assert result.suggestion.reason
        assert any(
            "loyer" in kw.lower() for kw in result.suggestion.matched_keywords
        )

    def test_rule_match_confidence_is_in_range(self):
        result = suggest("Honoraires expert-comptable", "charge")
        assert 0.7 <= result.suggestion.confidence <= 1.0


# ──────────────────────────────────────────────────────────────────────
# Ambiguous text → a top suggestion + alternatives
# ──────────────────────────────────────────────────────────────────────


class TestAmbiguousLabels:
    def test_two_distinct_accounts_emit_alternatives(self):
        # "Restaurant" → 625700 ; "Taxi" → 625100 — both above cutoff.
        result = suggest("Restaurant et taxi pour mission client", "charge")
        codes = {result.suggestion.code, *(a.code for a in result.alternatives)}
        assert "625100" in codes
        assert "625700" in codes
        assert len(result.alternatives) >= 1

    def test_top_is_highest_confidence(self):
        result = suggest("Restaurant et taxi pour mission client", "charge")
        for alt in result.alternatives:
            assert result.suggestion.confidence >= alt.confidence

    def test_alternative_margin_filters_low_confidence(self):
        # Tight margin → alternatives that are too far from the top are dropped.
        result = suggest(
            "Restaurant et taxi pour mission client",
            "charge",
            alternative_margin=0.001,
        )
        for alt in result.alternatives:
            assert alt.confidence >= result.suggestion.confidence - 0.001

    def test_top_k_limits_total_results(self):
        result = suggest(
            "Loyer Honoraires Restaurant Taxi Saas",
            "charge",
            top_k=2,
            alternative_margin=1.0,  # accept everything by confidence
        )
        assert len(result.alternatives) <= 1  # top_k=2 → 1 principal + 1 alt max


# ──────────────────────────────────────────────────────────────────────
# Unknown / fallback
# ──────────────────────────────────────────────────────────────────────


class TestFallbacks:
    def test_unknown_libelle_with_charge_uses_nature_fallback(self):
        result = suggest("Quelque chose d'absolument indéchiffrable", "charge")
        assert result.suggestion.source == PcgSource.FALLBACK_NATURE
        assert result.suggestion.code == "606300"
        assert result.suggestion.confidence < 0.5

    def test_unknown_libelle_with_produit_uses_produit_fallback(self):
        result = suggest("Quelque chose d'inconnu", "produit")
        assert result.suggestion.source == PcgSource.FALLBACK_NATURE
        assert result.suggestion.code == "706000"

    def test_unknown_libelle_with_autre_uses_unknown_bucket(self):
        result = suggest("Aucun signal exploitable", "autre")
        assert result.suggestion.source == PcgSource.FALLBACK_UNKNOWN
        assert result.suggestion.code == "471000"
        assert result.suggestion.confidence < 0.2
        # The reason must explicitly invite a human review.
        assert "humain" in result.suggestion.reason.lower() or (
            "revue" in result.suggestion.reason.lower()
        )

    def test_fallback_never_has_alternatives(self):
        result = suggest("???", "autre")
        assert result.alternatives == ()


# ──────────────────────────────────────────────────────────────────────
# Confidence sanity & explainability
# ──────────────────────────────────────────────────────────────────────


class TestConfidenceAndExplainability:
    def test_specificity_bonus_increases_confidence(self):
        # "honoraires" alone (generic rule, base 0.7).
        weak = suggest("Honoraires divers", "charge")
        # "honoraires expert-comptable" (specific rule, base 0.93 + bonus).
        strong = suggest("Honoraires expert-comptable", "charge")
        assert strong.suggestion.confidence > weak.suggestion.confidence

    def test_reason_is_present_and_short(self):
        result = suggest("Loyer Q2", "charge")
        assert result.suggestion.reason
        assert len(result.suggestion.reason) < 200

    def test_source_is_one_of_known_values(self):
        result = suggest("Loyer", "charge")
        assert result.suggestion.source in {
            PcgSource.RULE,
            PcgSource.HISTORICAL_SIMILARITY,
            PcgSource.LLM_ASSISTED,
            PcgSource.FALLBACK_NATURE,
            PcgSource.FALLBACK_UNKNOWN,
        }

    def test_to_dict_output_is_serializable_and_contains_alternatives_key(self):
        result = suggest("Restaurant et taxi", "charge")
        out = result.to_dict()
        assert "code" in out
        assert "alternatives" in out
        assert isinstance(out["alternatives"], list)


# ──────────────────────────────────────────────────────────────────────
# Diacritics / case handling
# ──────────────────────────────────────────────────────────────────────


class TestNormalisation:
    def test_accents_are_ignored(self):
        a = suggest("PÉAGE A7 LYON", "charge").suggestion
        b = suggest("peage a7 lyon", "charge").suggestion
        assert a.code == b.code == "625100"

    def test_uppercase_input_matches_rules(self):
        result = suggest("LOYER LOCAL COMMERCIAL", "charge")
        assert result.suggestion.code == "613100"


# ──────────────────────────────────────────────────────────────────────
# Future hook: historical_lookup (GoldenCaseDraft will plug in here)
# ──────────────────────────────────────────────────────────────────────


class TestHistoricalLookupHook:
    def test_historical_lookup_can_outrank_rules(self):
        """A high-confidence historical match wins over a rule match."""

        def fake_historical(libelle, nature):
            return [
                PcgSuggestion(
                    code="999999",
                    label="Historique cabinet",
                    confidence=0.99,
                    reason="3 corrections récentes pointent vers ce compte.",
                    source=PcgSource.HISTORICAL_SIMILARITY,
                )
            ]

        result = suggest(
            "Loyer mars",  # would normally match rule → 613100
            "charge",
            historical_lookup=fake_historical,
        )
        assert result.suggestion.code == "999999"
        assert result.suggestion.source == PcgSource.HISTORICAL_SIMILARITY
        # The rule-based 613100 is then surfaced as an alternative.
        codes = {a.code for a in result.alternatives}
        assert "613100" in codes

    def test_historical_lookup_failure_does_not_break(self):
        """Engine survives a bug in the lookup callable."""

        def broken(libelle, nature):
            raise RuntimeError("boom")

        result = suggest("Loyer mars", "charge", historical_lookup=broken)
        # We still get the rule-based suggestion.
        assert result.suggestion.code == "613100"

    def test_no_dependency_on_llm_or_network(self):
        """Engine must not import or require any LLM/network module."""
        import inspect

        import app.services.pcg_mapping_service as svc

        src = inspect.getsource(svc)
        assert "openai" not in src.lower()
        assert "mistral" not in src.lower()
        assert "anthropic" not in src.lower()
        assert "httpx" not in src.lower()
        assert "requests" not in src.lower()


# ──────────────────────────────────────────────────────────────────────
# Catalog sanity
# ──────────────────────────────────────────────────────────────────────


class TestRuleCatalog:
    def test_all_required_categories_are_covered(self):
        # Each category from the spec must yield a non-fallback result on a
        # realistic libellé.
        coverage_samples = {
            "loyers": "Loyer mars 2026",
            "charges_locatives": "Charges locatives Q1",
            "assurances": "Assurance multirisque pro",
            "honoraires_comptables": "Honoraires expert-comptable",
            "honoraires_juridiques": "Honoraires avocat consultation",
            "frais_bancaires": "Frais bancaires tenue de compte",
            "fournitures_administratives": "Fournitures de bureau papeterie",
            "telecom_internet": "Abonnement Internet fibre Orange",
            "deplacements": "Billet train SNCF",
            "restauration_reception": "Restaurant client Le Train Bleu",
            "entretien_reparation": "Maintenance climatisation",
            "sous_traitance": "Sous-traitance freelance dev",
            "achats_marchandises": "Achats marchandises revente",
            "logiciels_saas": "Abonnement SaaS Notion",
            "publicite_marketing": "Campagne publicité Google Ads",
            "carburant": "Carburant Total Energies",
            "peages_parking": "Péage autoroute A7",
            "frais_postaux": "La Poste affranchissement",
            "cotisations_professionnelles": "Cotisation ordre des avocats",
        }
        missing: list[tuple[str, str]] = []
        for category, sample in coverage_samples.items():
            result = suggest(sample, "charge")
            if result.suggestion.source != PcgSource.RULE:
                missing.append((category, sample))
        assert not missing, f"Missing rule coverage: {missing}"

    def test_all_rule_codes_are_six_digits(self):
        for rule in RULES:
            assert rule.account.code.isdigit()
            assert len(rule.account.code) == 6

    def test_pcg_roots_kept_for_callers(self):
        # The legacy module-level dict must keep a few critical roots.
        for root in ("613", "622", "626", "627", "606", "607"):
            assert root in PCG_ROOTS
