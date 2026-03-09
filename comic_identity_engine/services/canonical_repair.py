"""Audit and repair tooling for duplicate canonical entities."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from comic_identity_engine.database.models import Issue, SeriesRun


_FALLBACK_CREATED_AT = datetime.max.replace(tzinfo=timezone.utc)


class CanonicalRepairService:
    """Audit and merge duplicate canonical series and issues."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the service with an async session."""
        self.session = session

    async def audit_duplicates(
        self,
        *,
        series_ids: Sequence[uuid.UUID] | None = None,
        issue_ids: Sequence[uuid.UUID] | None = None,
    ) -> dict[str, Any]:
        """Return duplicate canonical groups with merge targets."""
        selected_series_ids = set(series_ids or [])
        selected_issue_ids = set(issue_ids or [])

        series_reports: list[dict[str, Any]] = []
        for title, start_year in await self._list_series_duplicate_keys():
            series_runs = await self._load_series_group(title, start_year)
            if len(series_runs) < 2:
                continue
            if not self._matches_filters(
                series_runs=series_runs,
                selected_series_ids=selected_series_ids,
                selected_issue_ids=selected_issue_ids,
            ):
                continue
            series_reports.append(self._serialize_series_group(series_runs))

        issue_reports: list[dict[str, Any]] = []
        for title, start_year, issue_number in await self._list_issue_duplicate_keys():
            issues = await self._load_issue_group(title, start_year, issue_number)
            if len(issues) < 2:
                continue
            if not self._matches_filters(
                issues=issues,
                selected_series_ids=selected_series_ids,
                selected_issue_ids=selected_issue_ids,
            ):
                continue
            issue_reports.append(self._serialize_issue_group(issues))

        return {
            "series_duplicates": series_reports,
            "issue_duplicates": issue_reports,
            "summary": {
                "series_duplicate_groups": len(series_reports),
                "issue_duplicate_groups": len(issue_reports),
                "duplicate_series_rows": sum(
                    len(group["series_runs"]) for group in series_reports
                ),
                "duplicate_issue_rows": sum(
                    len(group["issues"]) for group in issue_reports
                ),
            },
        }

    async def repair_duplicates(
        self,
        *,
        series_ids: Sequence[uuid.UUID] | None = None,
        issue_ids: Sequence[uuid.UUID] | None = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Repair duplicate canonicals or return a dry-run plan."""
        selected_series_ids = set(series_ids or [])
        selected_issue_ids = set(issue_ids or [])

        selected_series_keys: list[tuple[str, int]] = []
        selected_issue_keys: list[tuple[str, int, str]] = []
        series_reports: list[dict[str, Any]] = []
        issue_reports: list[dict[str, Any]] = []

        for title, start_year, issue_number in await self._list_issue_duplicate_keys():
            issues = await self._load_issue_group(title, start_year, issue_number)
            if len(issues) < 2:
                continue
            if not self._matches_filters(
                issues=issues,
                selected_series_ids=selected_series_ids,
                selected_issue_ids=selected_issue_ids,
            ):
                continue
            selected_issue_keys.append((title, start_year, issue_number))
            issue_reports.append(self._serialize_issue_group(issues))

        for title, start_year in await self._list_series_duplicate_keys():
            series_runs = await self._load_series_group(title, start_year)
            if len(series_runs) < 2:
                continue
            if not self._matches_filters(
                series_runs=series_runs,
                selected_series_ids=selected_series_ids,
                selected_issue_ids=selected_issue_ids,
            ):
                continue
            selected_series_keys.append((title, start_year))
            series_reports.append(self._serialize_series_group(series_runs))

        issue_repairs: list[dict[str, Any]] = []
        series_repairs: list[dict[str, Any]] = []

        if not dry_run:
            for title, start_year, issue_number in selected_issue_keys:
                issue_repairs.append(
                    await self._merge_issue_group(
                        title=title,
                        start_year=start_year,
                        issue_number=issue_number,
                    )
                )

            for title, start_year in selected_series_keys:
                series_repairs.append(
                    await self._merge_series_group(title=title, start_year=start_year)
                )

            await self.session.commit()

        return {
            "dry_run": dry_run,
            "series_duplicates": series_reports,
            "issue_duplicates": issue_reports,
            "series_repairs": series_repairs,
            "issue_repairs": issue_repairs,
            "summary": {
                "series_duplicate_groups": len(series_reports),
                "issue_duplicate_groups": len(issue_reports),
                "series_rows_merged": sum(
                    len(repair["merged_series_run_ids"]) for repair in series_repairs
                ),
                "issue_rows_merged": sum(
                    len(repair["merged_issue_ids"]) for repair in issue_repairs
                ),
                "applied": not dry_run,
            },
        }

    async def _list_series_duplicate_keys(self) -> list[tuple[str, int]]:
        stmt = (
            select(SeriesRun.title, SeriesRun.start_year)
            .group_by(SeriesRun.title, SeriesRun.start_year)
            .having(func.count(SeriesRun.id) > 1)
            .order_by(SeriesRun.title, SeriesRun.start_year)
        )
        result = await self.session.execute(stmt)
        return [(title, start_year) for title, start_year in result.all()]

    async def _list_issue_duplicate_keys(self) -> list[tuple[str, int, str]]:
        stmt = (
            select(SeriesRun.title, SeriesRun.start_year, Issue.issue_number)
            .join(Issue, Issue.series_run_id == SeriesRun.id)
            .group_by(SeriesRun.title, SeriesRun.start_year, Issue.issue_number)
            .having(func.count(Issue.id) > 1)
            .order_by(SeriesRun.title, SeriesRun.start_year, Issue.issue_number)
        )
        result = await self.session.execute(stmt)
        return [
            (title, start_year, issue_number)
            for title, start_year, issue_number in result.all()
        ]

    async def _load_series_group(
        self,
        title: str,
        start_year: int,
    ) -> list[SeriesRun]:
        stmt = (
            select(SeriesRun)
            .where(
                SeriesRun.title == title,
                SeriesRun.start_year == start_year,
            )
            .options(
                selectinload(SeriesRun.issues).selectinload(Issue.external_mappings),
                selectinload(SeriesRun.issues).selectinload(Issue.variants),
            )
            .order_by(SeriesRun.created_at, SeriesRun.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def _load_issue_group(
        self,
        title: str,
        start_year: int,
        issue_number: str,
    ) -> list[Issue]:
        stmt = (
            select(Issue)
            .join(SeriesRun, Issue.series_run_id == SeriesRun.id)
            .where(
                SeriesRun.title == title,
                SeriesRun.start_year == start_year,
                Issue.issue_number == issue_number,
            )
            .options(
                selectinload(Issue.series_run),
                selectinload(Issue.external_mappings),
                selectinload(Issue.variants),
            )
            .order_by(Issue.created_at, Issue.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    def _matches_filters(
        self,
        *,
        series_runs: Sequence[SeriesRun] | None = None,
        issues: Sequence[Issue] | None = None,
        selected_series_ids: set[uuid.UUID],
        selected_issue_ids: set[uuid.UUID],
    ) -> bool:
        if not selected_series_ids and not selected_issue_ids:
            return True

        group_series_ids: set[uuid.UUID] = set()
        group_issue_ids: set[uuid.UUID] = set()

        if series_runs is not None:
            group_series_ids.update(series.id for series in series_runs)
            group_issue_ids.update(
                issue.id for series in series_runs for issue in series.issues
            )

        if issues is not None:
            group_series_ids.update(issue.series_run_id for issue in issues)
            group_issue_ids.update(issue.id for issue in issues)

        if selected_series_ids and group_series_ids.intersection(selected_series_ids):
            return True
        if selected_issue_ids and group_issue_ids.intersection(selected_issue_ids):
            return True
        return False

    def _serialize_series_group(
        self, series_runs: Sequence[SeriesRun]
    ) -> dict[str, Any]:
        ordered = sorted(series_runs, key=self._entity_sort_key)
        winner = ordered[0]
        return {
            "title": winner.title,
            "start_year": winner.start_year,
            "proposed_merge_target_series_id": str(winner.id),
            "series_runs": [
                {
                    "series_run_id": str(series.id),
                    "publisher": series.publisher,
                    "created_at": self._isoformat(series.created_at),
                    "issue_count": len(series.issues),
                    "issue_numbers": sorted(
                        issue.issue_number for issue in series.issues
                    ),
                    "mapping_count": sum(
                        len(issue.external_mappings) for issue in series.issues
                    ),
                    "mapping_sources": sorted(
                        {
                            mapping.source
                            for issue in series.issues
                            for mapping in issue.external_mappings
                        }
                    ),
                }
                for series in ordered
            ],
        }

    def _serialize_issue_group(self, issues: Sequence[Issue]) -> dict[str, Any]:
        ordered = sorted(issues, key=self._entity_sort_key)
        winner = ordered[0]
        return {
            "series_title": winner.series_run.title,
            "series_start_year": winner.series_run.start_year,
            "issue_number": winner.issue_number,
            "proposed_merge_target_issue_id": str(winner.id),
            "issues": [
                {
                    "issue_id": str(issue.id),
                    "series_run_id": str(issue.series_run_id),
                    "cover_date": self._isoformat(issue.cover_date),
                    "upc": issue.upc,
                    "created_at": self._isoformat(issue.created_at),
                    "variant_suffixes": sorted(
                        variant.variant_suffix for variant in issue.variants
                    ),
                    "mappings": [
                        {
                            "source": mapping.source,
                            "source_issue_id": mapping.source_issue_id,
                            "source_series_id": mapping.source_series_id,
                        }
                        for mapping in sorted(
                            issue.external_mappings,
                            key=lambda mapping: (
                                mapping.source,
                                mapping.source_issue_id,
                            ),
                        )
                    ],
                }
                for issue in ordered
            ],
        }

    async def _merge_issue_group(
        self,
        *,
        title: str,
        start_year: int,
        issue_number: str,
    ) -> dict[str, Any]:
        issues = await self._load_issue_group(title, start_year, issue_number)
        if len(issues) < 2:
            return {
                "series_title": title,
                "series_start_year": start_year,
                "issue_number": issue_number,
                "merge_target_issue_id": None,
                "merged_issue_ids": [],
                "upc_conflicts": [],
                "variant_conflicts": [],
            }

        ordered = sorted(issues, key=self._entity_sort_key)
        winner = ordered[0]
        return await self._merge_issue_objects(
            winner=winner,
            losers=ordered[1:],
            series_title=title,
            series_start_year=start_year,
        )

    async def _merge_series_group(
        self,
        *,
        title: str,
        start_year: int,
    ) -> dict[str, Any]:
        series_runs = await self._load_series_group(title, start_year)
        if len(series_runs) < 2:
            return {
                "title": title,
                "start_year": start_year,
                "merge_target_series_id": None,
                "merged_series_run_ids": [],
                "publisher_conflicts": [],
            }

        ordered = sorted(series_runs, key=self._entity_sort_key)
        winner = ordered[0]
        winner_issues_by_number = {issue.issue_number: issue for issue in winner.issues}
        merged_series_ids: list[str] = []
        publisher_conflicts: list[dict[str, Any]] = []

        for loser in ordered[1:]:
            if winner.publisher is None and loser.publisher is not None:
                winner.publisher = loser.publisher
            elif (
                winner.publisher
                and loser.publisher
                and winner.publisher != loser.publisher
            ):
                publisher_conflicts.append(
                    {
                        "winner_series_run_id": str(winner.id),
                        "winner_publisher": winner.publisher,
                        "loser_series_run_id": str(loser.id),
                        "loser_publisher": loser.publisher,
                    }
                )

            for loser_issue in list(loser.issues):
                existing_winner_issue = winner_issues_by_number.get(
                    loser_issue.issue_number
                )
                if existing_winner_issue is not None:
                    await self._merge_issue_objects(
                        winner=existing_winner_issue,
                        losers=[loser_issue],
                        series_title=title,
                        series_start_year=start_year,
                    )
                    continue

                loser_issue.series_run = winner
                winner_issues_by_number[loser_issue.issue_number] = loser_issue

            await self.session.flush()
            await self.session.delete(loser)
            merged_series_ids.append(str(loser.id))

        await self.session.flush()
        return {
            "title": title,
            "start_year": start_year,
            "merge_target_series_id": str(winner.id),
            "merged_series_run_ids": merged_series_ids,
            "publisher_conflicts": publisher_conflicts,
        }

    async def _merge_issue_objects(
        self,
        *,
        winner: Issue,
        losers: Iterable[Issue],
        series_title: str,
        series_start_year: int,
    ) -> dict[str, Any]:
        merged_issue_ids: list[str] = []
        upc_conflicts: list[dict[str, Any]] = []
        variant_conflicts: list[dict[str, Any]] = []
        winner_variants = {
            variant.variant_suffix: variant for variant in winner.variants
        }

        for loser in losers:
            if winner.cover_date is None and loser.cover_date is not None:
                winner.cover_date = loser.cover_date

            if winner.upc is None and loser.upc is not None:
                winner.upc = loser.upc
            elif winner.upc and loser.upc and winner.upc != loser.upc:
                upc_conflicts.append(
                    {
                        "winner_issue_id": str(winner.id),
                        "winner_upc": winner.upc,
                        "loser_issue_id": str(loser.id),
                        "loser_upc": loser.upc,
                    }
                )

            for mapping in list(loser.external_mappings):
                mapping.issue = winner

            for variant in list(loser.variants):
                existing_variant = winner_variants.get(variant.variant_suffix)
                if existing_variant is None:
                    variant.issue = winner
                    winner_variants[variant.variant_suffix] = variant
                    continue

                if existing_variant.variant_name is None and variant.variant_name:
                    existing_variant.variant_name = variant.variant_name
                elif (
                    existing_variant.variant_name
                    and variant.variant_name
                    and existing_variant.variant_name != variant.variant_name
                ):
                    variant_conflicts.append(
                        {
                            "winner_issue_id": str(winner.id),
                            "loser_issue_id": str(loser.id),
                            "variant_suffix": variant.variant_suffix,
                            "winner_variant_name": existing_variant.variant_name,
                            "loser_variant_name": variant.variant_name,
                        }
                    )
                await self.session.delete(variant)

            await self.session.flush()
            await self.session.delete(loser)
            merged_issue_ids.append(str(loser.id))

        await self.session.flush()
        return {
            "series_title": series_title,
            "series_start_year": series_start_year,
            "issue_number": winner.issue_number,
            "merge_target_issue_id": str(winner.id),
            "merged_issue_ids": merged_issue_ids,
            "upc_conflicts": upc_conflicts,
            "variant_conflicts": variant_conflicts,
        }

    def _entity_sort_key(self, entity: SeriesRun | Issue) -> tuple[datetime, str]:
        created_at = entity.created_at or _FALLBACK_CREATED_AT
        return created_at, str(entity.id)

    def _isoformat(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat()
