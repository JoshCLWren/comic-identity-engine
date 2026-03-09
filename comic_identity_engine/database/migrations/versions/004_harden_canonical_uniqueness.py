"""Harden canonical series and issue uniqueness.

Revision ID: 004
Revises: 003
Create Date: 2026-03-09 09:00

This migration:
1. Consolidates duplicate canonical series and issues into deterministic winners
2. Repoints dependent rows to the surviving canonical entities
3. Adds database uniqueness for canonical series and issues

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Perform database upgrade."""
    op.execute(
        """
        BEGIN;

        CREATE TEMP TABLE tmp_series_resolution ON COMMIT DROP AS
        SELECT
            sr.id AS source_series_id,
            FIRST_VALUE(sr.id) OVER (
                PARTITION BY sr.title, sr.start_year
                ORDER BY sr.created_at, sr.id
            ) AS target_series_id
        FROM series_runs AS sr;

        CREATE TEMP TABLE tmp_series_publisher_fallback ON COMMIT DROP AS
        SELECT DISTINCT ON (resolution.target_series_id)
            resolution.target_series_id,
            source.publisher
        FROM tmp_series_resolution AS resolution
        JOIN series_runs AS source
            ON source.id = resolution.source_series_id
        WHERE source.publisher IS NOT NULL
        ORDER BY resolution.target_series_id, source.created_at, source.id;

        UPDATE series_runs AS winner
        SET publisher = COALESCE(winner.publisher, fallback.publisher)
        FROM tmp_series_publisher_fallback AS fallback
        WHERE winner.id = fallback.target_series_id;

        CREATE TEMP TABLE tmp_issue_resolution ON COMMIT DROP AS
        SELECT
            issue.id AS source_issue_id,
            FIRST_VALUE(issue.id) OVER (
                PARTITION BY series_resolution.target_series_id, issue.issue_number
                ORDER BY issue.created_at, issue.id
            ) AS target_issue_id,
            series_resolution.target_series_id
        FROM issues AS issue
        JOIN tmp_series_resolution AS series_resolution
            ON series_resolution.source_series_id = issue.series_run_id;

        CREATE TEMP TABLE tmp_issue_cover_date_fallback ON COMMIT DROP AS
        SELECT DISTINCT ON (resolution.target_issue_id)
            resolution.target_issue_id,
            source.cover_date
        FROM tmp_issue_resolution AS resolution
        JOIN issues AS source
            ON source.id = resolution.source_issue_id
        WHERE source.cover_date IS NOT NULL
        ORDER BY resolution.target_issue_id, source.created_at, source.id;

        CREATE TEMP TABLE tmp_issue_upc_fallback ON COMMIT DROP AS
        SELECT DISTINCT ON (resolution.target_issue_id)
            resolution.target_issue_id,
            source.upc
        FROM tmp_issue_resolution AS resolution
        JOIN issues AS source
            ON source.id = resolution.source_issue_id
        WHERE source.upc IS NOT NULL
        ORDER BY resolution.target_issue_id, source.created_at, source.id;

        UPDATE issues AS winner
        SET cover_date = COALESCE(winner.cover_date, fallback.cover_date)
        FROM tmp_issue_cover_date_fallback AS fallback
        WHERE winner.id = fallback.target_issue_id;

        UPDATE issues AS winner
        SET upc = COALESCE(winner.upc, fallback.upc)
        FROM tmp_issue_upc_fallback AS fallback
        WHERE winner.id = fallback.target_issue_id;

        CREATE TEMP TABLE tmp_variant_resolution ON COMMIT DROP AS
        SELECT
            variant.id AS source_variant_id,
            FIRST_VALUE(variant.id) OVER (
                PARTITION BY issue_resolution.target_issue_id, variant.variant_suffix
                ORDER BY variant.created_at, variant.id
            ) AS target_variant_id,
            issue_resolution.target_issue_id
        FROM variants AS variant
        JOIN tmp_issue_resolution AS issue_resolution
            ON issue_resolution.source_issue_id = variant.issue_id;

        UPDATE variants AS variant
        SET issue_id = resolution.target_issue_id
        FROM tmp_variant_resolution AS resolution
        WHERE variant.id = resolution.source_variant_id
          AND variant.id = resolution.target_variant_id
          AND variant.issue_id <> resolution.target_issue_id;

        DELETE FROM variants AS variant
        USING tmp_variant_resolution AS resolution
        WHERE variant.id = resolution.source_variant_id
          AND variant.id <> resolution.target_variant_id;

        UPDATE external_mappings AS mapping
        SET issue_id = resolution.target_issue_id
        FROM tmp_issue_resolution AS resolution
        WHERE mapping.issue_id = resolution.source_issue_id
          AND mapping.issue_id <> resolution.target_issue_id;

        DELETE FROM issues AS issue
        USING tmp_issue_resolution AS resolution
        WHERE issue.id = resolution.source_issue_id
          AND resolution.source_issue_id <> resolution.target_issue_id;

        UPDATE issues AS issue
        SET series_run_id = resolution.target_series_id
        FROM tmp_issue_resolution AS resolution
        WHERE issue.id = resolution.source_issue_id
          AND resolution.source_issue_id = resolution.target_issue_id
          AND issue.series_run_id <> resolution.target_series_id;

        DELETE FROM series_runs AS series
        USING tmp_series_resolution AS resolution
        WHERE series.id = resolution.source_series_id
          AND resolution.source_series_id <> resolution.target_series_id;

        COMMIT;
        """
    )

    op.create_unique_constraint(
        "uq_series_runs_title_start_year",
        "series_runs",
        ["title", "start_year"],
    )
    op.create_unique_constraint(
        "uq_issues_series_run_id_issue_number",
        "issues",
        ["series_run_id", "issue_number"],
    )


def downgrade() -> None:
    """Perform database downgrade."""
    op.drop_constraint(
        "uq_issues_series_run_id_issue_number",
        "issues",
        type_="unique",
    )
    op.drop_constraint(
        "uq_series_runs_title_start_year",
        "series_runs",
        type_="unique",
    )
