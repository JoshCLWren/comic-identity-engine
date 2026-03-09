"""Administrative CLI commands for canonical audit and repair workflows."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Sequence

import click

from comic_identity_engine.database.connection import AsyncSessionLocal
from comic_identity_engine.services.canonical_repair import CanonicalRepairService


def _parse_uuid_values(values: Sequence[str], option_name: str) -> list[uuid.UUID]:
    parsed: list[uuid.UUID] = []
    for value in values:
        try:
            parsed.append(uuid.UUID(value))
        except ValueError as exc:
            raise click.BadParameter(
                f"{value!r} is not a valid UUID",
                param_hint=option_name,
            ) from exc
    return parsed


def _print_summary(report: dict[str, object]) -> None:
    summary = dict(report.get("summary", {}) or {})
    click.echo(f"Series duplicate groups: {summary.get('series_duplicate_groups', 0)}")
    click.echo(f"Issue duplicate groups: {summary.get('issue_duplicate_groups', 0)}")


async def _run_audit(
    *,
    series_ids: list[uuid.UUID],
    issue_ids: list[uuid.UUID],
) -> dict[str, object]:
    async with AsyncSessionLocal() as session:
        service = CanonicalRepairService(session)
        return await service.audit_duplicates(
            series_ids=series_ids,
            issue_ids=issue_ids,
        )


async def _run_repair(
    *,
    series_ids: list[uuid.UUID],
    issue_ids: list[uuid.UUID],
    apply: bool,
) -> dict[str, object]:
    async with AsyncSessionLocal() as session:
        service = CanonicalRepairService(session)
        return await service.repair_duplicates(
            series_ids=series_ids,
            issue_ids=issue_ids,
            dry_run=not apply,
        )


@click.group(name="cie-admin")
def cli_admin() -> None:
    """Administrative commands for duplicate canonical maintenance."""


@cli_admin.command("audit-duplicates")
@click.option(
    "--series-id",
    "series_ids",
    multiple=True,
    help="Limit audit output to duplicate groups containing this series UUID.",
)
@click.option(
    "--issue-id",
    "issue_ids",
    multiple=True,
    help="Limit audit output to duplicate groups containing this issue UUID.",
)
@click.option(
    "--json-output",
    "json_output",
    is_flag=True,
    help="Render the audit report as JSON.",
)
def audit_duplicates_command(
    series_ids: tuple[str, ...],
    issue_ids: tuple[str, ...],
    json_output: bool,
) -> None:
    """Audit duplicate canonical series and issues."""
    report = asyncio.run(
        _run_audit(
            series_ids=_parse_uuid_values(series_ids, "--series-id"),
            issue_ids=_parse_uuid_values(issue_ids, "--issue-id"),
        )
    )

    if json_output:
        click.echo(json.dumps(report, indent=2))
        return

    _print_summary(report)
    for group in report.get("series_duplicates", []):
        click.echo(
            f"{group['title']} ({group['start_year']}): "
            f"merge target {group['proposed_merge_target_series_id']}"
        )
    for group in report.get("issue_duplicates", []):
        click.echo(
            f"{group['series_title']} ({group['series_start_year']}) "
            f"#{group['issue_number']}: "
            f"merge target {group['proposed_merge_target_issue_id']}"
        )


@cli_admin.command("repair-duplicates")
@click.option(
    "--series-id",
    "series_ids",
    multiple=True,
    help="Limit repair to duplicate groups containing this series UUID.",
)
@click.option(
    "--issue-id",
    "issue_ids",
    multiple=True,
    help="Limit repair to duplicate groups containing this issue UUID.",
)
@click.option(
    "--apply",
    is_flag=True,
    help="Apply the repair instead of returning a dry-run plan.",
)
@click.option(
    "--json-output",
    "json_output",
    is_flag=True,
    help="Render the repair report as JSON.",
)
def repair_duplicates_command(
    series_ids: tuple[str, ...],
    issue_ids: tuple[str, ...],
    apply: bool,
    json_output: bool,
) -> None:
    """Merge duplicate canonical series and issues."""
    report = asyncio.run(
        _run_repair(
            series_ids=_parse_uuid_values(series_ids, "--series-id"),
            issue_ids=_parse_uuid_values(issue_ids, "--issue-id"),
            apply=apply,
        )
    )

    if json_output:
        click.echo(json.dumps(report, indent=2))
        return

    mode = "applied" if apply else "dry run"
    click.echo(f"Repair mode: {mode}")
    _print_summary(report)
    if apply:
        click.echo(
            "Merged series rows: "
            f"{sum(len(item['merged_series_run_ids']) for item in report.get('series_repairs', []))}"
        )
        click.echo(
            "Merged issue rows: "
            f"{sum(len(item['merged_issue_ids']) for item in report.get('issue_repairs', []))}"
        )
