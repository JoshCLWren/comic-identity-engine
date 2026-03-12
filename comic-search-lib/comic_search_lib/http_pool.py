"""Shared HTTP connection pool for efficient TCP connection reuse.

This module provides domain-specific connection pooling for HTTP-based scrapers
(GCD, CPG, AA, CCL) to avoid creating new connections for each request.

Key benefits:
- Reuses TCP connections across requests to the same domain
- Reduces latency and resource usage
- Built-in rate limiting per domain
- Custom SSL configuration per domain
- Proper lifecycle management

Example:
    >>> from comic_search_lib.http_pool import get_http_pool
    >>>
    >>> async def fetch_gcd_issue(issue_id: str):
    ...     pool = get_http_pool()
    ...     session = await pool.get_session("https://www.comics.org/issue/123")
    ...     async with session.get(url) as response:
    ...         return await response.text()
"""

from __future__ import annotations

import asyncio
import logging
import ssl
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict, Optional

import aiohttp


logger = logging.getLogger(__name__)


@dataclass
class DomainConfig:
    """Configuration for a domain's connection pool."""

    rate_limit: float = 1.0  # Seconds between requests
    max_connections: int = 10  # Max concurrent connections
    timeout: float = 30.0  # Request timeout in seconds
    verify_ssl: bool = True  # Whether to verify SSL certificates
    max_keepalive: int = 5  # Max keep-alive connections per host


# Domain-specific configurations
DOMAIN_CONFIGS: Dict[str, DomainConfig] = {
    "comics.org": DomainConfig(
        rate_limit=0.5,
        max_connections=10,
        timeout=15.0,
        verify_ssl=True,
        max_keepalive=5,
    ),
    "comicspriceguide.com": DomainConfig(
        rate_limit=1.0,
        max_connections=5,
        timeout=10.0,
        verify_ssl=True,
        max_keepalive=3,
    ),
    "atomicavenue.com": DomainConfig(
        rate_limit=1.0,
        max_connections=5,
        timeout=10.0,
        verify_ssl=True,
        max_keepalive=3,
    ),
    "comiccollectorlive.com": DomainConfig(
        rate_limit=1.5,
        max_connections=5,
        timeout=40.0,
        verify_ssl=False,  # CCL has SSL certificate issues
        max_keepalive=3,
    ),
}


class HttpConnectionPool:
    """
    Shared HTTP connection pool with domain-specific sessions.

    Maintains a separate aiohttp.ClientSession for each domain with
    custom configuration (rate limiting, SSL, timeouts).
    """

    def __init__(self):
        """Initialize the HTTP connection pool."""
        self._sessions: Dict[str, aiohttp.ClientSession] = {}
        self._rate_limit_locks: Dict[str, asyncio.Lock] = {}
        self._last_request_time: Dict[str, float] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize sessions for all configured domains."""
        if self._initialized:
            return

        logger.info("Initializing HTTP connection pool")

        for domain, config in DOMAIN_CONFIGS.items():
            await self._create_session(domain, config)

        self._initialized = True
        logger.info(
            f"HTTP connection pool initialized with {len(self._sessions)} domains"
        )

    async def _create_session(self, domain: str, config: DomainConfig) -> None:
        """Create a session for a domain."""
        if domain in self._sessions:
            return

        ssl_context = None
        if not config.verify_ssl:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        connector = aiohttp.TCPConnector(
            limit=config.max_connections,
            limit_per_host=config.max_keepalive,
            ssl=ssl_context if not config.verify_ssl else None,
        )

        timeout = aiohttp.ClientTimeout(total=config.timeout)

        session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
        )

        self._sessions[domain] = session
        self._rate_limit_locks[domain] = asyncio.Lock()
        self._last_request_time[domain] = 0.0

        logger.debug(f"Created session for {domain} (max={config.max_connections})")

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        from urllib.parse import urlparse

        parsed = urlparse(url)
        domain = parsed.netloc

        # Remove port if present
        if ":" in domain:
            domain = domain.split(":")[0]

        return domain

    async def _get_config(self, domain: str) -> DomainConfig:
        """Get configuration for a domain, creating default if needed."""
        if domain not in DOMAIN_CONFIGS:
            logger.warning(f"No config for {domain}, using defaults")
            DOMAIN_CONFIGS[domain] = DomainConfig()
            await self._create_session(domain, DOMAIN_CONFIGS[domain])

        return DOMAIN_CONFIGS[domain]

    @asynccontextmanager
    async def get_session(self, url: str):
        """
        Get a session for a URL with rate limiting.

        Args:
            url: The URL to request

        Yields:
            aiohttp.ClientSession configured for the URL's domain
        """
        if not self._initialized:
            await self.initialize()

        domain = self._extract_domain(url)
        config = await self._get_config(domain)

        # Apply rate limiting
        async with self._rate_limit_locks[domain]:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_request_time[domain]

            if elapsed < config.rate_limit:
                wait_time = config.rate_limit - elapsed
                logger.debug(f"Rate limiting {domain}: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)

            self._last_request_time[domain] = asyncio.get_event_loop().time()

        session = self._sessions[domain]
        yield session

    async def cleanup(self) -> None:
        """Close all sessions."""
        if not self._initialized:
            return

        logger.info("Cleaning up HTTP connection pool")

        for domain, session in self._sessions.items():
            try:
                await asyncio.wait_for(session.close(), timeout=5.0)
                logger.debug(f"Closed session for {domain}")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout closing session for {domain}")
            except Exception as e:
                logger.warning(f"Error closing session for {domain}: {e}")

        self._sessions.clear()
        self._rate_limit_locks.clear()
        self._last_request_time.clear()
        self._initialized = False

    async def __aenter__(self):
        """Enter context manager."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager."""
        await self.cleanup()


_global_pool: Optional[HttpConnectionPool] = None


async def get_http_pool() -> HttpConnectionPool:
    """Get or create the global HTTP connection pool.

    Returns:
        The shared HttpConnectionPool instance
    """
    global _global_pool

    if _global_pool is None:
        _global_pool = HttpConnectionPool()
        await _global_pool.initialize()

    return _global_pool


@asynccontextmanager
async def http_session(url: str):
    """
    Context manager for getting an HTTP session with automatic cleanup.

    Example:
        >>> async with http_session("https://www.comics.org/issue/123") as session:
        ...     async with session.get(url) as response:
        ...         return await response.text()
    """
    pool = await get_http_pool()

    async with pool.get_session(url) as session:
        yield session
