"""Initial migration - create failed_trials table

Revision ID: 001_initial
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'failed_trials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nct_id', sa.String(length=20), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('condition', sa.Text(), nullable=True),
        sa.Column('drug_name', sa.Text(), nullable=True),
        sa.Column('phase', sa.String(length=50), nullable=True),
        sa.Column('overall_status', sa.String(length=50), nullable=True),
        sa.Column('why_stopped', sa.Text(), nullable=True),
        sa.Column('failure_category', sa.String(length=100), nullable=True),
        sa.Column('salvageability_score', sa.Integer(), nullable=True),
        sa.Column('recommended_actions', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('sponsor', sa.Text(), nullable=True),
        sa.Column('start_date', sa.String(length=20), nullable=True),
        sa.Column('completion_date', sa.String(length=20), nullable=True),
        sa.Column('enrollment', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_failed_trials_id'), 'failed_trials', ['id'], unique=False)
    op.create_index(op.f('ix_failed_trials_nct_id'), 'failed_trials', ['nct_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_failed_trials_nct_id'), table_name='failed_trials')
    op.drop_index(op.f('ix_failed_trials_id'), table_name='failed_trials')
    op.drop_table('failed_trials')
