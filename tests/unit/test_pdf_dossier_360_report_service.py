from app.services.pdf_dossier_360_report_service import generate_dossier_360_pdf


def test_generate_dossier_360_pdf_returns_pdf_bytes() -> None:
    payload = {
        "portfolio": {
            "clients_count": 1,
            "documents_count": 3,
            "average_score": 78,
            "ready_dossiers": 0,
            "at_risk_dossiers": 1,
            "critical_actions": 2,
            "top_missing_documents": [
                {"label": "Declaration fiscale ou TVA", "count": 1},
            ],
        },
        "dossiers": [
            {
                "client_name": "Client Demo",
                "score": 78,
                "readiness": "A completer",
                "risk_level": "high",
                "document_count": 3,
                "ready_count": 2,
                "entity_count": 12,
                "missing_documents": ["Declaration fiscale ou TVA"],
                "blockers": ["Piece cle manquante: Declaration fiscale ou TVA."],
                "next_actions": ["Ajouter: Declaration fiscale ou TVA."],
            }
        ],
    }

    pdf = generate_dossier_360_pdf(payload)

    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000
