"""Harden audit trail metadata

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-05 00:00:00.000000

"""

from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id uuid PRIMARY KEY,
            created_at timestamp with time zone NOT NULL DEFAULT now(),
            updated_at timestamp with time zone NOT NULL DEFAULT now(),
            actor_type varchar(20) NOT NULL DEFAULT 'user',
            user_id uuid REFERENCES users(id) ON DELETE SET NULL,
            org_id uuid,
            action varchar(80) NOT NULL,
            resource_type varchar(40) NOT NULL,
            resource_id varchar(64),
            method varchar(10) NOT NULL,
            path varchar(500) NOT NULL,
            status_code integer NOT NULL,
            ip_address varchar(45),
            user_agent varchar(500),
            request_id varchar(64),
            event_hash varchar(64),
            details jsonb
        )
        """
    )
    op.execute(
        """
        ALTER TABLE audit_logs
            ADD COLUMN IF NOT EXISTS actor_type varchar(20) NOT NULL DEFAULT 'user',
            ADD COLUMN IF NOT EXISTS request_id varchar(64),
            ADD COLUMN IF NOT EXISTS event_hash varchar(64)
        """
    )
    for column in (
        "actor_type",
        "user_id",
        "org_id",
        "action",
        "resource_type",
        "resource_id",
        "request_id",
        "event_hash",
    ):
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_audit_logs_{column} ON audit_logs ({column})"
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_event_hash;")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_request_id;")
    op.execute("ALTER TABLE audit_logs DROP COLUMN IF EXISTS event_hash;")
    op.execute("ALTER TABLE audit_logs DROP COLUMN IF EXISTS request_id;")
    op.execute("ALTER TABLE audit_logs DROP COLUMN IF EXISTS actor_type;")
