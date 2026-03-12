"""Circuit breaker with Fibonacci backoff for resilient web scraping.

This module provides a circuit breaker pattern that:
1. Tracks failures and opens circuit after threshold
2. Uses Fibonacci backoff for retry delays
3. Automatically recovers when service becomes healthy
4. Emits events for monitoring

Example:
    >>> from comic_search_lib.resilience import circuit_breaker
    >>>
    >>> @circuit_breaker(failure_threshold=5, reset_timeout_seconds=60)
    >>> async def fetch_comic_data(url):
    ...     # Will retry with Fibonacci backoff: 1s, 1s, 2s, 3s, 5s, 8s...
    ...     # Circuit opens after 5 failures
    ...     # Closes again after successful request
    ...     return await httpx.get(url)
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Any, Callable, TypeVar

from comic_search_lib.exceptions import SearchError


logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests allowed
    OPEN = "open"  # Circuit tripped, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5
    reset_timeout_seconds: int = 60
    max_delay_seconds: int = 300
    jitter_factor: float = 0.1


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker."""

    state: CircuitState
    failure_count: int
    success_count: int
    last_failure_time: float | None
    last_success_time: float | None
    opened_at: float | None


def fibonacci_delay(attempt: int, max_delay: int = 300) -> int:
    """
    Calculate Fibonacci-based delay for retry attempt.

    Sequence: 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377...

    Args:
        attempt: Retry attempt number (1-indexed)
        max_delay: Maximum delay in seconds

    Returns:
        Delay in seconds
    """
    a, b = 1, 1
    for _ in range(attempt - 1):
        a, b = b, a + b
    return min(a, max_delay)


class CircuitBreaker:
    """
    Circuit breaker with Fibonacci backoff.

    Prevents cascading failures by blocking requests to failing services
    and automatically recovering when service becomes healthy.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        reset_timeout_seconds: int = 60,
        max_delay_seconds: int = 300,
    ):
        """Initialize circuit breaker.

        Args:
            name: Circuit breaker name for logging/metrics
            failure_threshold: Failures before opening circuit
            reset_timeout_seconds: Seconds before attempting recovery
            max_delay_seconds: Maximum Fibonacci backoff delay
        """
        self.name = name
        self.config = CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            reset_timeout_seconds=reset_timeout_seconds,
            max_delay_seconds=max_delay_seconds,
        )

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._last_success_time: float | None = None
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    @property
    def stats(self) -> CircuitBreakerStats:
        """Get circuit breaker statistics."""
        return CircuitBreakerStats(
            state=self._state,
            failure_count=self._failure_count,
            success_count=self._success_count,
            last_failure_time=self._last_failure_time,
            last_success_time=self._last_success_time,
            opened_at=self._opened_at,
        )

    def can_attempt(self) -> bool:
        """
        Check if request should be allowed.

        Returns:
            True if request allowed, False if circuit is open
        """
        now = time.time()

        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            # Check if reset timeout has elapsed
            if self._opened_at and (
                now - self._opened_at >= self.config.reset_timeout_seconds
            ):
                logger.info(
                    f"Circuit '{self.name}': OPEN -> HALF_OPEN (reset timeout elapsed)"
                )
                self._state = CircuitState.HALF_OPEN
                return True
            return False

        return True  # HALF_OPEN: allow test request

    def record_success(self) -> None:
        """Record successful request."""
        self._success_count += 1
        self._last_success_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            logger.info(
                f"Circuit '{self.name}': HALF_OPEN -> CLOSED (recovery confirmed)"
            )
            self._state = CircuitState.CLOSED
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record failed request."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            logger.warning(
                f"Circuit '{self.name}': HALF_OPEN -> OPEN (recovery failed)"
            )
            self._state = CircuitState.OPEN
            self._opened_at = time.time()
        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self.config.failure_threshold:
                logger.warning(
                    f"Circuit '{self.name}': CLOSED -> OPEN "
                    f"({self._failure_count} failures >= threshold {self.config.failure_threshold})"
                )
                self._state = CircuitState.OPEN
                self._opened_at = time.time()

    async def call_with_retry[T](
        self,
        operation: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Execute operation with circuit breaker and Fibonacci backoff.

        Args:
            operation: Async callable to execute
            *args: Positional args for operation
            **kwargs: Keyword args for operation

        Returns:
            Result from operation

        Raises:
            SearchError: If circuit is open or all retries exhausted
        """
        if not self.can_attempt():
            raise SearchError(
                f"Circuit '{self.name}' is OPEN - blocking request",
                source="circuit_breaker",
            )

        attempt = 0
        last_error: Exception | None = None

        while True:
            attempt += 1

            try:
                result = await operation(*args, **kwargs)
                self.record_success()
                return result

            except Exception as e:
                last_error = e
                self.record_failure()

                # Check if circuit opened after this failure
                if not self.can_attempt():
                    raise SearchError(
                        f"Circuit '{self.name}' opened after {attempt} attempts",
                        source="circuit_breaker",
                        original_error=e,
                    ) from e

                # Calculate Fibonacci delay with jitter
                base_delay = fibonacci_delay(attempt, self.config.max_delay_seconds)
                jitter = random.uniform(
                    1.0 - self.config.jitter_factor,
                    1.0 + self.config.jitter_factor,
                )
                actual_delay = base_delay * jitter

                logger.warning(
                    f"Circuit '{self.name}': attempt {attempt} failed: {e}, "
                    f"retrying after {actual_delay:.1f}s"
                )

                await asyncio.sleep(actual_delay)


def circuit_breaker(
    name: str | None = None,
    failure_threshold: int = 5,
    reset_timeout_seconds: int = 60,
    max_delay_seconds: int = 300,
):
    """
    Decorator to apply circuit breaker with Fibonacci backoff to async function.

    Args:
        name: Circuit breaker name (defaults to function name)
        failure_threshold: Failures before opening circuit
        reset_timeout_seconds: Seconds before attempting recovery
        max_delay_seconds: Maximum Fibonacci backoff delay

    Example:
        >>> @circuit_breaker(failure_threshold=3, reset_timeout_seconds=30)
        >>> async def fetch_data(url):
        ...     return await httpx.get(url)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        breaker_name = name or func.__name__
        breaker = CircuitBreaker(
            name=breaker_name,
            failure_threshold=failure_threshold,
            reset_timeout_seconds=reset_timeout_seconds,
            max_delay_seconds=max_delay_seconds,
        )

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await breaker.call_with_retry(func, *args, **kwargs)

        # Attach circuit breaker to function for inspection
        wrapper._circuit_breaker = breaker  # type: ignore
        return wrapper

    return decorator
