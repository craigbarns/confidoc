"""Tests for beta lead schemas and model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.lead import BetaLeadCreate


def test_beta_lead_model_has_expected_columns():
    from app.models.beta_lead import BetaLead

    cols = {c.name for c in BetaLead.__table__.columns}

    assert "email" in cols
    assert "company" in cols
    assert "use_case" in cols
    assert "consent_to_contact" in cols
    assert "metadata_json" in cols


def test_beta_lead_schema_strips_and_normalizes_source():
    payload = BetaLeadCreate(
        email="DPO@CABINET.FR",
        full_name="  Marie   Martin  ",
        company=" Cabinet   Martin ",
        use_case="Nous voulons tester ConfiDoc sur des bilans clients.",
        source=" Landing Beta Form ",
        consent_to_contact=True,
    )

    assert payload.full_name == "Marie Martin"
    assert payload.company == "Cabinet Martin"
    assert payload.source == "landing_beta_form"


def test_beta_lead_schema_requires_consent():
    with pytest.raises(ValidationError):
        BetaLeadCreate(
            email="dpo@cabinet.fr",
            full_name="Marie Martin",
            company="Cabinet Martin",
            use_case="Nous voulons tester ConfiDoc sur des bilans clients.",
            consent_to_contact=False,
        )
