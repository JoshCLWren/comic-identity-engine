"""Caching system for Comic Identity Engine.

SOURCE: Derived from comic-web-scrapers/comic_scrapers/common/cache.py
MODIFICATIONS:
- None - direct copy with updated imports

USAGE:
- Local caching within adapter instances
- Reducing redundant HTTP requests
- Per-key locks for concurrency

USED BY:
- Platform adapters (for local caching)
- Identity resolver (for candidate caching)
- TieredCache for combining L1/L2 cache
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional, Tuple

from comic_identity_engine.core.interfaces import CacheProvider

logger = logging.getLogger(__name__)


class MemoryCache(CacheProvider):
    """In-memory cache implementation.

    This implementation stores cache entries in memory with optional TTL.
    Uses per-key locks for improved concurrency.

    USAGE:
    - L1 cache for frequently accessed data
    - Adapter-local caching
    - Reducing redundant HTTP requests
    """

    def __init__(self, max_keys: int = 10000):
        """Initialize the memory cache.

        Args:
            max_keys (int): Maximum number of keys to store before eviction
        """
        self._cache: Dict[str, Tuple[Any, Optional[float]]] = {}
        self._global_lock = asyncio.Lock()
        self._key_locks: Dict[str, asyncio.Lock] = {}
        self._max_keys = max_keys
        self._access_times: Dict[str, float] = {}

    async def _get_key_lock(self, key: str) -> asyncio.Lock:
        """Get a lock for a specific key, creating one if needed.

        Args:
            key (str): Cache key

        Returns:
            asyncio.Lock: Lock for this key
        """
        async with self._global_lock:
            if key not in self._key_locks:
                self._key_locks[key] = asyncio.Lock()
            return self._key_locks[key]

    async def _cleanup_unused_locks(self):
        """Clean up locks for keys that are no longer in the cache."""
        async with self._global_lock:
            unused_keys = [k for k in self._key_locks if k not in self._cache]
            for key in unused_keys:
                del self._key_locks[key]

    async def _ensure_capacity(self):
        """Ensure the cache doesn't exceed the maximum number of keys.

        Uses LRU strategy for eviction.
        """
        async with self._global_lock:
            if len(self._cache) >= self._max_keys:
                lru_keys = sorted(self._access_times.items(), key=lambda x: x[1])[
                    : len(self._cache) // 10 or 1
                ]
                for key, _ in lru_keys:
                    if key in self._cache:
                        del self._cache[key]
                    if key in self._access_times:
                        del self._access_times[key]

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache.

        Args:
            key (str): Cache key

        Returns:
            Optional[Any]: The cached value, or None if not found or expired
        """
        self._access_times[key] = time.time()

        key_lock = await self._get_key_lock(key)

        async with key_lock:
            if key not in self._cache:
                return None

            value, expiry = self._cache[key]

            if expiry is not None and time.time() > expiry:
                del self._cache[key]
                if key in self._access_times:
                    del self._access_times[key]
                asyncio.create_task(self._cleanup_unused_locks())
                return None

            return value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set a value in the cache.

        Args:
            key (str): Cache key
            value (Any): Value to cache
            ttl (Optional[int]): Time-to-live in seconds, or None for no expiration
        """
        await self._ensure_capacity()

        key_lock = await self._get_key_lock(key)

        self._access_times[key] = time.time()

        async with key_lock:
            expiry = time.time() + ttl if ttl is not None else None
            self._cache[key] = (value, expiry)

    async def delete(self, key: str) -> None:
        """Delete a value from the cache.

        Args:
            key (str): Cache key
        """
        key_lock = await self._get_key_lock(key)

        async with key_lock:
            if key in self._cache:
                del self._cache[key]
            if key in self._access_times:
                del self._access_times[key]

        asyncio.create_task(self._cleanup_unused_locks())

    async def clear(self) -> None:
        """Clear all values from the cache."""
        async with self._global_lock:
            self._cache.clear()
            self._access_times.clear()
            self._key_locks.clear()

    def get_stats(self) -> Dict[str, int]:
        """Get statistics about the cache.

        Returns:
            Dict with cache statistics
        """
        now = time.time()
        count = len(self._cache)
        expired = sum(
            1
            for _, expiry in self._cache.values()
            if expiry is not None and now > expiry
        )

        return {
            "total_entries": count,
            "expired_entries": expired,
            "active_entries": count - expired,
            "total_locks": len(self._key_locks),
        }


class TieredCache(CacheProvider):
    """Tiered cache implementation that combines multiple cache providers.

    This implementation checks caches in order (fastest to slowest)
    and populates missing entries in faster caches when found in slower ones.

    USAGE:
    - Combine MemoryCache (L1) with Redis (L2)
    - Automatic promotion from L2 to L1
    - Write-through to all layers
    """

    def __init__(self, providers: list):
        """Initialize the tiered cache.

        Args:
            providers (list): Ordered list of cache providers (fastest to slowest)
                Example: [MemoryCache(), RedisCache()]
        """
        self.providers = providers

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache.

        Checks each provider in order, populating faster caches when a value
        is found in a slower cache.

        Args:
            key (str): Cache key

        Returns:
            Optional[Any]: The cached value, or None if not found
        """
        for i, provider in enumerate(self.providers):
            value = await provider.get(key)
            if value is not None:
                for j in range(i):
                    await self.providers[j].set(key, value)
                return value

        return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set a value in all cache providers.

        Args:
            key (str): Cache key
            value (Any): Value to cache
            ttl (Optional[int]): Time-to-live in seconds, or None for no expiration
        """
        for provider in self.providers:
            await provider.set(key, value, ttl)

    async def delete(self, key: str) -> None:
        """Delete a value from all cache providers.

        Args:
            key (str): Cache key
        """
        for provider in self.providers:
            await provider.delete(key)

    async def clear(self) -> None:
        """Clear all values from all cache providers."""
        for provider in self.providers:
            await provider.clear()
