from app.services.dossier_360_service import build_dossier_360


def test_dossier_360_prioritizes_incomplete_high_risk_client() -> None:
    documents = [
        {
            "id": "doc-alpha-bilan",
            "original_filename": "bilan_alpha_2025.pdf",
            "status": "ready",
            "doc_type": "bilan",
            "tags": ["Alpha"],
        },
        {
            "id": "doc-alpha-facture",
            "original_filename": "facture_alpha.pdf",
            "status": "uploaded",
            "doc_type": "facture",
            "tags": ["Alpha"],
        },
        {
            "id": "doc-beta-liasse",
            "original_filename": "liasse_beta_2025.pdf",
            "status": "ready",
            "doc_type": "liasse_fiscale",
            "tags": ["Beta"],
        },
        {
            "id": "doc-beta-bank",
            "original_filename": "releve_bancaire_beta.pdf",
            "status": "ready",
            "doc_type": "releve_bancaire",
            "tags": ["Beta"],
        },
    ]

    payload = build_dossier_360(
        documents,
        risk_by_document={"doc-alpha-bilan": 72.0, "doc-beta-liasse": 12.0},
        entity_counts_by_document={"doc-alpha-bilan": 8, "doc-alpha-facture": 2},
        limit=5,
    )

    assert payload["portfolio"]["clients_count"] == 2
    assert payload["portfolio"]["at_risk_dossiers"] == 1
    assert payload["dossiers"][0]["client_name"] == "Alpha"
    assert payload["dossiers"][0]["risk_level"] == "high"
    assert payload["dossiers"][0]["entity_count"] == 10
    assert payload["dossiers"][0]["missing_documents"]
    assert any("anonymisation" in action for action in payload["dossiers"][0]["next_actions"])
    assert payload["mission_control"]["urgency"] == "danger"
    assert "securiser" in payload["mission_control"]["headline"]
    assert any("Alpha" in action for action in payload["mission_control"]["next_best_actions"])
    assert "Completeness des pieces justificatives" in payload["mission_control"]["audit_focus"]


def test_dossier_360_handles_empty_portfolio() -> None:
    payload = build_dossier_360([])

    assert payload["portfolio"]["clients_count"] == 0
    assert payload["portfolio"]["average_score"] == 0
    assert payload["mission_control"]["urgency"] == "neutral"
    assert payload["mission_control"]["next_best_actions"]
    assert payload["dossiers"] == []
