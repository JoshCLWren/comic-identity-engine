"""Add review fields to mapping_corrections

Revision ID: 009
Revises: 008
Create Date: 2024-03-10

"""

from alembic import op
import sqlalchemy as sa


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mapping_corrections",
        sa.Column(
            "review_status", sa.String(50), nullable=False, server_default="pending"
        ),
    )
    op.add_column(
        "mapping_corrections",
        sa.Column("reviewed_by", sa.String(255), nullable=True),
    )
    op.add_column(
        "mapping_corrections",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "mapping_corrections",
        sa.Column("review_notes", sa.Text(), nullable=True),
    )

    op.create_index(
        "ix_mapping_corrections_review_status",
        "mapping_corrections",
        ["review_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mapping_corrections_review_status", table_name="mapping_corrections"
    )
    op.drop_column("mapping_corrections", "review_notes")
    op.drop_column("mapping_corrections", "reviewed_at")
    op.drop_column("mapping_corrections", "reviewed_by")
    op.drop_column("mapping_corrections", "review_status")
