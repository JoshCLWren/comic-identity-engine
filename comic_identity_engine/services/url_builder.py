"""URL builder placeholder.

This module intentionally does not reconstruct platform URLs from stored IDs.

The implementation plan requires authoritative external URLs to be stored on
external mappings at write time. The current schema does not have a URL column,
so generating URLs here would repeat the exact inference bug that polluted the
database with malformed and incorrect links.

What should be done instead:
- add `source_url` and `is_canonical` to external mappings
- persist the exact discovered URL when a mapping is created
- use stored URLs here as the primary source of truth
- only use template-based reconstruction as a legacy fallback after migration
"""

import uuid
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession


logger = structlog.get_logger(__name__)

SUPPORTED_PLATFORMS = {"gcd", "locg", "ccl", "aa", "cpg", "hip", "clz"}


async def build_urls(
    issue_id: uuid.UUID,
    sources: list[str],
    session: AsyncSession,
) -> dict[str, str]:
    """Return no generated URLs until authoritative source URLs are persisted.

    This is deliberately conservative. Returning an empty mapping is safer than
    reconstructing platform URLs from incomplete IDs and surfacing incorrect
    links to users.
    """
    del session

    if not issue_id:
        raise ValueError("issue_id is required")

    if not sources:
        raise ValueError("sources list cannot be empty")

    urls: dict[str, str] = {}
    for source in sources:
        if source not in SUPPORTED_PLATFORMS:
            logger.warning("Unsupported platform", platform=source)
            continue

        if source == "clz":
            # TODO: once authoritative external URLs are persisted, CLZ should
            # continue returning a sentinel because it is CSV-only and has no URL.
            urls[source] = "N/A (CLZ is CSV import only)"
            continue

        # TODO: after the schema migration, load and return the stored
        # authoritative URL for this issue/platform mapping.
        urls[source] = ""

    logger.warning(
        "URL generation disabled until external mappings store authoritative source URLs",
        issue_id=str(issue_id),
        sources=sources,
    )
    return urls


async def build_url_for_platform(
    issue_id: uuid.UUID,
    platform: str,
    session: AsyncSession,
) -> Optional[str]:
    """Return None until authoritative source URLs are persisted."""
    if not platform:
        raise ValueError("platform is required")

    if platform not in SUPPORTED_PLATFORMS:
        raise ValueError(f"Unsupported platform: {platform}")

    urls = await build_urls(issue_id, [platform], session)
    result = urls.get(platform)
    return result if result else None


async def get_all_platform_urls(
    issue_id: uuid.UUID,
    session: AsyncSession,
) -> dict[str, str]:
    """Return per-platform placeholders until URL storage is fixed."""
    return await build_urls(issue_id, sorted(SUPPORTED_PLATFORMS), session)
