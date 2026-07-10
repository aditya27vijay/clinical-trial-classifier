"""add resolution quality usage timeline real world usage

Revision ID: 45e656f534a2
Revises: 001_initial
Create Date: 2026-07-10 04:49:23.525886

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '45e656f534a2'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # molecules: resolution-quality + real-world-usage + timeline-bounds columns
    op.add_column("molecules", sa.Column("resolution_method", sa.String(30), nullable=True))
    op.add_column("molecules", sa.Column("resolution_conflict", sa.Boolean(), nullable=True, server_default=sa.false()))
    op.add_column("molecules", sa.Column("is_combination", sa.Boolean(), nullable=True, server_default=sa.false()))
    op.add_column("molecules", sa.Column("combination_components", sa.JSON(), nullable=True))
    op.add_column("molecules", sa.Column("drugbank_id", sa.String(20), nullable=True))
    op.add_column("molecules", sa.Column("approval_status", sa.String(30), nullable=True))
    op.add_column("molecules", sa.Column("first_studied", sa.Date(), nullable=True))
    op.add_column("molecules", sa.Column("last_active", sa.Date(), nullable=True))
    op.create_index("ix_molecules_drugbank_id", "molecules", ["drugbank_id"])
 
    # molecule_trials: usage-timeline columns ("when and where it was used")
    op.add_column("molecule_trials", sa.Column("sponsor", sa.String(300), nullable=True))
    op.add_column("molecule_trials", sa.Column("status", sa.String(50), nullable=True))
    op.add_column("molecule_trials", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("molecule_trials", sa.Column("completion_date", sa.Date(), nullable=True))
    op.add_column("molecule_trials", sa.Column("why_stopped", sa.Text(), nullable=True))
 
    # new table: molecule_real_world_usage
    op.create_table(
        "molecule_real_world_usage",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("molecule_id", sa.BigInteger(),
                  sa.ForeignKey("molecules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("indication", sa.String(300), nullable=False),
        sa.Column("disease_id", sa.String(30), nullable=True),
        sa.Column("approval_status", sa.String(30), nullable=True),
        sa.Column("region", sa.String(10), nullable=True),
        sa.Column("association_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("approved_date", sa.Date(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("external_id", sa.String(30), nullable=True),
        sa.UniqueConstraint("molecule_id", "indication", "source",
                             name="uq_molecule_indication_source"),
    )
 
 
def downgrade() -> None:
    op.drop_table("molecule_real_world_usage")
 
    op.drop_column("molecule_trials", "why_stopped")
    op.drop_column("molecule_trials", "completion_date")
    op.drop_column("molecule_trials", "start_date")
    op.drop_column("molecule_trials", "status")
    op.drop_column("molecule_trials", "sponsor")
 
    op.drop_index("ix_molecules_drugbank_id", table_name="molecules")
    op.drop_column("molecules", "last_active")
    op.drop_column("molecules", "first_studied")
    op.drop_column("molecules", "approval_status")
    op.drop_column("molecules", "drugbank_id")
    op.drop_column("molecules", "combination_components")
    op.drop_column("molecules", "is_combination")
    op.drop_column("molecules", "resolution_conflict")
    op.drop_column("molecules", "resolution_method")