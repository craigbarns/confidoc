"""Add soft delete columns, composite indexes, and OCR config

Revision ID: c2d3e4f5a6b7
Revises: b1a2c3d4e5f6
Create Date: 2026-03-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c2d3e4f5a6b7'
down_revision = 'b1a2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Soft delete columns on documents ---
    op.add_column('documents', sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('documents', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_documents_is_deleted', 'documents', ['is_deleted'])

    # --- Composite indexes for performance ---
    op.create_index('ix_documents_user_created', 'documents', ['uploaded_by_user_id', 'created_at'])
    op.create_index('ix_documents_org_created', 'documents', ['org_id', 'created_at'])
    op.create_index('ix_documents_user_active', 'documents', ['uploaded_by_user_id', 'is_deleted'])
    op.create_index('ix_documents_org_status', 'documents', ['org_id', 'status'])


def downgrade() -> None:
    op.drop_index('ix_documents_org_status', table_name='documents')
    op.drop_index('ix_documents_user_active', table_name='documents')
    op.drop_index('ix_documents_org_created', table_name='documents')
    op.drop_index('ix_documents_user_created', table_name='documents')
    op.drop_index('ix_documents_is_deleted', table_name='documents')
    op.drop_column('documents', 'deleted_at')
    op.drop_column('documents', 'is_deleted')
