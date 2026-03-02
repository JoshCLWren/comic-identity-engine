"""URL builder for comic platform URLs.

This module provides URL building for all 7 supported comic platforms
from internal issue UUIDs.

USAGE:
    from comic_identity_engine.services import build_urls

    urls = await build_urls(issue_id, ["gcd", "locg", "ccl"])
    print(urls["gcd"])  # "https://www.comics.org/issue/125295/"
"""

import uuid
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from comic_identity_engine.database.repositories import (
    ExternalMappingRepository,
    IssueRepository,
)


logger = structlog.get_logger(__name__)

# Platform URL templates
PLATFORM_TEMPLATES = {
    "gcd": "https://www.comics.org/issue/{source_issue_id}/",
    "locg": "https://leagueofcomicgeeks.com/comic/{source_series_id}/issue-{source_issue_id}",
    "ccl": "https://www.comiccollectorlive.com/issue/{source_series_id}/{source_issue_id}",
    "aa": "https://atomicavenue.com/atomic/item/{source_issue_id}/1/details",
    "cpg": "https://www.comicspriceguide.com/titles/{source_series_id}/{issue_number}/{source_issue_id}",
    "hip": "https://www.hipcomic.com/price-guide/us/marvel/comic/{source_series_id}/{source_issue_id}/",
    "clz": None,
}


async def build_urls(
    issue_id: uuid.UUID,
    sources: list[str],
    session: AsyncSession,
) -> dict[str, str]:
    """Build platform URLs for an internal issue UUID.

    Args:
        issue_id: Internal canonical issue UUID
        sources: List of platform codes (gcd, locg, ccl, etc.)
        session: Async database session

    Returns:
        Dictionary mapping platform code to URL

    Raises:
        RepositoryError: If database query fails
        ValueError: If required template fields are missing

    Examples:
        >>> urls = await build_urls(issue_id, ["gcd", "locg"], session)
        >>> print(urls["gcd"])
        'https://www.comics.org/issue/125295/'
    """
    if not issue_id:
        raise ValueError("issue_id is required")

    if not sources:
        raise ValueError("sources list cannot be empty")

    logger.info(
        "Building URLs",
        issue_id=str(issue_id),
        sources=sources,
    )

    issue_repo = IssueRepository(session)
    issue = await issue_repo.find_by_id(issue_id)

    if not issue:
        logger.info("Issue not found", issue_id=str(issue_id))
        return {}

    mapping_repo = ExternalMappingRepository(session)
    mappings = await mapping_repo.find_by_issue(issue_id)

    urls = {}
    for source in sources:
        if source not in PLATFORM_TEMPLATES:
            logger.warning("Unsupported platform", platform=source)
            continue

        if PLATFORM_TEMPLATES[source] is None:
            logger.info("Platform does not support URLs", platform=source)
            urls[source] = f"N/A ({source.upper()} is CSV import only)"
            continue

        mapping = next((m for m in mappings if m.source == source), None)
        if not mapping:
            logger.warning(
                "No external mapping found",
                platform=source,
                issue_id=str(issue_id),
            )
            urls[source] = ""
            continue

        template = PLATFORM_TEMPLATES[source]
        try:
            template_fields = _extract_template_fields(template)
            format_kwargs = {
                "source_issue_id": mapping.source_issue_id,
                "source_series_id": mapping.source_series_id or "",
            }

            if "issue_number" in template_fields:
                format_kwargs["issue_number"] = issue.issue_number or "-1"

            _validate_template_fields(template, format_kwargs)
            url = template.format(**format_kwargs)
            urls[source] = url
        except KeyError as e:
            logger.error(
                "Missing required template field",
                platform=source,
                missing_field=str(e),
            )
            urls[source] = ""
            continue

    logger.info(
        "URLs built successfully",
        issue_id=str(issue_id),
        num_urls=len([u for u in urls.values() if u]),
    )

    return urls


def _extract_template_fields(template: str) -> set[str]:
    """Extract field names from a format template.

    Args:
        template: Format string with {field} placeholders

    Returns:
        Set of field names
    """
    import re

    return set(re.findall(r"\{(\w+)\}", template))


def _validate_template_fields(template: str, fields: dict[str, str]) -> None:
    """Validate that all required template fields are present.

    Args:
        template: Format string with {field} placeholders
        fields: Dictionary of field values

    Raises:
        ValueError: If required fields are missing
    """
    required_fields = _extract_template_fields(template)
    missing_fields = required_fields - set(fields.keys())
    if missing_fields:
        raise ValueError(
            f"Missing required template fields: {', '.join(sorted(missing_fields))}"
        )


async def build_url_for_platform(
    issue_id: uuid.UUID,
    platform: str,
    session: AsyncSession,
) -> Optional[str]:
    """Build a single platform URL for an internal issue UUID.

    Args:
        issue_id: Internal canonical issue UUID
        platform: Platform code (gcd, locg, ccl, etc.)
        session: Async database session

    Returns:
        URL string if found, None if not found or mapping doesn't exist

    Raises:
        RepositoryError: If database query fails
        ValueError: If platform is invalid

    Examples:
        >>> url = await build_url_for_platform(issue_id, "gcd", session)
        >>> print(url)
        'https://www.comics.org/issue/125295/'
    """
    if not platform:
        raise ValueError("platform is required")

    if platform not in PLATFORM_TEMPLATES:
        raise ValueError(f"Unsupported platform: {platform}")

    urls = await build_urls(issue_id, [platform], session)
    result = urls.get(platform)
    return result if result else None


async def get_all_platform_urls(
    issue_id: uuid.UUID,
    session: AsyncSession,
) -> dict[str, str]:
    """Get URLs for all supported platforms.

    Args:
        issue_id: Internal canonical issue UUID
        session: Async database session

    Returns:
        Dictionary mapping platform code to URL

    Raises:
        RepositoryError: If database query fails

    Examples:
        >>> urls = await get_all_platform_urls(issue_id, session)
        >>> print(urls["gcd"])
        'https://www.comics.org/issue/125295/'
    """
    all_platforms = list(PLATFORM_TEMPLATES.keys())
    return await build_urls(issue_id, all_platforms, session)
