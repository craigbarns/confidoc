"""Add timestamp defaults to clients and dossiers

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-29 11:40:00.000000

"""

from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table_name in ("clients", "dossiers"):
        op.execute(
            f"""
            ALTER TABLE {table_name}
                ALTER COLUMN created_at SET DEFAULT now(),
                ALTER COLUMN updated_at SET DEFAULT now()
            """
        )


def downgrade() -> None:
    for table_name in ("clients", "dossiers"):
        op.execute(
            f"""
            ALTER TABLE {table_name}
                ALTER COLUMN created_at DROP DEFAULT,
                ALTER COLUMN updated_at DROP DEFAULT
            """
        )
