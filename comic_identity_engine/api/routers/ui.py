"""UI router for inventory views.

Provides HTML responses for HTMX-powered frontend views.
"""

from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select, distinct
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from jinja2 import Environment, FileSystemLoader, select_autoescape

from comic_identity_engine.database.connection import get_db
from comic_identity_engine.database.models import (
    Issue,
    SeriesRun,
    ExternalMapping,
    MappingCorrection,
)

router = APIRouter(prefix="/ui", tags=["UI"])

ALL_PLATFORMS = ["gcd", "locg", "ccl", "aa", "cpg", "hip", "clz"]

PLATFORM_URLS = {
    "gcd": "https://www.comics.org/issue/{id}/",
    "locg": "https://leagueofcomicgeeks.com/comic/{id}",
    "ccl": "https://www.comiccollectorlive.com/Issues/{id}",
    "aa": "https://atomicavenue.com/Comic/{id}",
    "cpg": "https://www.comicspriceguide.com/comic/{id}",
    "hip": "https://hipcomic.com/listing/{id}",
    "clz": "https://www.collectorz.com/comic/{id}",
}

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_template(name: str, **context) -> str:
    template = jinja_env.get_template(name)
    return template.render(**context)


@router.get("/inventory", response_class=HTMLResponse)
async def inventory_page(request: Request):
    return HTMLResponse(
        render_template("inventory.html", request=request, platforms=ALL_PLATFORMS)
    )


@router.get("/partials/stats", response_class=HTMLResponse)
async def stats_partial(db: AsyncSession = Depends(get_db)):
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
            {
                "platform": platform,
                "mapped": mapped,
                "total": total_issues,
                "percentage": round(percentage, 1),
            }
        )

    stats = {
        "total_issues": total_issues,
        "total_series": total_series,
        "total_mappings": total_mappings,
        "coverage_by_platform": coverage_by_platform,
    }

    return HTMLResponse(
        render_template(
            "components/stats_cards.html", stats=stats, platforms=ALL_PLATFORMS
        )
    )


@router.get("/partials/issues", response_class=HTMLResponse)
async def issues_partial(
    series_title: Optional[str] = Query(None),
    issue_number: Optional[str] = Query(None),
    publisher: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    has_all_platforms: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Issue)
        .options(
            selectinload(Issue.series_run),
            selectinload(Issue.external_mappings),
        )
        .join(SeriesRun)
        .order_by(SeriesRun.title, Issue.issue_number)
    )

    if series_title:
        query = query.where(SeriesRun.title.ilike(f"%{series_title}%"))

    if issue_number:
        query = query.where(Issue.issue_number == issue_number)

    if publisher:
        query = query.where(SeriesRun.publisher.ilike(f"%{publisher}%"))

    if platform:
        subquery = (
            select(ExternalMapping.issue_id)
            .where(ExternalMapping.source == platform)
            .distinct()
        )
        query = query.where(Issue.id.in_(subquery))

    if has_all_platforms:
        subquery = (
            select(ExternalMapping.issue_id)
            .where(ExternalMapping.source.in_(ALL_PLATFORMS))
            .group_by(ExternalMapping.issue_id)
            .having(func.count(distinct(ExternalMapping.source)) == len(ALL_PLATFORMS))
        )
        query = query.where(Issue.id.in_(subquery))

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    issues = result.scalars().all()

    rows_html = []
    for issue in issues:
        mapped_platforms = {m.source for m in issue.external_mappings}
        rows_html.append(
            f'<tr class="issue-row clickable" data-issue-id="{issue.id}">'
            f'<td class="col-series">{issue.series_run.title}</td>'
            f'<td class="col-issue_number">{issue.issue_number}</td>'
            f'<td class="col-year">{issue.series_run.start_year}</td>'
            f'<td class="col-publisher col-hidden">{issue.series_run.publisher or "-"}</td>'
            f'<td class="col-cover_date col-hidden">{issue.cover_date.isoformat() if issue.cover_date else "-"}</td>'
            f'<td class="col-platforms">'
            f'<div class="platform-badges">'
        )

        for plat in ALL_PLATFORMS:
            if plat in mapped_platforms:
                mapping = next(
                    (m for m in issue.external_mappings if m.source == plat), None
                )
                badge_class = (
                    "badge-inaccurate"
                    if mapping and not mapping.is_accurate
                    else "badge-mapped"
                )
                icon = "?" if mapping and not mapping.is_accurate else "✓"
                rows_html.append(
                    f'<span class="badge {badge_class}" title="{plat}: {mapping.source_issue_id if mapping else ""}">'
                    f"{plat.upper()} {icon}</span>"
                )
            else:
                rows_html.append(
                    f'<span class="badge badge-unmapped" title="{plat}: Not mapped">'
                    f"{plat.upper()} ✗</span>"
                )

        rows_html.append("</div></td></tr>")

    return HTMLResponse("".join(rows_html))


