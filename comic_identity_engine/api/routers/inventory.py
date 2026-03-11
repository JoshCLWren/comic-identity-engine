"""Inventory viewing router for Comic Identity Engine.

Provides endpoints for viewing current database state - issues, mappings, and coverage statistics. This is the dynamic frontend data source.
"""

from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select, distinct
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from comic_identity_engine.database.connection import get_db
from comic_identity_engine.database.models import Issue, SeriesRun, ExternalMapping

router = APIRouter(prefix="/inventory", tags=["Inventory"])


ALL_PLATFORMS = ["gcd", "locg", "ccl", "aa", "cpg", "hip", "clz"]


class IssueMappingStatus(BaseModel):
    """Mapping status for a single platform."""

    platform: str
    source_issue_id: str
    source_series_id: Optional[str] = None


class IssueListItem(BaseModel):
    """Issue for list view."""

    id: UUID
    series_title: str
    issue_number: str
    start_year: int
    publisher: Optional[str]
    cover_date: Optional[str]
    upc: Optional[str]
    mappings: list[IssueMappingStatus]
    platforms_found: int
    platforms_total: int


class IssueListResponse(BaseModel):
    """Paginated list of issues."""

    issues: list[IssueListItem]
    total: int
    offset: int
    limit: int


class MappingCoverage(BaseModel):
    """Coverage stats for a platform."""

    platform: str
    mapped: int
    total: int
    percentage: float


class InventoryStatsResponse(BaseModel):
    """Overall inventory statistics."""

    total_issues: int
    total_series: int
    total_mappings: int
    coverage_by_platform: list[MappingCoverage]


