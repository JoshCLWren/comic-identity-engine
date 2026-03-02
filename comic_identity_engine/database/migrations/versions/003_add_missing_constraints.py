"""Add missing unique constraints and indexes.

Revision ID: 003
Revises: 002
Create Date: 2026-03-01 17:00

This migration adds:
1. Unique constraint on variants(issue_id, variant_suffix)
2. Unique constraint on external_mappings(source, source_issue_id)

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Perform database upgrade."""
    op.create_unique_constraint(
        "uq_variants_issue_id_variant_suffix",
        "variants",
        ["issue_id", "variant_suffix"],
    )
    op.create_unique_constraint(
        "uq_external_mappings_source_source_issue_id",
        "external_mappings",
        ["source", "source_issue_id"],
    )


def downgrade() -> None:
    """Perform database downgrade."""
    op.drop_constraint(
        "uq_external_mappings_source_source_issue_id",
        "external_mappings",
        type_="unique",
    )
    op.drop_constraint(
        "uq_variants_issue_id_variant_suffix",
        "variants",
        type_="unique",
    )
