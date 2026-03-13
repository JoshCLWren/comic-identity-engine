"""Series cache service for Redis-backed URL and entity caching.

This module provides caching for series lookups and cross-platform URL mappings
to reduce database load and improve resolution performance.

USAGE:
    from comic_identity_engine.services.series_cache import SeriesCacheService

    cache = SeriesCacheService()

    # Cache series lookup
    await cache.set_series("X-Men", 1991, series_run_id)
    series_id = await cache.get_series("X-Men", 1991)

    # Cache issue URLs for all platforms
    await cache.set_issue_urls(issue_id, {"gcd": "https://...", "locg": "https://..."})
    urls = await cache.get_issue_urls(issue_id)

CACHE KEYS:
    - Series: "series:{normalized_title}:{start_year}"
    - Issue URLs: "issue_urls:{issue_id}"
    - Series URLs: "series_urls:{series_run_id}"

TTL:
    - Series lookups: 24 hours (86400 seconds)
    - Issue URL mappings: 7 days (604800 seconds)
    - Series URL mappings: 7 days (604800 seconds)
"""

import re
import uuid
from typing import Dict, Optional

import structlog

from comic_identity_engine.core.cache.redis_singleton import redis_cache

logger = structlog.get_logger(__name__)

# Default TTL values for different cache types
SERIES_CACHE_TTL = 86400  # 24 hours
ISSUE_URLS_CACHE_TTL = 604800  # 7 days
SERIES_URLS_CACHE_TTL = 604800  # 7 days

# Key prefixes for different cache types
SERIES_KEY_PREFIX = "series"
ISSUE_URLS_KEY_PREFIX = "issue_urls"
SERIES_URLS_KEY_PREFIX = "series_urls"


