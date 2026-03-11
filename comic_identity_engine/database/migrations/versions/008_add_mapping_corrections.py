"""Add mapping corrections table and external_mapping enhancements.

Revision ID: 008
Revises: 004
Create Date: 2026-03-10

This migration:
1. Creates mapping_corrections table for tracking user corrections
2. Adds is_accurate and source_url columns to external_mappings

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "008"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "external_mappings",
        sa.Column("is_accurate", sa.Boolean(), nullable=True, server_default="true"),
    )
    op.add_column(
        "external_mappings",
        sa.Column("source_url", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_external_mappings_is_accurate",
        "external_mappings",
        ["is_accurate"],
    )

    op.create_table(
        "mapping_corrections",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "issue_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("issues.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("original_source_issue_id", sa.String(500), nullable=False),
        sa.Column("correct_source_issue_id", sa.String(500), nullable=True),
        sa.Column(
            "correction_type",
            sa.String(50),
            nullable=False,
        ),
        sa.Column("user_notes", sa.Text(), nullable=True),
        sa.Column("corrected_by", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_mapping_corrections_issue_id",
        "mapping_corrections",
        ["issue_id"],
    )
    op.create_index(
        "ix_mapping_corrections_source",
        "mapping_corrections",
        ["source"],
    )
    op.create_index(
        "ix_mapping_corrections_correction_type",
        "mapping_corrections",
        ["correction_type"],
    )


def downgrade() -> None:
    op.drop_table("mapping_corrections")
    op.drop_index("ix_external_mappings_is_accurate", "external_mappings")
    op.drop_column("external_mappings", "source_url")
    op.drop_column("external_mappings", "is_accurate")
