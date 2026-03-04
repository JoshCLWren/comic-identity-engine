"""HTTP client infrastructure for platform adapters.

This module provides a robust async HTTP client with:
- Connection pooling via httpx.AsyncClient
- Retry logic with exponential backoff
- Per-platform rate limiting
- Request/response logging
- Proper error handling

USAGE:
    async with HttpClient(platform="gcd") as client:
        response = await client.get(
            f"https://www.comics.org/api/issue/{issue_id}/?format=json"
        )
        data = response.json()
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from comic_identity_engine.errors import NetworkError, RateLimitError

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RetryConfig:
    """Configuration for retry behavior.

    Attributes:
        max_attempts: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay between retries in seconds (default: 10.0)
        exponential_base: Base for exponential backoff calculation (default: 2)
    """

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 10.0
    exponential_base: int = 2

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay <= 0:
            raise ValueError("base_delay must be positive")
        if self.max_delay <= 0:
            raise ValueError("max_delay must be positive")


class RateLimiter:
    """Simple in-memory rate limiter for per-platform request throttling.

    Implements a token bucket algorithm with 1 request per second minimum rate.
    Each platform gets its own rate limiter instance.

    USAGE:
        limiter = RateLimiter(platform="gcd", min_interval=1.0)
        await limiter.acquire()
        # Make request
    """

    def __init__(
        self,
        platform: str,
        min_interval: float = 1.0,
    ) -> None:
        """Initialize the rate limiter.

        Args:
            platform: Platform identifier (e.g., 'gcd', 'hip', 'cpg')
            min_interval: Minimum seconds between requests (default: 1.0)
        """
        self.platform = platform
        self.min_interval = min_interval
        self._last_request_time: float | None = None
        self._lock = asyncio.Lock()
        self._logger = structlog.get_logger(__name__).bind(platform=platform)

    async def acquire(self) -> None:
        """Acquire permission to make a request.

        Blocks until the minimum interval has passed since the last request.
        """
        async with self._lock:
            if self._last_request_time is not None:
                elapsed = asyncio.get_event_loop().time() - self._last_request_time
                if elapsed < self.min_interval:
                    wait_time = self.min_interval - elapsed
                    self._logger.debug(
                        "rate_limit.wait",
                        wait_seconds=wait_time,
                        platform=self.platform,
                    )
                    await asyncio.sleep(wait_time)

            self._last_request_time = asyncio.get_event_loop().time()
            self._logger.debug("rate_limit.acquired", platform=self.platform)


class HttpClientError(NetworkError):
    """Error specific to HTTP client operations."""

    def __init__(
        self,
        message: str,
        source: str | None = None,
        original_error: Exception | None = None,
        status_code: int | None = None,
        url: str | None = None,
    ) -> None:
        """Initialize HTTP client error.

        Args:
            message: Error message
            source: Platform identifier
            original_error: Original exception that caused this error
            status_code: HTTP status code if applicable
            url: URL that was being requested
        """
        self.url = url
        super().__init__(message, source, original_error, status_code)

    def __str__(self) -> str:
        """Return string representation of the error."""
        url_str = f" (URL: {self.url})" if self.url else ""
        return f"{super().__str__()}{url_str}"


class HttpClient:
    """Async HTTP client with retry logic, rate limiting, and logging.

    This client provides a context manager interface and should be used
    with 'async with' to ensure proper resource cleanup.

    FEATURES:
    - Connection pooling (max 10 connections per platform)
    - Exponential backoff retries (max 3 attempts, starting at 1s)
    - Per-platform rate limiting (1 request per second minimum)
    - Request/response logging via structlog
    - Timeout handling (default 30s)

    USAGE:
        async with HttpClient(platform="gcd") as client:
            response = await client.get("https://api.example.com/data")
            data = response.json()

    ATTRIBUTES:
        platform: Platform identifier for rate limiting and logging
        timeout: Request timeout in seconds
        max_connections: Maximum concurrent connections
        retry_config: Retry behavior configuration
    """

    DEFAULT_TIMEOUT = 30.0
    DEFAULT_MAX_CONNECTIONS = 10
    DEFAULT_RETRY_CONFIG = RetryConfig()
    DEFAULT_VERIFY_SSL = True

    def __init__(
        self,
        platform: str,
        timeout: float = DEFAULT_TIMEOUT,
        max_connections: int = DEFAULT_MAX_CONNECTIONS,
        retry_config: RetryConfig | None = None,
        base_url: str | None = None,
        headers: dict[str, str] | None = None,
        verify_ssl: bool = DEFAULT_VERIFY_SSL,
    ) -> None:
        """Initialize the HTTP client.

        Args:
            platform: Platform identifier (e.g., 'gcd', 'hip', 'cpg')
            timeout: Request timeout in seconds (default: 30.0)
            max_connections: Maximum concurrent connections (default: 10)
            retry_config: Retry configuration (default: 3 attempts, exponential backoff)
            base_url: Optional base URL for all requests
            headers: Optional default headers for all requests
            verify_ssl: Whether to verify SSL certificates (default: True)

        Raises:
            ValueError: If timeout or max_connections is invalid
        """
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_connections < 1:
            raise ValueError("max_connections must be at least 1")

        self.platform = platform
        self.timeout = timeout
        self.max_connections = max_connections
        self.retry_config = retry_config or self.DEFAULT_RETRY_CONFIG
        self.base_url = base_url
        self.headers = headers or {}
        self.verify_ssl = verify_ssl

        self._client: httpx.AsyncClient | None = None
        self._rate_limiter = RateLimiter(platform=platform)
        self._logger = structlog.get_logger(__name__).bind(platform=platform)

    async def __aenter__(self) -> HttpClient:
        """Enter async context and initialize the httpx client."""
        await self._ensure_initialized()
        return self

    async def _ensure_initialized(self) -> None:
        """Ensure the httpx client is initialized."""
        if self._client is None:
            limits = httpx.Limits(
                max_connections=self.max_connections,
                max_keepalive_connections=self.max_connections,
            )

            timeout = httpx.Timeout(self.timeout)

            self._client = httpx.AsyncClient(
                timeout=timeout,
                limits=limits,
                base_url=self.base_url or "",
                headers=self.headers,
                verify=self.verify_ssl,
            )

            self._logger.debug(
                "http_client.initialized",
                platform=self.platform,
                timeout=self.timeout,
                max_connections=self.max_connections,
                verify_ssl=self.verify_ssl,
            )

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit async context and cleanup resources."""
        if self._client:
            await self._client.aclose()
            self._client = None
            self._logger.debug("http_client.closed", platform=self.platform)

    def _is_retryable_error(self, exc: Exception) -> bool:
        """Check if an exception should trigger a retry.

        Retry on:
        - Network timeouts
        - Connection errors
        - 5xx server errors

        Args:
            exc: The exception to check

        Returns:
            True if the error is retryable
        """
        if isinstance(exc, httpx.TimeoutException):
            return True
        if isinstance(exc, httpx.ConnectError):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code >= 500
        return False

    async def _make_request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make a single HTTP request with logging.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            **kwargs: Additional arguments passed to httpx

        Returns:
            httpx.Response object

        Raises:
            HttpClientError: On request failure
        """
        if not self._client:
            raise RuntimeError("HttpClient not initialized. Use 'async with' context.")

        request_id = structlog.contextvars.get_contextvars().get("request_id", "")
        log = self._logger.bind(
            http_method=method,
            url=url,
            request_id=request_id,
        )

        log.debug("http.request.starting")

        try:
            response = await self._client.request(method, url, **kwargs)
            response.raise_for_status()

            log.debug(
                "http.request.success",
                status_code=response.status_code,
                content_length=len(response.content),
            )

            return response

        except httpx.HTTPStatusError as e:
            log.warning(
                "http.request.failed",
                status_code=e.response.status_code,
                error=str(e),
            )

            if e.response.status_code == 429:
                retry_after = e.response.headers.get("retry-after")
                raise RateLimitError(
                    message=f"Rate limited by {self.platform}",
                    source=self.platform,
                    original_error=e,
                    retry_after=int(retry_after) if retry_after else None,
                ) from e

            raise HttpClientError(
                message=f"HTTP error {e.response.status_code}",
                source=self.platform,
                original_error=e,
                status_code=e.response.status_code,
                url=str(e.request.url),
            ) from e

        except httpx.TimeoutException as e:
            log.error("http.request.timeout", error=str(e))
            raise HttpClientError(
                message=f"Request timeout after {self.timeout}s",
                source=self.platform,
                original_error=e,
                url=url,
            ) from e

        except httpx.ConnectError as e:
            log.error("http.request.connection_error", error=str(e))
            raise HttpClientError(
                message=f"Connection error: {e}",
                source=self.platform,
                original_error=e,
                url=url,
            ) from e

        except httpx.HTTPError as e:
            log.error("http.request.error", error=str(e))
            raise HttpClientError(
                message=f"HTTP error: {e}",
                source=self.platform,
                original_error=e,
                url=url,
            ) from e

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an HTTP request with rate limiting and retries.

        Args:
            method: HTTP method
            url: Request URL
            **kwargs: Additional arguments passed to httpx

        Returns:
            httpx.Response object

        Raises:
            HttpClientError: After all retries exhausted
            RateLimitError: On rate limit responses (not retried)
        """
        await self._rate_limiter.acquire()

        # Use tenacity for retry logic with exponential backoff
        @retry(
            stop=stop_after_attempt(self.retry_config.max_attempts),
            wait=wait_exponential(
                multiplier=self.retry_config.base_delay,
                max=self.retry_config.max_delay,
                exp_base=self.retry_config.exponential_base,
            ),
            retry=retry_if_exception_type(HttpClientError),
            reraise=True,
        )
        async def _do_request() -> httpx.Response:
            try:
                return await self._make_request(method, url, **kwargs)
            except HttpClientError as e:
                # Only retry on 5xx errors and timeouts
                if e.status_code is not None and e.status_code < 500:
                    raise
                self._logger.warning(
                    "http.request.retry",
                    attempt="current",
                    error=str(e),
                )
                raise

        try:
            return await _do_request()
        except HttpClientError:
            self._logger.error(
                "http.request.failed_permanently",
                method=method,
                url=url,
                attempts=self.retry_config.max_attempts,
            )
            raise

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make a GET request.

        Args:
            url: Request URL (or path if base_url was set)
            params: Query parameters
            headers: Additional headers
            **kwargs: Additional arguments passed to httpx

        Returns:
            httpx.Response object
        """
        await self._ensure_initialized()
        request_headers = {**self.headers, **(headers or {})}
        return await self._request_with_retry(
            "GET",
            url,
            params=params,
            headers=request_headers,
            **kwargs,
        )

    async def post(
        self,
        url: str,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make a POST request.

        Args:
            url: Request URL (or path if base_url was set)
            data: Form data
            json: JSON body
            headers: Additional headers
            **kwargs: Additional arguments passed to httpx

        Returns:
            httpx.Response object
        """
        request_headers = {**self.headers, **(headers or {})}
        return await self._request_with_retry(
            "POST",
            url,
            data=data,
            json=json,
            headers=request_headers,
            **kwargs,
        )

    async def put(
        self,
        url: str,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make a PUT request.

        Args:
            url: Request URL (or path if base_url was set)
            data: Form data
            json: JSON body
            headers: Additional headers
            **kwargs: Additional arguments passed to httpx

        Returns:
            httpx.Response object
        """
        request_headers = {**self.headers, **(headers or {})}
        return await self._request_with_retry(
            "PUT",
            url,
            data=data,
            json=json,
            headers=request_headers,
            **kwargs,
        )

    async def patch(
        self,
        url: str,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make a PATCH request.

        Args:
            url: Request URL (or path if base_url was set)
            data: Form data
            json: JSON body
            headers: Additional headers
            **kwargs: Additional arguments passed to httpx

        Returns:
            httpx.Response object
        """
        request_headers = {**self.headers, **(headers or {})}
        return await self._request_with_retry(
            "PATCH",
            url,
            data=data,
            json=json,
            headers=request_headers,
            **kwargs,
        )

    async def delete(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make a DELETE request.

        Args:
            url: Request URL (or path if base_url was set)
            headers: Additional headers
            **kwargs: Additional arguments passed to httpx

        Returns:
            httpx.Response object
        """
        request_headers = {**self.headers, **(headers or {})}
        return await self._request_with_retry(
            "DELETE",
            url,
            headers=request_headers,
            **kwargs,
        )

    async def request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an HTTP request with the specified method.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE)
            url: Request URL (or path if base_url was set)
            **kwargs: Additional arguments passed to httpx

        Returns:
            httpx.Response object
        """
        return await self._request_with_retry(method, url, **kwargs)
