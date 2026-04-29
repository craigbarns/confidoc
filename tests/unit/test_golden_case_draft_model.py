"""Schema-level checks for the GoldenCaseDraft table."""

from __future__ import annotations


def test_table_has_required_columns():
    from app.models.golden_case_draft import GoldenCaseDraft

    cols = GoldenCaseDraft.__table__.columns
    required = {
        "id",
        "org_id",
        "document_id",
        "created_by_user_id",
        "field_name",
        "predicted_value",
        "corrected_value",
        "source_snippet",
        "error_type",
        "confidence_before",
        "document_type",
        "status",
        "created_at",
        "updated_at",
    }
    assert required.issubset(set(cols.keys()))


def test_required_indexes_present():
    from app.models.golden_case_draft import GoldenCaseDraft

    index_names = {idx.name for idx in GoldenCaseDraft.__table__.indexes}
    for expected in (
        "ix_golden_case_drafts_org_created",
        "ix_golden_case_drafts_org_status",
        "ix_golden_case_drafts_org_doc_type",
        "ix_golden_case_drafts_org_error_type",
    ):
        assert expected in index_names, f"missing index {expected}"


def test_org_id_is_indexed_and_not_null():
    from app.models.golden_case_draft import GoldenCaseDraft

    org_col = GoldenCaseDraft.__table__.c.org_id
    assert org_col.nullable is False
    assert org_col.index is True


def test_status_enum_values():
    from app.models.golden_case_draft import GoldenDraftStatus

    assert {s.value for s in GoldenDraftStatus} == {"draft", "accepted", "rejected"}


def test_sensitive_columns_use_encrypted_string():
    from app.models.golden_case_draft import GoldenCaseDraft
    from app.services.crypto_service import EncryptedString

    for name in ("predicted_value", "corrected_value", "source_snippet"):
        col_type = GoldenCaseDraft.__table__.c[name].type
        assert isinstance(col_type, EncryptedString), (
            f"column {name} must use EncryptedString to keep PII encrypted at rest"
        )
