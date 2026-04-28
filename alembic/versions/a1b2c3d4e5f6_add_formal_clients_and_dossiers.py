"""Add formal clients and dossiers tables

Revision ID: a1b2c3d4e5f6
Revises: f5a6b7c8d9e0
Create Date: 2026-04-27 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a1b2c3d4e5f6"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create clients table
    op.create_table(
        "clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("external_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_clients_name"), "clients", ["name"], unique=False)
    op.create_index(op.f("ix_clients_org_id"), "clients", ["org_id"], unique=False)
    op.create_index(op.f("ix_clients_external_id"), "clients", ["external_id"], unique=False)

    # 2. Create dossiers table
    op.create_table(
        "dossiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exercice", sa.String(length=9), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", "exercice", name="uq_dossier_client_exercice"),
    )
    op.create_index(op.f("ix_dossiers_exercice"), "dossiers", ["exercice"], unique=False)
    op.create_index(op.f("ix_dossiers_org_id"), "dossiers", ["org_id"], unique=False)

    # 3. Add columns to documents
    op.add_column("documents", sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("documents", sa.Column("dossier_id", postgresql.UUID(as_uuid=True), nullable=True))
    
    op.create_index(op.f("ix_documents_client_id"), "documents", ["client_id"], unique=False)
    op.create_index(op.f("ix_documents_dossier_id"), "documents", ["dossier_id"], unique=False)
    
    op.create_foreign_key("fk_documents_client_id", "documents", "clients", ["client_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_documents_dossier_id", "documents", "dossiers", ["dossier_id"], ["id"], ondelete="SET NULL")

    # 4. Data migration: populate clients and dossiers from existing client_name/exercice
    # We use raw SQL to ensure it works even if models change later
    op.execute("""
        INSERT INTO clients (id, org_id, name, created_at, updated_at, is_deleted)
        SELECT gen_random_uuid(), org_id, client_name, now(), now(), false
        FROM (
            SELECT DISTINCT ON (org_id, client_name) org_id, client_name
            FROM documents
            WHERE client_name IS NOT NULL AND client_id IS NULL AND org_id IS NOT NULL
        ) sub
        ON CONFLICT DO NOTHING;
    """)
    
    op.execute("""
        UPDATE documents d
        SET client_id = c.id
        FROM clients c
        WHERE d.client_name = c.name AND d.org_id = c.org_id AND d.client_id IS NULL;
    """)
    
    op.execute("""
        INSERT INTO dossiers (id, org_id, client_id, exercice, created_at, updated_at, is_deleted)
        SELECT gen_random_uuid(), org_id, client_id, exercice, now(), now(), false
        FROM (
            SELECT DISTINCT ON (client_id, exercice) org_id, client_id, exercice
            FROM documents
            WHERE exercice IS NOT NULL AND client_id IS NOT NULL AND dossier_id IS NULL
        ) sub
        ON CONFLICT (client_id, exercice) DO NOTHING;
    """)
    
    op.execute("""
        UPDATE documents d
        SET dossier_id = ds.id
        FROM dossiers ds
        WHERE d.client_id = ds.client_id AND d.exercice = ds.exercice AND d.org_id = ds.org_id AND d.dossier_id IS NULL;
    """)


def downgrade() -> None:
    op.drop_constraint("fk_documents_dossier_id", "documents", type_="foreignkey")
    op.drop_constraint("fk_documents_client_id", "documents", type_="foreignkey")
    op.drop_index(op.f("ix_documents_dossier_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_client_id"), table_name="documents")
    op.drop_column("documents", "dossier_id")
    op.drop_column("documents", "client_id")
    op.drop_table("dossiers")
    op.drop_table("clients")
