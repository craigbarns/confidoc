"""Add golden_case_drafts table (Data Flywheel)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-29 12:50:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "golden_case_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("field_name", sa.String(length=120), nullable=False),
        # Sensitive textual columns — stored encrypted at the application level
        # via EncryptedString (Fernet). The DB column itself is a plain string
        # of generous length to accommodate the ciphertext.
        sa.Column("predicted_value", sa.String(length=2000), nullable=True),
        sa.Column("corrected_value", sa.String(length=2000), nullable=False),
        sa.Column("source_snippet", sa.String(length=2000), nullable=True),
        sa.Column("error_type", sa.String(length=60), nullable=False),
        sa.Column("confidence_before", sa.Float(), nullable=True),
        sa.Column("document_type", sa.String(length=60), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('draft','accepted','rejected')",
            name="ck_golden_case_drafts_status",
        ),
    )

    op.create_index(
        op.f("ix_golden_case_drafts_org_id"),
        "golden_case_drafts",
        ["org_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_golden_case_drafts_document_id"),
        "golden_case_drafts",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_golden_case_drafts_created_by_user_id"),
        "golden_case_drafts",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_golden_case_drafts_status"),
        "golden_case_drafts",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_golden_case_drafts_document_type"),
        "golden_case_drafts",
        ["document_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_golden_case_drafts_error_type"),
        "golden_case_drafts",
        ["error_type"],
        unique=False,
    )

    # Composite indexes optimized for the common org-scoped queries.
    op.create_index(
        "ix_golden_case_drafts_org_created",
        "golden_case_drafts",
        ["org_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_golden_case_drafts_org_status",
        "golden_case_drafts",
        ["org_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_golden_case_drafts_org_doc_type",
        "golden_case_drafts",
        ["org_id", "document_type"],
        unique=False,
    )
    op.create_index(
        "ix_golden_case_drafts_org_error_type",
        "golden_case_drafts",
        ["org_id", "error_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_golden_case_drafts_org_error_type", table_name="golden_case_drafts"
    )
    op.drop_index(
        "ix_golden_case_drafts_org_doc_type", table_name="golden_case_drafts"
    )
    op.drop_index(
        "ix_golden_case_drafts_org_status", table_name="golden_case_drafts"
    )
    op.drop_index(
        "ix_golden_case_drafts_org_created", table_name="golden_case_drafts"
    )
    op.drop_index(
        op.f("ix_golden_case_drafts_error_type"), table_name="golden_case_drafts"
    )
    op.drop_index(
        op.f("ix_golden_case_drafts_document_type"),
        table_name="golden_case_drafts",
    )
    op.drop_index(
        op.f("ix_golden_case_drafts_status"), table_name="golden_case_drafts"
    )
    op.drop_index(
        op.f("ix_golden_case_drafts_created_by_user_id"),
        table_name="golden_case_drafts",
    )
    op.drop_index(
        op.f("ix_golden_case_drafts_document_id"), table_name="golden_case_drafts"
    )
    op.drop_index(
        op.f("ix_golden_case_drafts_org_id"), table_name="golden_case_drafts"
    )
    op.drop_table("golden_case_drafts")
