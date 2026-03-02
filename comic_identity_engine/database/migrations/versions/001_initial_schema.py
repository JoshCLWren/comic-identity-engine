"""Initial schema for Comic Identity Engine.

Revision ID: 001
Revises:
Create Date: 2026-03-01 16:40

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Perform database upgrade."""
    op.create_table(
        "series_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("start_year", sa.Integer(), nullable=False),
        sa.Column("publisher", sa.String(500), nullable=True),
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
    )

    op.create_index("ix_series_runs_title", "series_runs", ["title"])
    op.create_index("ix_series_runs_start_year", "series_runs", ["start_year"])

    op.create_table(
        "issues",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "series_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("series_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("issue_number", sa.String(50), nullable=False),
        sa.Column("cover_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("upc", sa.String(50), nullable=True),
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
    )

    op.create_index("ix_issues_series_run_id", "issues", ["series_run_id"])
    op.create_index("ix_issues_issue_number", "issues", ["issue_number"])
    op.create_index("ix_issues_upc", "issues", ["upc"], unique=True)
    op.create_index(
        "ix_issues_series_run_id_issue_number",
        "issues",
        ["series_run_id", "issue_number"],
    )

    op.create_table(
        "variants",
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
        sa.Column("variant_suffix", sa.String(20), nullable=False),
        sa.Column("variant_name", sa.String(500), nullable=True),
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
    )

    op.create_index("ix_variants_issue_id", "variants", ["issue_id"])
    op.create_index("ix_variants_variant_suffix", "variants", ["variant_suffix"])

    op.create_table(
        "external_mappings",
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
        sa.Column("source_series_id", sa.String(500), nullable=True),
        sa.Column("source_issue_id", sa.String(500), nullable=False),
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
    )

    op.create_index("ix_external_mappings_issue_id", "external_mappings", ["issue_id"])
    op.create_index("ix_external_mappings_source", "external_mappings", ["source"])

    op.create_table(
        "operations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column("operation_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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
    )

    op.create_index("ix_operations_operation_type", "operations", ["operation_type"])
    op.create_index("ix_operations_status", "operations", ["status"])
    op.create_index("ix_operations_input_hash", "operations", ["input_hash"])


def downgrade() -> None:
    """Perform database downgrade."""
    op.drop_table("operations")
    op.drop_table("external_mappings")
    op.drop_table("variants")
    op.drop_table("issues")
    op.drop_table("series_runs")
