"""Add human_feedback table

Revision ID: b1a2c3d4e5f6
Revises: 
Create Date: 2026-03-21 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'b1a2c3d4e5f6'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        'human_feedbacks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('doc_type', sa.String(length=50), nullable=False),
        sa.Column('profile_used', sa.String(length=50), nullable=False),
        sa.Column('feedback_type', sa.String(length=50), nullable=False),
        sa.Column('original_value_hash', sa.String(length=64), nullable=True),
        sa.Column('corrected_value_hash', sa.String(length=64), nullable=True),
        sa.Column('entity_type', sa.String(length=50), nullable=True),
        sa.Column('original_label', sa.String(length=50), nullable=True),
        sa.Column('corrected_label', sa.String(length=50), nullable=True),
        sa.Column('action_taken', sa.String(length=50), nullable=True),
        sa.Column('source_page', sa.Integer(), nullable=True),
        sa.Column('source_span_start', sa.Integer(), nullable=True),
        sa.Column('source_span_end', sa.Integer(), nullable=True),
        sa.Column('review_comment', sa.Text(), nullable=True),
        sa.Column('applied_to_rules', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_human_feedbacks_document_id'), 'human_feedbacks', ['document_id'], unique=False)
    op.create_index(op.f('ix_human_feedbacks_user_id'), 'human_feedbacks', ['user_id'], unique=False)
    op.create_index(op.f('ix_human_feedbacks_organization_id'), 'human_feedbacks', ['organization_id'], unique=False)
    op.create_index(op.f('ix_human_feedbacks_feedback_type'), 'human_feedbacks', ['feedback_type'], unique=False)
    op.create_index(op.f('ix_human_feedbacks_applied_to_rules'), 'human_feedbacks', ['applied_to_rules'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_human_feedbacks_applied_to_rules'), table_name='human_feedbacks')
    op.drop_index(op.f('ix_human_feedbacks_feedback_type'), table_name='human_feedbacks')
    op.drop_index(op.f('ix_human_feedbacks_organization_id'), table_name='human_feedbacks')
    op.drop_index(op.f('ix_human_feedbacks_user_id'), table_name='human_feedbacks')
    op.drop_index(op.f('ix_human_feedbacks_document_id'), table_name='human_feedbacks')
    op.drop_table('human_feedbacks')