@router.get("/partials/search", response_class=HTMLResponse)
async def search_partial(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
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

    rows_html = []
    for issue in issues:
        mapped_platforms = {m.source for m in issue.external_mappings}
        rows_html.append(
            f'<tr class="issue-row clickable" data-issue-id="{issue.id}">'
            f'<td class="col-series">{issue.series_run.title}</td>'
            f'<td class="col-issue_number">{issue.issue_number}</td>'
            f'<td class="col-year">{issue.series_run.start_year}</td>'
            f'<td class="col-publisher col-hidden">{issue.series_run.publisher or "-"}</td>'
            f'<td class="col-cover_date col-hidden">{issue.cover_date.isoformat() if issue.cover_date else "-"}</td>'
            f'<td class="col-platforms">'
            f'<div class="platform-badges">'
        )

        for plat in ALL_PLATFORMS:
            if plat in mapped_platforms:
                mapping = next(
                    (m for m in issue.external_mappings if m.source == plat), None
                )
                badge_class = (
                    "badge-inaccurate"
                    if mapping and not mapping.is_accurate
                    else "badge-mapped"
                )
                icon = "?" if mapping and not mapping.is_accurate else "✓"
                rows_html.append(
                    f'<span class="badge {badge_class}" title="{plat}: {mapping.source_issue_id if mapping else ""}">'
                    f"{plat.upper()} {icon}</span>"
                )
            else:
                rows_html.append(
                    f'<span class="badge badge-unmapped" title="{plat}: Not mapped">'
                    f"{plat.upper()} ✗</span>"
                )

        rows_html.append("</div></td></tr>")

    return HTMLResponse("".join(rows_html))


@router.get("/issues/{issue_id}", response_class=HTMLResponse)
async def issue_detail_page(
    issue_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
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
        return HTMLResponse("<div class='error'>Issue not found</div>", status_code=404)

    mapping_dict = {m.source: m for m in issue.external_mappings}

    return HTMLResponse(
        render_template(
            "issue_detail.html",
            request=request,
            issue=issue,
            platforms=ALL_PLATFORMS,
            mapping_dict=mapping_dict,
            platform_urls=PLATFORM_URLS,
        )
    )


@router.get("/partials/issue-detail/{issue_id}", response_class=HTMLResponse)
async def issue_detail_partial(
    issue_id: UUID,
    db: AsyncSession = Depends(get_db),
):
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
        return HTMLResponse("<div class='error'>Issue not found</div>", status_code=404)

    mapping_dict = {m.source: m for m in issue.external_mappings}

    return HTMLResponse(
        render_template(
            "components/issue_detail_content.html",
            issue=issue,
            platforms=ALL_PLATFORMS,
            mapping_dict=mapping_dict,
            platform_urls=PLATFORM_URLS,
        )
    )


@router.get("/partials/issue-row/{issue_id}", response_class=HTMLResponse)
async def issue_row_partial(
    issue_id: UUID,
    db: AsyncSession = Depends(get_db),
):
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
        return HTMLResponse("", status_code=404)

    mapped_platforms = {m.source for m in issue.external_mappings}

    html = f'<tr class="issue-row clickable" data-issue-id="{issue.id}">'
    html += f'<td class="col-series">{issue.series_run.title}</td>'
    html += f'<td class="col-issue_number">{issue.issue_number}</td>'
    html += f'<td class="col-year">{issue.series_run.start_year}</td>'
    html += (
        f'<td class="col-publisher col-hidden">{issue.series_run.publisher or "-"}</td>'
    )
    html += f'<td class="col-cover_date col-hidden">{issue.cover_date.isoformat() if issue.cover_date else "-"}</td>'
    html += '<td class="col-platforms"><div class="platform-badges">'

    for plat in ALL_PLATFORMS:
        if plat in mapped_platforms:
            mapping = next(
                (m for m in issue.external_mappings if m.source == plat), None
            )
            badge_class = (
                "badge-inaccurate"
                if mapping and not mapping.is_accurate
                else "badge-mapped"
            )
            icon = "?" if mapping and not mapping.is_accurate else "✓"
            html += f'<span class="badge {badge_class}" title="{plat}: {mapping.source_issue_id if mapping else ""}">'
            html += f"{plat.upper()} {icon}</span>"
        else:
            html += f'<span class="badge badge-unmapped" title="{plat}: Not mapped">'
            html += f"{plat.upper()} ✗</span>"

    html += "</div></td></tr>"
    return HTMLResponse(html)