@router.get("/issues", response_model=IssueListResponse)
async def list_issues(
    series_title: Optional[str] = Query(
        None, description="Filter by series title (partial match)"
    ),
    issue_number: Optional[str] = Query(None, description="Filter by issue number"),
    publisher: Optional[str] = Query(None, description="Filter by publisher"),
    platform: Optional[str] = Query(
        None, description="Filter to issues with this platform mapped"
    ),
    has_all_platforms: Optional[bool] = Query(
        None, description="Filter to issues with all 7 platforms mapped"
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> IssueListResponse:
    """List issues with their current mapping status.

    This queries the live database, not static operation snapshots.
    """
    query = (
        select(Issue)
        .options(
            selectinload(Issue.series_run),
            selectinload(Issue.external_mappings),
        )
        .join(SeriesRun)
        .order_by(SeriesRun.title, Issue.issue_number)
    )

    count_query = select(func.count(Issue.id)).select_from(Issue).join(SeriesRun)

    if series_title:
        query = query.where(SeriesRun.title.ilike(f"%{series_title}%"))
        count_query = count_query.where(SeriesRun.title.ilike(f"%{series_title}%"))

    if issue_number:
        query = query.where(Issue.issue_number == issue_number)
        count_query = count_query.where(Issue.issue_number == issue_number)

    if publisher:
        query = query.where(SeriesRun.publisher.ilike(f"%{publisher}%"))
        count_query = count_query.where(SeriesRun.publisher.ilike(f"%{publisher}%"))

    if platform:
        subquery = (
            select(ExternalMapping.issue_id)
            .where(ExternalMapping.source == platform)
            .distinct()
        )
        query = query.where(Issue.id.in_(subquery))
        count_query = count_query.where(Issue.id.in_(subquery))

    if has_all_platforms:
        subquery = (
            select(ExternalMapping.issue_id)
            .where(ExternalMapping.source.in_(ALL_PLATFORMS))
            .group_by(ExternalMapping.issue_id)
            .having(func.count(distinct(ExternalMapping.source)) == len(ALL_PLATFORMS))
        )
        query = query.where(Issue.id.in_(subquery))
        count_query = count_query.where(Issue.id.in_(subquery))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    issues = result.scalars().all()

    issue_list = []
    for issue in issues:
        mappings = [
            IssueMappingStatus(
                platform=m.source,
                source_issue_id=m.source_issue_id,
                source_series_id=m.source_series_id,
            )
            for m in issue.external_mappings
        ]

        issue_list.append(
            IssueListItem(
                id=issue.id,
                series_title=issue.series_run.title,
                issue_number=issue.issue_number,
                start_year=issue.series_run.start_year,
                publisher=issue.series_run.publisher,
                cover_date=issue.cover_date.isoformat() if issue.cover_date else None,
                upc=issue.upc,
                mappings=mappings,
                platforms_found=len({m.source for m in issue.external_mappings}),
                platforms_total=len(ALL_PLATFORMS),
            )
        )

    return IssueListResponse(
        issues=issue_list,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/issues/{issue_id}", response_model=IssueListItem)
async def get_issue_detail(
    issue_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> IssueListItem:
    """Get detailed view of a single issue with all mappings."""
    query = (
        select(Issue)
        .where(Issue.id == issue_id)
        .options(
            selectinload(Issue.series_run),
            selectinload(Issue.external_mappings),
        )
    )

    result = await db.execute(query)
    issue = result.scalar_one_or_none()

    if not issue:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Issue not found")

    mappings = [
        IssueMappingStatus(
            platform=m.source,
            source_issue_id=m.source_issue_id,
            source_series_id=m.source_series_id,
        )
        for m in issue.external_mappings
    ]

    return IssueListItem(
        id=issue.id,
        series_title=issue.series_run.title,
        issue_number=issue.issue_number,
        start_year=issue.series_run.start_year,
        publisher=issue.series_run.publisher,
        cover_date=issue.cover_date.isoformat() if issue.cover_date else None,
        upc=issue.upc,
        mappings=mappings,
        platforms_found=len({m.source for m in issue.external_mappings}),
        platforms_total=len(ALL_PLATFORMS),
    )


@router.get("/stats", response_model=InventoryStatsResponse)
async def get_inventory_stats(
    db: AsyncSession = Depends(get_db),
) -> InventoryStatsResponse:
    """Get overall inventory statistics and mapping coverage."""
    total_issues_result = await db.execute(select(func.count(Issue.id)))
    total_issues = total_issues_result.scalar() or 0

    total_series_result = await db.execute(select(func.count(SeriesRun.id)))
    total_series = total_series_result.scalar() or 0

    total_mappings_result = await db.execute(select(func.count(ExternalMapping.id)))
    total_mappings = total_mappings_result.scalar() or 0

    coverage_by_platform = []
    for platform in ALL_PLATFORMS:
        mapped_result = await db.execute(
            select(func.count(distinct(ExternalMapping.issue_id))).where(
                ExternalMapping.source == platform
            )
        )
        mapped = mapped_result.scalar() or 0

        percentage = (mapped / total_issues * 100) if total_issues > 0 else 0.0

        coverage_by_platform.append(
            MappingCoverage(
                platform=platform,
                mapped=mapped,
                total=total_issues,
                percentage=round(percentage, 1),
            )
        )

    return InventoryStatsResponse(
        total_issues=total_issues,
        total_series=total_series,
        total_mappings=total_mappings,
        coverage_by_platform=coverage_by_platform,
    )


@router.get("/search", response_model=IssueListResponse)
async def search_inventory(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> IssueListResponse:
    """Full-text search across series titles, issue numbers, and platform IDs."""
    query = (
        select(Issue)
        .options(
            selectinload(Issue.series_run),
            selectinload(Issue.external_mappings),
        )
        .join(SeriesRun)
        .where(
            (SeriesRun.title.ilike(f"%{q}%"))
            | (Issue.issue_number == q)
            | (Issue.upc == q)
            | (
                Issue.id.in_(
                    select(ExternalMapping.issue_id).where(
                        ExternalMapping.source_issue_id.ilike(f"%{q}%")
                    )
                )
            )
        )
        .order_by(SeriesRun.title, Issue.issue_number)
        .limit(limit)
    )

    result = await db.execute(query)
    issues = result.scalars().all()

    issue_list = []
    for issue in issues:
        mappings = [
            IssueMappingStatus(
                platform=m.source,
                source_issue_id=m.source_issue_id,
                source_series_id=m.source_series_id,
            )
            for m in issue.external_mappings
        ]

        issue_list.append(
            IssueListItem(
                id=issue.id,
                series_title=issue.series_run.title,
                issue_number=issue.issue_number,
                start_year=issue.series_run.start_year,
                publisher=issue.series_run.publisher,
                cover_date=issue.cover_date.isoformat() if issue.cover_date else None,
                upc=issue.upc,
                mappings=mappings,
                platforms_found=len({m.source for m in issue.external_mappings}),
                platforms_total=len(ALL_PLATFORMS),
            )
        )

    return IssueListResponse(
        issues=issue_list,
        total=len(issue_list),
        offset=0,
        limit=limit,
    )
