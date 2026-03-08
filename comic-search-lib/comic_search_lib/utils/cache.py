"""Simple in-memory cache for search results."""

import time
from typing import Any, Dict, Optional


class SimpleCache:
    """Simple in-memory cache with TTL support.

    No Redis required - just a Python dict with expiration.
    """

    def __init__(self, ttl: int = 43200):
        """Initialize cache.

        Args:
            ttl: Default time-to-live in seconds (default: 12 hours)
        """
        self._cache: Dict[str, tuple[Any, float]] = {}
        self._ttl = ttl

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value if exists and not expired, None otherwise
        """
        if key not in self._cache:
            return None

        value, expiry = self._cache[key]
        if time.time() > expiry:
            del self._cache[key]
            return None

        return value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if not provided)
        """
        expiry = time.time() + (ttl or self._ttl)
        self._cache[key] = (value, expiry)

    async def delete(self, key: str) -> None:
        """Delete value from cache.

        Args:
            key: Cache key
        """
        self._cache.pop(key, None)

    async def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()