class SeriesCacheService:
    """Redis-backed cache for series lookups and URL mappings.

    This service provides caching for:
    - SeriesRun entity lookups by title and start year
    - Cross-platform issue URL mappings
    - Cross-platform series URL mappings

    All cache operations are async and include error handling for Redis failures.
    Cache misses return None gracefully rather than raising exceptions.
    """

    def __init__(self) -> None:
        """Initialize the series cache service."""
        self._redis = redis_cache

    def _normalize_cache_key(self, value: Optional[str]) -> str:
        """Normalize a string value for use as a cache key component.

        Normalization includes:
        - Converting to lowercase
        - Removing extra whitespace
        - Removing special characters that could cause key collisions
        - Replacing spaces with underscores
        - Trimming to reasonable length

        Args:
            value: String value to normalize, or None/empty string

        Returns:
            Normalized string safe for use in cache keys, or "null" if input is None/empty

        Examples:
            >>> _normalize_cache_key("X-Men")
            "x-men"
            >>> _normalize_cache_key("  The   Amazing  Spider-Man  ")
            "the_amazing_spider-man"
            >>> _normalize_cache_key(None)
            "null"
        """
        if not value or not isinstance(value, str):
            return "null"

        normalized = value.strip().lower()
        normalized = re.sub(r"\s+", "_", normalized)
        normalized = re.sub(r"[^\w\-]", "", normalized)

        if not normalized:
            return "null"

        return normalized

    def _build_series_key(self, title: str, start_year: int) -> str:
        """Build a Redis cache key for series lookup.

        Args:
            title: Series title
            start_year: Series start year

        Returns:
            Redis cache key string

        Examples:
            >>> _build_series_key("X-Men", 1991)
            "series:x-men:1991"
        """
        normalized_title = self._normalize_cache_key(title)
        return f"{SERIES_KEY_PREFIX}:{normalized_title}:{start_year}"

    def _build_issue_urls_key(self, issue_id: uuid.UUID) -> str:
        """Build a Redis cache key for issue URL mappings.

        Args:
            issue_id: Canonical issue UUID

        Returns:
            Redis cache key string

        Examples:
            >>> _build_issue_urls_key(uuid.UUID("12345678-1234-5678-1234-567812345678"))
            "issue_urls:12345678-1234-5678-1234-567812345678"
        """
        return f"{ISSUE_URLS_KEY_PREFIX}:{issue_id}"

    def _build_series_urls_key(self, series_run_id: uuid.UUID) -> str:
        """Build a Redis cache key for series URL mappings.

        Args:
            series_run_id: Canonical series run UUID

        Returns:
            Redis cache key string

        Examples:
            >>> _build_series_urls_key(uuid.UUID("12345678-1234-5678-1234-567812345678"))
            "series_urls:12345678-1234-5678-1234-567812345678"
        """
        return f"{SERIES_URLS_KEY_PREFIX}:{series_run_id}"

    async def get_series(self, title: str, start_year: int) -> Optional[uuid.UUID]:
        """Get cached series_run_id by title and start year.

        Args:
            title: Series title
            start_year: Series start year

        Returns:
            Cached series_run_id as UUID, or None if not found in cache

        Raises:
            RuntimeError: Only if Redis connection fails critically
        """
        if not title or not isinstance(title, str):
            logger.debug("Invalid title for series cache lookup", title=title)
            return None

        if not isinstance(start_year, int) or start_year < 1800 or start_year > 2100:
            logger.debug(
                "Invalid start_year for series cache lookup", start_year=start_year
            )
            return None

        key = self._build_series_key(title, start_year)

        try:
            result = await self._redis.get(key)
            if result is None:
                logger.debug(
                    "Series cache miss",
                    title=title,
                    start_year=start_year,
                    cache_key=key,
                )
                return None

            series_run_id = uuid.UUID(result) if isinstance(result, str) else result
            logger.debug(
                "Series cache hit",
                title=title,
                start_year=start_year,
                series_run_id=str(series_run_id),
            )
            return series_run_id

        except RuntimeError as e:
            logger.warning(
                "Redis connection failed during series cache lookup",
                title=title,
                start_year=start_year,
                error=str(e),
            )
            return None
        except (ValueError, AttributeError) as e:
            logger.warning(
                "Invalid cached series ID format",
                title=title,
                start_year=start_year,
                cache_key=key,
                cached_value=type(e).__name__,
                error=str(e),
            )
            return None

    async def set_series(
        self,
        title: str,
        start_year: int,
        series_run_id: uuid.UUID,
        ttl: Optional[int] = None,
    ) -> bool:
        """Cache series_run_id by title and start year.

        Args:
            title: Series title
            start_year: Series start year
            series_run_id: Canonical series run UUID to cache
            ttl: Optional TTL in seconds (defaults to SERIES_CACHE_TTL)

        Returns:
            True if cached successfully, False otherwise

        Raises:
            RuntimeError: Only if Redis connection fails critically
        """
        if not title or not isinstance(title, str):
            logger.debug("Invalid title for series cache set", title=title)
            return False

        if not isinstance(start_year, int) or start_year < 1800 or start_year > 2100:
            logger.debug(
                "Invalid start_year for series cache set", start_year=start_year
            )
            return False

        if not isinstance(series_run_id, uuid.UUID):
            logger.debug(
                "Invalid series_run_id for series cache set",
                series_run_id=series_run_id,
            )
            return False

        key = self._build_series_key(title, start_year)
        cache_ttl = ttl if ttl is not None else SERIES_CACHE_TTL

        try:
            await self._redis.set(key, str(series_run_id), ttl=cache_ttl)
            logger.debug(
                "Cached series lookup",
                title=title,
                start_year=start_year,
                series_run_id=str(series_run_id),
                ttl=cache_ttl,
                cache_key=key,
            )
            return True

        except RuntimeError as e:
            logger.warning(
                "Redis connection failed during series cache set",
                title=title,
                start_year=start_year,
                series_run_id=str(series_run_id),
                error=str(e),
            )
            return False

    async def delete_series(self, title: str, start_year: int) -> bool:
        """Delete cached series_run_id by title and start year.

        Args:
            title: Series title
            start_year: Series start year

        Returns:
            True if deleted successfully (or key didn't exist), False on Redis error

        Raises:
            RuntimeError: Only if Redis connection fails critically
        """
        if not title or not isinstance(title, str):
            return False

        if not isinstance(start_year, int):
            return False

        key = self._build_series_key(title, start_year)

        try:
            await self._redis.delete(key)
            logger.debug(
                "Deleted series cache entry",
                title=title,
                start_year=start_year,
                cache_key=key,
            )
            return True

        except RuntimeError as e:
            logger.warning(
                "Redis connection failed during series cache delete",
                title=title,
                start_year=start_year,
                error=str(e),
            )
            return False

    async def get_issue_urls(self, issue_id: uuid.UUID) -> Optional[Dict[str, str]]:
        """Get cached platform URL mappings for an issue.

        Args:
            issue_id: Canonical issue UUID

        Returns:
            Dictionary mapping platform codes to URLs, or None if not cached

        Examples:
            >>> await get_issue_urls(issue_id)
            {"gcd": "https://www.comics.org/issue/125295/", "locg": "https://..."}
        """
        if not isinstance(issue_id, uuid.UUID):
            logger.debug(
                "Invalid issue_id for issue URLs cache lookup", issue_id=issue_id
            )
            return None

        key = self._build_issue_urls_key(issue_id)

        try:
            result = await self._redis.get(key)
            if result is None:
                logger.debug(
                    "Issue URLs cache miss",
                    issue_id=str(issue_id),
                    cache_key=key,
                )
                return None

            if not isinstance(result, dict):
                logger.warning(
                    "Invalid cached issue URLs format",
                    issue_id=str(issue_id),
                    cache_key=key,
                    cached_type=type(result).__name__,
                )
                return None

            logger.debug(
                "Issue URLs cache hit",
                issue_id=str(issue_id),
                platforms=list(result.keys()),
            )
            return result

        except RuntimeError as e:
            logger.warning(
                "Redis connection failed during issue URLs cache lookup",
                issue_id=str(issue_id),
                error=str(e),
            )
            return None

    async def set_issue_urls(
        self,
        issue_id: uuid.UUID,
        urls: Dict[str, str],
        ttl: Optional[int] = None,
    ) -> bool:
        """Cache platform URL mappings for an issue.

        Args:
            issue_id: Canonical issue UUID
            urls: Dictionary mapping platform codes to URLs
            ttl: Optional TTL in seconds (defaults to ISSUE_URLS_CACHE_TTL)

        Returns:
            True if cached successfully, False otherwise

        Examples:
            >>> await set_issue_urls(issue_id, {"gcd": "https://...", "locg": "https://..."})
        """
        if not isinstance(issue_id, uuid.UUID):
            logger.debug("Invalid issue_id for issue URLs cache set", issue_id=issue_id)
            return False

        if not isinstance(urls, dict) or not urls:
            logger.debug("Invalid URLs for issue URLs cache set", urls=urls)
            return False

        key = self._build_issue_urls_key(issue_id)
        cache_ttl = ttl if ttl is not None else ISSUE_URLS_CACHE_TTL

        try:
            await self._redis.set(key, urls, ttl=cache_ttl)
            logger.debug(
                "Cached issue URLs",
                issue_id=str(issue_id),
                platforms=list(urls.keys()),
                ttl=cache_ttl,
                cache_key=key,
            )
            return True

        except RuntimeError as e:
            logger.warning(
                "Redis connection failed during issue URLs cache set",
                issue_id=str(issue_id),
                error=str(e),
            )
            return False

    async def delete_issue_urls(self, issue_id: uuid.UUID) -> bool:
        """Delete cached platform URL mappings for an issue.

        Args:
            issue_id: Canonical issue UUID

        Returns:
            True if deleted successfully (or key didn't exist), False on Redis error
        """
        if not isinstance(issue_id, uuid.UUID):
            return False

        key = self._build_issue_urls_key(issue_id)

        try:
            await self._redis.delete(key)
            logger.debug(
                "Deleted issue URLs cache entry",
                issue_id=str(issue_id),
                cache_key=key,
            )
            return True

        except RuntimeError as e:
            logger.warning(
                "Redis connection failed during issue URLs cache delete",
                issue_id=str(issue_id),
                error=str(e),
            )
            return False

    async def get_series_urls(
        self, series_run_id: uuid.UUID
    ) -> Optional[Dict[str, str]]:
        """Get cached platform URL mappings for a series.

        Args:
            series_run_id: Canonical series run UUID

        Returns:
            Dictionary mapping platform codes to series URLs, or None if not cached

        Examples:
            >>> await get_series_urls(series_run_id)
            {"gcd": "https://www.comics.org/series/12345/", "locg": "https://..."}
        """
        if not isinstance(series_run_id, uuid.UUID):
            logger.debug(
                "Invalid series_run_id for series URLs cache lookup",
                series_run_id=series_run_id,
            )
            return None

        key = self._build_series_urls_key(series_run_id)

        try:
            result = await self._redis.get(key)
            if result is None:
                logger.debug(
                    "Series URLs cache miss",
                    series_run_id=str(series_run_id),
                    cache_key=key,
                )
                return None

            if not isinstance(result, dict):
                logger.warning(
                    "Invalid cached series URLs format",
                    series_run_id=str(series_run_id),
                    cache_key=key,
                    cached_type=type(result).__name__,
                )
                return None

            logger.debug(
                "Series URLs cache hit",
                series_run_id=str(series_run_id),
                platforms=list(result.keys()),
            )
            return result

        except RuntimeError as e:
            logger.warning(
                "Redis connection failed during series URLs cache lookup",
                series_run_id=str(series_run_id),
                error=str(e),
            )
            return None

    async def set_series_urls(
        self,
        series_run_id: uuid.UUID,
        urls: Dict[str, str],
        ttl: Optional[int] = None,
    ) -> bool:
        """Cache platform URL mappings for a series.

        Args:
            series_run_id: Canonical series run UUID
            urls: Dictionary mapping platform codes to series URLs
            ttl: Optional TTL in seconds (defaults to SERIES_URLS_CACHE_TTL)

        Returns:
            True if cached successfully, False otherwise

        Examples:
            >>> await set_series_urls(series_run_id, {"gcd": "https://...", "locg": "https://..."})
        """
        if not isinstance(series_run_id, uuid.UUID):
            logger.debug(
                "Invalid series_run_id for series URLs cache set",
                series_run_id=series_run_id,
            )
            return False

        if not isinstance(urls, dict) or not urls:
            logger.debug("Invalid URLs for series URLs cache set", urls=urls)
            return False

        key = self._build_series_urls_key(series_run_id)
        cache_ttl = ttl if ttl is not None else SERIES_URLS_CACHE_TTL

        try:
            await self._redis.set(key, urls, ttl=cache_ttl)
            logger.debug(
                "Cached series URLs",
                series_run_id=str(series_run_id),
                platforms=list(urls.keys()),
                ttl=cache_ttl,
                cache_key=key,
            )
            return True

        except RuntimeError as e:
            logger.warning(
                "Redis connection failed during series URLs cache set",
                series_run_id=str(series_run_id),
                error=str(e),
            )
            return False

    async def delete_series_urls(self, series_run_id: uuid.UUID) -> bool:
        """Delete cached platform URL mappings for a series.

        Args:
            series_run_id: Canonical series run UUID

        Returns:
            True if deleted successfully (or key didn't exist), False on Redis error
        """
        if not isinstance(series_run_id, uuid.UUID):
            return False

        key = self._build_series_urls_key(series_run_id)

        try:
            await self._redis.delete(key)
            logger.debug(
                "Deleted series URLs cache entry",
                series_run_id=str(series_run_id),
                cache_key=key,
            )
            return True

        except RuntimeError as e:
            logger.warning(
                "Redis connection failed during series URLs cache delete",
                series_run_id=str(series_run_id),
                error=str(e),
            )
            return False

    async def invalidate_all_for_series(self, title: str, start_year: int) -> bool:
        """Invalidate all cache entries for a series (lookup + URLs).

        This is a convenience method that deletes both the series lookup cache
        and the series URL mappings cache for the given series.

        Args:
            title: Series title
            start_year: Series start year

        Returns:
            True if all entries deleted successfully, False if any deletion failed
        """
        series_deleted = await self.delete_series(title, start_year)

        success = True
        if not series_deleted:
            success = False

        return success

    async def invalidate_all_for_issue(self, issue_id: uuid.UUID) -> bool:
        """Invalidate all cache entries for an issue.

        This is a convenience method that deletes the issue URL mappings cache.

        Args:
            issue_id: Canonical issue UUID

        Returns:
            True if deletion was successful, False otherwise
        """
        return await self.delete_issue_urls(issue_id)

    async def clear_all_cache(self) -> bool:
        """Clear all series-related cache entries.

        WARNING: This clears ALL series cache entries from Redis, not just
        entries created by this service. Use with caution.

        Returns:
            True if cache cleared successfully, False otherwise

        Raises:
            RuntimeError: If Redis connection fails critically
        """
        try:
            await self._redis.clear()
            logger.info("Cleared all series cache entries")
            return True

        except RuntimeError as e:
            logger.error(
                "Failed to clear series cache",
                error=str(e),
            )
            return False
