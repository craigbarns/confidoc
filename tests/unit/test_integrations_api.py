"""Tests for API-first cabinet integrations."""

from app.services.integration_service import (
    API_KEY_PREFIX,
    build_request_hash,
    generate_api_key_value,
    is_api_key_token,
)


def test_api_key_generation_uses_public_prefix():
    key = generate_api_key_value()
    assert key.startswith(API_KEY_PREFIX)
    assert is_api_key_token(key)
    assert not is_api_key_token("not-a-confidoc-key")


def test_idempotency_hash_is_stable_and_sensitive_to_payload():
    first = build_request_hash(
        {
            "route": "POST /api/v1/uploads",
            "filename": "liasse.pdf",
            "sha256": "abc",
        }
    )
    same = build_request_hash(
        {
            "sha256": "abc",
            "filename": "liasse.pdf",
            "route": "POST /api/v1/uploads",
        }
    )
    different = build_request_hash(
        {
            "route": "POST /api/v1/uploads",
            "filename": "liasse-v2.pdf",
            "sha256": "abc",
        }
    )
    assert first == same
    assert first != different


def test_integration_models_expose_expected_columns():
    from app.models.integration import ApiKey, IdempotencyRecord, WebhookEndpoint

    api_key_cols = {column.name for column in ApiKey.__table__.columns}
    assert {"key_hash", "key_prefix", "scopes", "last_used_at"} <= api_key_cols

    webhook_cols = {column.name for column in WebhookEndpoint.__table__.columns}
    assert {"url", "signing_secret", "events", "failure_count"} <= webhook_cols

    idempotency_cols = {column.name for column in IdempotencyRecord.__table__.columns}
    assert {"idempotency_key", "request_hash", "response_body", "status_code"} <= idempotency_cols


def test_integrations_router_routes_exist():
    from app.api.v1.integrations import router

    paths = {route.path for route in router.routes}
    assert "/api-keys" in paths
    assert "/webhooks" in paths
    assert "/webhooks/{webhook_id}/test" in paths
    assert "/guide" in paths
