"""Tests for centralized audit trail safeguards."""

import uuid

from app.services.audit_trail_service import (
    build_audit_event_hash,
    sanitize_audit_details,
)


def test_sanitize_audit_details_redacts_sensitive_values():
    details = sanitize_audit_details(
        {
            "profile": "strict",
            "raw_text": "Mme Claire Moreau claire.moreau@example.fr",
            "token": "secret-token",
            "text_length": 42,
        }
    )

    assert details is not None
    assert details["profile"] == "strict"
    assert details["raw_text"]["redacted"] is True
    assert details["token"]["redacted"] is True
    assert "Claire" not in str(details)
    # Keys containing "text" are conservatively redacted to avoid PII leaks.
    assert details["text_length"]["redacted"] is True


def test_sanitize_audit_details_keeps_safe_structured_metadata():
    org_id = uuid.uuid4()
    details = sanitize_audit_details(
        {
            "org_id": org_id,
            "entity_summary": {"EMAIL": 2, "IBAN": 1},
            "pages": 3,
        }
    )

    assert details == {
        "org_id": str(org_id),
        "entity_summary": {"EMAIL": 2, "IBAN": 1},
        "pages": 3,
    }


def test_build_audit_event_hash_is_stable_for_same_payload():
    payload = {
        "action": "pipeline:anonymize",
        "resource_type": "document",
        "resource_id": str(uuid.uuid4()),
        "method": "SYSTEM",
        "path": "pipeline:pipeline:anonymize",
        "status_code": 200,
        "user_id": str(uuid.uuid4()),
        "org_id": str(uuid.uuid4()),
        "details": {"detections_count": 12},
    }

    first = build_audit_event_hash(**payload)
    second = build_audit_event_hash(**payload)

    assert first == second
    assert len(first) == 64
