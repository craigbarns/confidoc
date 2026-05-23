from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.api.v1._doc_stats import (
    _created_last_7_days,
    _document_to_dossier_360_input,
    _risk_score_percent,
)
from app.models.document import DocumentStatus


def test_risk_score_percent_normalizes_fraction_and_bounds() -> None:
    assert _risk_score_percent(None) == 0.0
    assert _risk_score_percent(0.82) == 82
    assert _risk_score_percent(82) == 82
    assert _risk_score_percent(150) == 100


def test_document_to_dossier_360_input_preserves_cabinet_metadata() -> None:
    created_at = datetime(2026, 5, 20, tzinfo=UTC)
    document = SimpleNamespace(
        id="doc-1",
        original_filename="liasse_2025.pdf",
        status=DocumentStatus.READY,
        tags=[],
        client_name="Cabinet Test",
        doc_type=None,
        doc_category="liasse_fiscale",
        exercice="2025",
        created_at=created_at,
        updated_at=created_at,
    )

    payload = _document_to_dossier_360_input(document)  # type: ignore[arg-type]

    assert payload["client_name"] == "Cabinet Test"
    assert payload["tags"] == ["Cabinet Test"]
    assert payload["doc_type"] == "liasse_fiscale"
    assert payload["doc_category"] == "liasse_fiscale"
    assert payload["exercice"] == "2025"


def test_created_last_7_days_returns_dense_daily_series() -> None:
    now = datetime(2026, 5, 23, 14, 0, tzinfo=UTC)
    series = _created_last_7_days(
        [
            now,
            now - timedelta(days=1),
            now - timedelta(days=1, hours=2),
            now - timedelta(days=9),
        ],
        now,
    )

    assert len(series) == 7
    assert series[-1] == {"date": "2026-05-23", "count": 1}
    assert series[-2] == {"date": "2026-05-22", "count": 2}
    assert series[0] == {"date": "2026-05-17", "count": 0}
