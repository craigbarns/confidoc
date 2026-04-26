"""Add API integration tables

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-04-26 00:00:00.000000

"""

from alembic import op

revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            id uuid PRIMARY KEY,
            created_at timestamp with time zone NOT NULL DEFAULT now(),
            updated_at timestamp with time zone NOT NULL DEFAULT now(),
            org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            created_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
            name varchar(120) NOT NULL,
            key_prefix varchar(40) NOT NULL,
            key_hash varchar(64) NOT NULL UNIQUE,
            scopes varchar(80)[],
            is_active boolean NOT NULL DEFAULT true,
            last_used_at timestamp with time zone,
            expires_at timestamp with time zone,
            revoked_at timestamp with time zone
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_api_keys_key_hash ON api_keys (key_hash);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_api_keys_key_prefix ON api_keys (key_prefix);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_api_keys_org_id ON api_keys (org_id);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_api_keys_org_active ON api_keys (org_id, is_active);"
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_api_keys_user_active
            ON api_keys (created_by_user_id, is_active)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS webhook_endpoints (
            id uuid PRIMARY KEY,
            created_at timestamp with time zone NOT NULL DEFAULT now(),
            updated_at timestamp with time zone NOT NULL DEFAULT now(),
            org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            created_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
            name varchar(120) NOT NULL,
            url varchar(2048) NOT NULL,
            signing_secret text NOT NULL,
            events varchar(80)[],
            is_active boolean NOT NULL DEFAULT true,
            failure_count integer NOT NULL DEFAULT 0,
            last_success_at timestamp with time zone,
            last_failure_at timestamp with time zone
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_webhook_endpoints_org_id ON webhook_endpoints (org_id);")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_webhook_endpoints_org_active
            ON webhook_endpoints (org_id, is_active)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS idempotency_records (
            id uuid PRIMARY KEY,
            created_at timestamp with time zone NOT NULL DEFAULT now(),
            updated_at timestamp with time zone NOT NULL DEFAULT now(),
            org_id uuid REFERENCES organizations(id) ON DELETE CASCADE,
            created_by_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            document_id uuid REFERENCES documents(id) ON DELETE SET NULL,
            route varchar(120) NOT NULL,
            idempotency_key varchar(180) NOT NULL,
            request_hash varchar(64) NOT NULL,
            status_code integer NOT NULL,
            response_body jsonb NOT NULL,
            expires_at timestamp with time zone,
            CONSTRAINT uix_idempotency_user_route_key
                UNIQUE (created_by_user_id, route, idempotency_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_idempotency_org_created
            ON idempotency_records (org_id, created_at)
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_idempotency_expires_at ON idempotency_records (expires_at);"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS webhook_deliveries (
            id uuid PRIMARY KEY,
            created_at timestamp with time zone NOT NULL DEFAULT now(),
            updated_at timestamp with time zone NOT NULL DEFAULT now(),
            org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            endpoint_id uuid NOT NULL REFERENCES webhook_endpoints(id) ON DELETE CASCADE,
            document_id uuid REFERENCES documents(id) ON DELETE SET NULL,
            event varchar(80) NOT NULL,
            event_id varchar(80) NOT NULL,
            status varchar(30) NOT NULL DEFAULT 'pending',
            attempts integer NOT NULL DEFAULT 0,
            status_code integer,
            error text,
            response_body_preview text,
            payload jsonb NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_endpoint_created
            ON webhook_deliveries (endpoint_id, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_org_created
            ON webhook_deliveries (org_id, created_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS webhook_deliveries;")
    op.execute("DROP TABLE IF EXISTS idempotency_records;")
    op.execute("DROP TABLE IF EXISTS webhook_endpoints;")
    op.execute("DROP TABLE IF EXISTS api_keys;")
