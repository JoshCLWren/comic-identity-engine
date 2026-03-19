"""HTTP cache decorator for Comic Identity Engine.

SOURCE: Derived from comic-web-scrapers/comic_scrapers/common/http_cache_decorator.py
MODIFICATIONS:
- Updated imports for our redis_cache

USAGE:
- Caching HTTP requests from platform APIs
- Reducing rate limit hits
- Configurable TTL per request

USED BY:
- Platform adapters (for caching HTTP responses)

EXAMPLE:
    @http_cached(ttl=3600)
    async def fetch_issue_data(url: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            return response.json()
"""

import functools
import inspect
import logging
from typing import Any, Callable

from comic_identity_engine.core.cache.redis_singleton import redis_cache

logger = logging.getLogger(__name__)


def http_cached(ttl: int = 300):
    """Decorator for caching HTTP requests based on URL.

    This decorator caches function results using the URL parameter as the cache key.
    The decorated function must have a "url" parameter (either positional or keyword).

    Args:
        ttl: Default time-to-live for cache entries in seconds. Defaults to 300.

    Returns:
        Decorated function with HTTP caching

    Raises:
        RuntimeError: If decorated function doesn't have a "url" parameter

    Examples:
        Basic usage with default TTL:
            @http_cached(ttl=3600)
            async def fetch_html(url: str) -> str:
                async with httpx.AsyncClient() as client:
                    response = await client.get(url)
                    return response.text

        With TTL override via function parameter:
            @http_cached(ttl=3600)
            async def fetch_html(url: str, ttl: int | None = None) -> str:
                async with httpx.AsyncClient() as client:
                    response = await client.get(url)
                    return response.text

            # Uses TTL 7200 from parameter
            await fetch_html("https://example.com", ttl=7200)

            # Uses default TTL 3600
            await fetch_html("https://example.com")
    """

    def decorator(func: Callable) -> Callable:
        sig = inspect.signature(func)
        params = sig.parameters

        if "url" not in params:
            raise RuntimeError(
                f"Function '{getattr(func, '__name__', repr(func))}' decorated with @http_cached "
                "must have a 'url' parameter"
            )

        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            url = bound_args.arguments.get("url")
            if url is None:
                raise RuntimeError(
                    f"Function '{getattr(func, '__name__', repr(func))}' missing required 'url' parameter"
                )

            cache_key = url

            effective_ttl = ttl
            if "ttl" in params and "ttl" in bound_args.arguments:
                param_ttl = bound_args.arguments["ttl"]
                if param_ttl is not None:
                    effective_ttl = param_ttl

            try:
                cached_value = await redis_cache.get(cache_key)
                if cached_value is not None:
                    logger.debug(f"Cache HIT: {cache_key}")
                    return cached_value
                else:
                    logger.debug(f"Cache MISS: {cache_key}")
            except RuntimeError as e:
                logger.debug(f"Cache unavailable for {cache_key}: {e}")
            except Exception as e:
                logger.debug(f"Unexpected error getting cache for {cache_key}: {e}")

            result = await func(*args, **kwargs)

            try:
                await redis_cache.set(cache_key, result, ttl=effective_ttl)
                logger.debug(f"Cache SET: {cache_key} (ttl={effective_ttl}s)")
            except RuntimeError as e:
                logger.debug(f"Failed to set cache for {cache_key}: {e}")
            except Exception as e:
                logger.debug(f"Unexpected error setting cache for {cache_key}: {e}")

            return result

        return wrapper

    return decorator
