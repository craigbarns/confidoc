"""Tests qualité structurée (bilan, compte de résultat) — régression P1/P2."""

from __future__ import annotations

from app.services.structured_dataset_service import (
    _cr_step_tolerances,
    _quality_bilan,
    _quality_compte_resultat,
)


def _field(value, confidence: float = 0.9) -> dict:
    return {"value": value, "confidence": confidence, "source": "unit:test"}


class TestCrStepTolerances:
    def test_ordering_strict_le_relaxed(self):
        s, r = _cr_step_tolerances(1_000_000.0)
        assert s < r
        assert s == max(250_000.0, 1_500_000.0)
        assert r == max(500_000.0, 2_000_000.0)


class TestQualityBilan:
    def _minimal_bilan(
        self,
        actif: float,
        passif: float,
    ) -> dict:
        return {
            "total_actif": _field(actif),
            "total_passif": _field(passif),
            "capitaux_propres": _field(100.0),
            "dettes_financieres": _field(200.0),
            "dettes_fournisseurs": _field(300.0),
            "resultat_exercice": _field(50.0),
        }

    def test_balanced_no_flags(self):
        q = _quality_bilan(self._minimal_bilan(1_000_000.0, 1_000_000.0))
        assert q["ready_for_ai"] is True
        assert "bilan_balance_mismatch" not in q["quality_flags"]
        assert "bilan_balance_minor_gap" not in q["quality_flags"]
        assert q["bilan_balance_gap"] == 0.0

    def test_minor_gap_within_relaxed(self):
        # écart > 2% strict mais <= 4% relaxé sur ~1M
        actif = 1_000_000.0
        passif = 1_000_000.0 + 35_000.0  # 3.5%
        q = _quality_bilan(self._minimal_bilan(actif, passif))
        assert q["ready_for_ai"] is True
        assert "bilan_balance_mismatch" not in q["quality_flags"]
        assert "bilan_balance_minor_gap" in q["quality_flags"]

    def test_mismatch_beyond_relaxed(self):
        q = _quality_bilan(self._minimal_bilan(1_000_000.0, 1_200_000.0))
        assert q["ready_for_ai"] is False
        assert "bilan_balance_mismatch" in q["quality_flags"]

    def test_non_numeric_totals_flagged(self):
        fields = self._minimal_bilan(1_000_000.0, 1_000_000.0)
        fields["total_actif"] = _field("not-a-number")
        q = _quality_bilan(fields)
        assert "bilan_balance_mismatch" in q["quality_flags"]


class TestQualityCompteResultat:
    def _minimal_cr(
        self,
        rex: float,
        rc: float,
        rn: float,
        ca: float = 5_000_000.0,
        charges_ex: float = 1_000_000.0,
    ) -> dict:
        return {
            "chiffre_affaires": _field(ca),
            "charges_externes": _field(charges_ex),
            "resultat_exploitation": _field(rex),
            "resultat_courant": _field(rc),
            "resultat_net": _field(rn),
        }

    def test_chain_coherent_no_minor(self):
        q = _quality_compte_resultat(self._minimal_cr(500_000.0, 520_000.0, 510_000.0))
        assert q["ready_for_ai"] is True
        assert "result_chain_inconsistent" not in q["quality_flags"]
        assert "result_chain_minor_gap" not in q["quality_flags"]

    def test_chain_minor_gap_rex_rc_band(self):
        # Ancre |REX| = 500k → tol_strict 750k, tol_relaxed 1M ; delta RC−REX = 900k
        rex = 500_000.0
        rc = rex + 900_000.0
        rn = rc
        q = _quality_compte_resultat(self._minimal_cr(rex, rc, rn))
        assert q["ready_for_ai"] is True
        assert "result_chain_inconsistent" not in q["quality_flags"]
        assert "result_chain_minor_gap" in q["quality_flags"]

    def test_chain_inconsistent_large_jump(self):
        # |REX| petit, RC énorme → dépasse 2×|REX| (500k plafond mini)
        q = _quality_compte_resultat(self._minimal_cr(100_000.0, 2_000_000.0, 2_000_000.0))
        assert q["ready_for_ai"] is False
        assert "result_chain_inconsistent" in q["quality_flags"]

    def test_non_numeric_chain_flagged(self):
        f = self._minimal_cr(100_000.0, 100_000.0, 100_000.0)
        f["resultat_courant"] = _field("x")
        q = _quality_compte_resultat(f)
        assert "result_chain_inconsistent" in q["quality_flags"]

    def test_metadata_deltas(self):
        q = _quality_compte_resultat(self._minimal_cr(500_000.0, 520_000.0, 510_000.0))
        assert q["cr_chain_delta_rex_rc"] == 20_000.0
        assert q["cr_chain_delta_rc_rn"] == 10_000.0
        assert q["cr_chain_tol_relaxed_rex_rc"] == 1_000_000.0  # max(500k, 2×500k)
        assert q["cr_chain_tol_relaxed_rc_rn"] == 1_040_000.0  # max(500k, 2×520k)
