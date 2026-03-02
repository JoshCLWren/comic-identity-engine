"""Seed X-Men #-1 with all platform mappings.

Revision ID: 002
Revises: 001
Create Date: 2026-03-01 16:45

"""

from typing import Sequence, Union
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Perform database upgrade."""
    from sqlalchemy.sql import table, column
    from sqlalchemy.dialects import postgresql

    series_runs_table = table(
        "series_runs",
        column("id", postgresql.UUID(as_uuid=True)),
        column("title", sa.String),
        column("start_year", sa.Integer),
        column("publisher", sa.String),
        column("created_at", sa.DateTime(timezone=True)),
        column("updated_at", sa.DateTime(timezone=True)),
    )

    issues_table = table(
        "issues",
        column("id", postgresql.UUID(as_uuid=True)),
        column("series_run_id", postgresql.UUID(as_uuid=True)),
        column("issue_number", sa.String),
        column("cover_date", sa.DateTime(timezone=True)),
        column("upc", sa.String),
        column("created_at", sa.DateTime(timezone=True)),
        column("updated_at", sa.DateTime(timezone=True)),
    )

    variants_table = table(
        "variants",
        column("id", postgresql.UUID(as_uuid=True)),
        column("issue_id", postgresql.UUID(as_uuid=True)),
        column("variant_suffix", sa.String),
        column("variant_name", sa.String),
        column("created_at", sa.DateTime(timezone=True)),
        column("updated_at", sa.DateTime(timezone=True)),
    )

    external_mappings_table = table(
        "external_mappings",
        column("id", postgresql.UUID(as_uuid=True)),
        column("issue_id", postgresql.UUID(as_uuid=True)),
        column("source", sa.String),
        column("source_series_id", sa.String),
        column("source_issue_id", sa.String),
        column("created_at", sa.DateTime(timezone=True)),
        column("updated_at", sa.DateTime(timezone=True)),
    )

    now = datetime.now(timezone.utc)

    series_id = uuid.uuid4()
    issue_id = uuid.uuid4()
    variant_a_id = uuid.uuid4()
    variant_b_id = uuid.uuid4()
    variant_ns_id = uuid.uuid4()
    gcd_mapping_id = uuid.uuid4()
    locg_mapping_id = uuid.uuid4()
    ccl_mapping_id = uuid.uuid4()
    aa_mapping_id = uuid.uuid4()
    cpg_mapping_id = uuid.uuid4()
    hip_mapping_id = uuid.uuid4()
    clz_mapping_id = uuid.uuid4()

    try:
        op.bulk_insert(
            series_runs_table,
            [
                {
                    "id": series_id,
                    "title": "X-Men",
                    "start_year": 1991,
                    "publisher": "Marvel Comics",
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )

        op.bulk_insert(
            issues_table,
            [
                {
                    "id": issue_id,
                    "series_run_id": series_id,
                    "issue_number": "-1",
                    "cover_date": datetime(1997, 7, 1),
                    "upc": "75960601772099911",
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )

        op.bulk_insert(
            variants_table,
            [
                {
                    "id": variant_a_id,
                    "issue_id": issue_id,
                    "variant_suffix": "A",
                    "variant_name": "Direct Edition",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": variant_b_id,
                    "issue_id": issue_id,
                    "variant_suffix": "B",
                    "variant_name": "Variant Edition",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": variant_ns_id,
                    "issue_id": issue_id,
                    "variant_suffix": "NS",
                    "variant_name": "Newsstand",
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )

        op.bulk_insert(
            external_mappings_table,
            [
                {
                    "id": gcd_mapping_id,
                    "issue_id": issue_id,
                    "source": "gcd",
                    "source_series_id": "4254",
                    "source_issue_id": "125295",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": locg_mapping_id,
                    "issue_id": issue_id,
                    "source": "locg",
                    "source_series_id": "5118",
                    "source_issue_id": "1169529",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": ccl_mapping_id,
                    "issue_id": issue_id,
                    "source": "ccl",
                    "source_series_id": "x-men-1991",
                    "source_issue_id": "98ab98c9-a87a-4cd2-b49a-ee5232abc0ad",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": aa_mapping_id,
                    "issue_id": issue_id,
                    "source": "aa",
                    "source_series_id": "217254",
                    "source_issue_id": "217255",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": cpg_mapping_id,
                    "issue_id": issue_id,
                    "source": "cpg",
                    "source_series_id": "x-men",
                    "source_issue_id": "phvpiu",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": hip_mapping_id,
                    "issue_id": issue_id,
                    "source": "hip",
                    "source_series_id": "x-men-1991",
                    "source_issue_id": "1-1",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": clz_mapping_id,
                    "issue_id": issue_id,
                    "source": "clz",
                    "source_series_id": "55370",
                    "source_issue_id": "9548415",
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )
    except Exception:
        raise


def downgrade() -> None:
    """Perform database downgrade.

    Delete the seed data by specific identifiers.
    """
    from sqlalchemy.sql import table, column
    from sqlalchemy.dialects import postgresql

    external_mappings_table = table(
        "external_mappings",
        column("issue_id", postgresql.UUID(as_uuid=True)),
    )

    variants_table = table(
        "variants",
        column("issue_id", postgresql.UUID(as_uuid=True)),
    )

    issues_table = table(
        "issues",
        column("issue_number", sa.String),
        column("upc", sa.String),
    )

    series_runs_table = table(
        "series_runs",
        column("title", sa.String),
        column("start_year", sa.Integer),
    )

    issue_id = (
        op.get_bind()
        .execute(
            sa.text("""
            SELECT id FROM issues
            WHERE issue_number = '-1' AND upc = '75960601772099911'
            LIMIT 1
        """)
        )
        .scalar()
    )

    if issue_id:
        op.execute(
            external_mappings_table.delete().where(
                external_mappings_table.c.issue_id == issue_id
            )
        )

        op.execute(variants_table.delete().where(variants_table.c.issue_id == issue_id))

    op.execute(
        issues_table.delete()
        .where(issues_table.c.issue_number == "-1")
        .where(issues_table.c.upc == "75960601772099911")
    )

    op.execute(
        series_runs_table.delete()
        .where(series_runs_table.c.title == "X-Men")
        .where(series_runs_table.c.start_year == 1991)
    )
