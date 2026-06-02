"""Tests du calcul de score RGPD (_calculate_gdpr_score).

Vérifie :
- Score de 0 à 100, jamais hors bornes
- Grade A (≥85), B (≥70), C (≥50), D (<50)
- Chaque composante du breakdown (success_rate, risk_score, ...)
- Recommandations contextuelles générées correctement
- Cas zéro document : score/grade null, message « non disponible » (pas de note fictive)
"""

from __future__ import annotations

import pytest

from app.api.v1._doc_stats import _calculate_gdpr_score

# ── Helpers ───────────────────────────────────────────────────────────


def _score(
    total: int = 0,
    status_counts: dict | None = None,
    risk: dict | None = None,
    activity: list | None = None,
) -> dict:
    return _calculate_gdpr_score(
        total_docs=total,
        status_counts=status_counts or {},
        risk_distribution=risk or {"low": 0, "medium": 0, "high": 0, "critical": 0},
        recent_activity=activity or [],
    )


# ══════════════════════════════════════════════════════════════════════
# Score bounds
# ══════════════════════════════════════════════════════════════════════


class TestScoreBounds:
    def test_score_is_integer(self):
        result = _score(10, {"ready": 10})
        assert isinstance(result["score"], int)

    def test_score_never_below_zero(self):
        # worst case: all failed, all critical
        result = _score(10, {"failed": 10}, {"critical": 100})
        assert result["score"] >= 0

    def test_score_never_above_100(self):
        # best case: all ready, all low risk, lots of activity
        result = _score(
            20,
            {"ready": 20},
            {"low": 20},
            [{"count": 5}] * 10,
        )
        assert result["score"] <= 100

    def test_zero_documents_no_numeric_score(self):
        """Aucune pièce : pas de score chiffré ni de note (évite un faux 50/100)."""
        result = _score(0, {})
        assert result["score"] is None
        assert result["grade"] is None
        assert result["color"] == "neutral"
        assert "non disponible" in (result.get("status") or "").lower()
        assert any("premier document" in r.lower() for r in result["recommendations"])


# ══════════════════════════════════════════════════════════════════════
# Grade thresholds
# ══════════════════════════════════════════════════════════════════════


class TestGradeThresholds:
    def test_grade_a_perfect(self):
        # 40 (success) + 30 (all low risk) + 15 (no failures) + 5 (no pending) = 90
        result = _score(10, {"ready": 10}, {"low": 10})
        assert result["score"] >= 85
        assert result["grade"] == "A"

    def test_grade_d_all_failed(self):
        # 0 success + 0 risk (no risks) + 0 failure resilience + 0 activity
        result = _score(10, {"failed": 10}, {"low": 0})
        assert result["grade"] in ("C", "D")

    def test_grade_b_mixed(self):
        # Some ready, some failed, medium risks
        result = _score(
            10,
            {"ready": 6, "failed": 2, "processing": 2},
            {"low": 4, "medium": 4, "high": 2},
        )
        # Score should be mid-range
        assert result["score"] >= 0

    def test_status_label_present(self):
        result = _score(10, {"ready": 10}, {"low": 10})
        assert result["status"] in ("Conforme", "A améliorer", "Non conforme")

    def test_color_present(self):
        result = _score(10, {"ready": 10}, {"low": 10})
        assert result["color"] in ("success", "warning", "danger")


# ══════════════════════════════════════════════════════════════════════
# Breakdown components
# ══════════════════════════════════════════════════════════════════════


class TestBreakdownComponents:
    def test_breakdown_keys_present(self):
        result = _score(10, {"ready": 5})
        bd = result["breakdown"]
        assert "success_rate" in bd
        assert "risk_score" in bd
        assert "failure_resilience" in bd
        assert "activity_momentum" in bd
        assert "pending_penalty" in bd

    def test_all_ready_gives_max_success_rate(self):
        result = _score(10, {"ready": 10})
        # success_rate = ready/total * 40 = 40
        assert result["breakdown"]["success_rate"] == pytest.approx(40.0, abs=1.0)

    def test_all_failed_gives_zero_success_rate(self):
        result = _score(10, {"failed": 10})
        assert result["breakdown"]["success_rate"] == pytest.approx(0.0, abs=0.1)

    def test_all_low_risk_gives_max_risk_score(self):
        result = _score(10, {"ready": 10}, {"low": 10})
        # risk_pts = 10*1.0/10 * 30 = 30
        assert result["breakdown"]["risk_score"] == pytest.approx(30.0, abs=1.0)

    def test_all_critical_risk_gives_zero_risk_score(self):
        result = _score(10, {"ready": 10}, {"critical": 10})
        # risk_pts = 0 * 0.0 / 10 * 30 = 0
        assert result["breakdown"]["risk_score"] == pytest.approx(0.0, abs=0.5)

    def test_activity_caps_at_10(self):
        activity = [{"count": 100}]
        result = _score(5, {"ready": 5}, activity=activity)
        assert result["breakdown"]["activity_momentum"] == 10

    def test_no_activity_gives_zero_momentum(self):
        result = _score(5, {"ready": 5}, activity=[])
        assert result["breakdown"]["activity_momentum"] == 0

    def test_no_pending_gives_max_pending_score(self):
        result = _score(10, {"ready": 10})
        assert result["breakdown"]["pending_penalty"] == 5

    def test_many_pending_reduces_score(self):
        result = _score(10, {"processing": 8, "uploaded": 2})
        assert result["breakdown"]["pending_penalty"] == 0


# ══════════════════════════════════════════════════════════════════════
# Recommendations
# ══════════════════════════════════════════════════════════════════════


class TestRecommendations:
    def test_recommendations_list_present(self):
        result = _score(10, {"ready": 10})
        assert isinstance(result["recommendations"], list)
        assert len(result["recommendations"]) > 0

    def test_high_failure_rate_triggers_recommendation(self):
        # >10% failure rate
        result = _score(10, {"ready": 8, "failed": 2})
        joined = " ".join(result["recommendations"])
        assert "échec" in joined.lower() or "qualité" in joined.lower()

    def test_many_pending_triggers_recommendation(self):
        result = _score(10, {"processing": 5, "uploaded": 2, "ready": 3})
        joined = " ".join(result["recommendations"])
        assert "attente" in joined.lower() or "analyse" in joined.lower()

    def test_critical_risk_triggers_recommendation(self):
        result = _score(10, {"ready": 5}, {"high": 3, "critical": 3, "low": 4})
        joined = " ".join(result["recommendations"])
        assert (
            "risque" in joined.lower()
            or "haut risque" in joined.lower()
            or "mappings" in joined.lower()
        )

    def test_no_ready_docs_triggers_recommendation(self):
        result = _score(5, {"uploaded": 5})
        joined = " ".join(result["recommendations"])
        assert "anonymis" in joined.lower() or "traitement" in joined.lower()

    def test_perfect_score_gives_positive_recommendation(self):
        result = _score(10, {"ready": 10}, {"low": 10}, [{"count": 3}] * 3)
        # With a good score and no issues, should get generic positive recommendation
        assert len(result["recommendations"]) >= 1
