"""Add client_name, exercice, doc_category to documents

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-04-26 00:00:00.000000

"""

from alembic import op

revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE documents
            ADD COLUMN IF NOT EXISTS client_name varchar(120),
            ADD COLUMN IF NOT EXISTS exercice varchar(9),
            ADD COLUMN IF NOT EXISTS doc_category varchar(30)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_documents_client_exercice
            ON documents (uploaded_by_user_id, client_name, exercice)
        """
    )
    op.execute(
        """
        UPDATE documents
        SET client_name = tags[1]
        WHERE tags IS NOT NULL
          AND array_length(tags, 1) >= 1
          AND client_name IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_documents_client_exercice")
    op.execute(
        """
        ALTER TABLE documents
            DROP COLUMN IF EXISTS doc_category,
            DROP COLUMN IF EXISTS exercice,
            DROP COLUMN IF EXISTS client_name
        """
    )
