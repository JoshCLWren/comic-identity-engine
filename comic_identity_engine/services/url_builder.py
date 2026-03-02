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

from comic_identity_engine.database.repositories import ExternalMappingRepository


logger = structlog.get_logger(__name__)

# Platform URL templates
PLATFORM_TEMPLATES = {
    "gcd": "https://www.comics.org/issue/{source_issue_id}/",
    "locg": "https://leagueofcomicgeeks.com/comic/{source_series_id}/issue-{source_issue_id}",
    "ccl": "https://www.comiccollectorlive.com/issue/{source_series_id}/{source_issue_id}",
    "aa": "https://atomicavenue.com/atomic/item/{source_issue_id}/1/details",
    "cpg": "https://www.comicspriceguide.com/titles/{source_series_id}/-1/{source_issue_id}",
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
        url = template.format(
            source_issue_id=mapping.source_issue_id,
            source_series_id=mapping.source_series_id or "",
        )
        urls[source] = url

    logger.info(
        "URLs built successfully",
        issue_id=str(issue_id),
        num_urls=len([u for u in urls.values() if u]),
    )

    return urls


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
        URL string or None if not found

    Raises:
        RepositoryError: If database query fails

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
    return urls.get(platform)


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
