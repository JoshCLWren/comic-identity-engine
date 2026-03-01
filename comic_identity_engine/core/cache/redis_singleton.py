"""Redis singleton for Comic Identity Engine.

SOURCE: Derived from comic-web-scrapers/comic_scrapers/common/redis_singleton.py
MODIFICATIONS:
- None - direct copy with updated imports

USAGE:
- Job queue (arq uses Redis internally)
- Application cache (DB 1)
- HTTP response cache (for FastAPI)
- Progress tracking for long-running jobs

USED BY:
- api/middleware/cache.py (HTTP response caching)
- services/operations.py (job progress)
- jobs/worker.py (arq job queue)
"""

import json
import logging
import os
import pickle
from typing import Any, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)

DEFAULT_POOL_SIZE = int(os.getenv("REDIS_POOL_SIZE", "100"))
DEFAULT_MAX_OVERFLOW = int(os.getenv("REDIS_MAX_OVERFLOW", "50"))
DEFAULT_SOCKET_CONNECT_TIMEOUT = float(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "2.0"))
DEFAULT_SOCKET_TIMEOUT = float(os.getenv("REDIS_SOCKET_TIMEOUT", "2.0"))


class RedisSingleton:
    """Singleton Redis client with connection pooling and serialization.

    This class provides thread-safe async access to Redis with automatic
    JSON and pickle serialization for Python objects. Uses connection
    pooling for improved performance.

    USAGE:
        # Initialize (typically in startup event)
        await redis_cache.initialize("redis://localhost:6379/1")

        # Use in application
        value = await redis_cache.get("my_key")
        await redis_cache.set("my_key", {"data": "value"}, ttl=3600)

        # Cleanup (typically in shutdown event)
        await redis_cache.close()
    """

    _instance: Optional["RedisSingleton"] = None

    def __new__(cls):
        """Create or return the singleton instance.

        Returns:
            RedisSingleton: The singleton instance
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the Redis singleton (lazy initialization)."""
        if hasattr(self, "_initialized"):
            return
        self._client: Optional[redis.Redis] = None
        self._initialized = False

    @property
    def client(self) -> redis.Redis:
        """Get the Redis client, ensuring it is initialized.

        Returns:
            redis.Redis: The Redis client

        Raises:
            RuntimeError: If Redis is not initialized
        """
        if self._client is None:
            raise RuntimeError("Redis not initialized. Call initialize() first.")
        return self._client

    async def initialize(self, redis_url: str) -> None:
        """Initialize Redis connection pool.

        Args:
            redis_url (str): Redis connection URL (e.g., "redis://localhost:6379/0")

        Raises:
            RuntimeError: If Redis is unavailable or connection fails
        """
        if self._initialized:
            logger.warning("Redis already initialized")
            return

        try:
            self._client = redis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=False,
                max_connections=DEFAULT_POOL_SIZE,
                socket_connect_timeout=DEFAULT_SOCKET_CONNECT_TIMEOUT,
                socket_timeout=DEFAULT_SOCKET_TIMEOUT,
            )
            self._initialized = True
            logger.info(
                f"Redis initialized: {redis_url} "
                f"(pool_size={DEFAULT_POOL_SIZE}, max_overflow={DEFAULT_MAX_OVERFLOW})"
            )
        except Exception as e:
            self._client = None
            self._initialized = False
            error_msg = f"Failed to connect to Redis: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from Redis by key.

        Args:
            key (str): Cache key

        Returns:
            Optional[Any]: The cached value, or None if not found

        Raises:
            RuntimeError: If Redis is not initialized or unavailable
        """
        try:
            data = await self.client.get(key)
            if data is None:
                return None
            try:
                return json.loads(data)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return pickle.loads(data)
        except Exception as e:
            error_msg = f"Failed to get key '{key}': {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set a value in Redis with optional TTL.

        Args:
            key (str): Cache key
            value (Any): Value to cache (JSON-serializable or picklable)
            ttl (Optional[int]): Time-to-live in seconds, or None for no expiration

        Raises:
            RuntimeError: If Redis is not initialized or unavailable
        """
        try:
            try:
                data = json.dumps(value)
            except (TypeError, ValueError):
                data = pickle.dumps(value)
            await self.client.set(key, data, ex=ttl)
        except Exception as e:
            error_msg = f"Failed to set key '{key}': {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    async def delete(self, key: str) -> None:
        """Delete a value from Redis by key.

        Args:
            key (str): Cache key

        Raises:
            RuntimeError: If Redis is not initialized or unavailable
        """
        try:
            await self.client.delete(key)
        except Exception as e:
            error_msg = f"Failed to delete key '{key}': {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    async def clear(self) -> None:
        """Clear all values from Redis.

        WARNING: This clears the entire database!

        Raises:
            RuntimeError: If Redis is not initialized or unavailable
        """
        try:
            await self.client.flushdb()
            logger.info("Redis cache cleared")
        except Exception as e:
            error_msg = f"Failed to clear Redis: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    async def close(self) -> None:
        """Close the Redis connection pool."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            self._initialized = False
            logger.info("Redis connection closed")


redis_cache = RedisSingleton()
