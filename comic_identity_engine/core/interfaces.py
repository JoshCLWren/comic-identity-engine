"""Core interfaces for Comic Identity Engine.

SOURCE: Derived from comic-web-scrapers/comic_scrapers/common/interfaces.py
MODIFICATIONS:
- Removed: ComicScraper (not needed for our use case)
- Kept: SessionManager, CacheProvider interfaces
- Added: None, interfaces are sufficient for our needs

USAGE:
- Abstract base classes for dependency injection
- Type hints for adapter implementations
- Consistent behavior across implementations

USED BY:
- Cache implementations (core/cache/*)
- HTTP session management (core/http/*)
"""

import abc
from typing import Any, Optional


class SessionManager(abc.ABC):
    """Abstract base class for managing HTTP sessions.

    This class provides an interface for session pooling and lifecycle
    management to ensure proper resource handling.

    USAGE:
    - HTTP session pooling for platform adapters
    - Connection lifecycle management
    - Proper cleanup on shutdown
    """

    @abc.abstractmethod
    async def get_session(self) -> Any:
        """Get an HTTP session from pool or create new one.

        Returns:
            Any: A session object (e.g., httpx.AsyncClient, aiohttp.ClientSession)

        Raises:
            ResourceExhaustedError: If session limit reached
            NetworkError: If session creation fails
        """
        pass

    @abc.abstractmethod
    async def release_session(self, session: Any) -> None:
        """Release a session back to the pool or close it.

        Args:
            session: The session to release

        Raises:
            NetworkError: If session release fails
        """
        pass

    @abc.abstractmethod
    async def cleanup(self) -> None:
        """Clean up all sessions.

        This method should be called when the session manager is no longer needed
        to ensure proper resource cleanup.
        """
        pass


class CacheProvider(abc.ABC):
    """Abstract base class for cache providers.

    This class provides an interface for caching adapter results
    to improve performance and reduce load on platform APIs.

    USAGE:
    - HTTP response caching
    - Query result caching
    - Cross-platform match caching
    """

    @abc.abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache.

        Args:
            key (str): Cache key

        Returns:
            Optional[Any]: The cached value, or None if not found
        """
        pass

    @abc.abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set a value in the cache.

        Args:
            key (str): Cache key
            value (Any): Value to cache
            ttl (Optional[int]): Time-to-live in seconds, or None for no expiration
        """
        pass

    @abc.abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a value from the cache.

        Args:
            key (str): Cache key
        """
        pass

    @abc.abstractmethod
    async def clear(self) -> None:
        """Clear all values from the cache."""
        pass
