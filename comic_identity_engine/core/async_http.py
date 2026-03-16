"""Async HTTP executor that routes requests through task queue.

This module provides the AsyncHttpExecutor class which executes HTTP requests
by enqueuing them as tasks in the arq job queue for maximum parallelism.

USAGE:
    executor = AsyncHttpExecutor(queue, operations_manager)
    result = await executor.get("gcd", "https://...")
    # result = {"status_code": 200, "content": "...", "elapsed_ms": 123}
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from comic_identity_engine.database.connection import AsyncSessionLocal
from comic_identity_engine.jobs.queue import JobQueue
from comic_identity_engine.services.operations import OperationsManager

logger = structlog.get_logger(__name__)


class AsyncHttpExecutor:
    """Execute HTTP requests via task queue for maximum parallelism.

    This class wraps HTTP request execution through the arq task queue,
    allowing all workers to process requests in parallel instead of being
    blocked on synchronous HTTP calls.

    Attributes:
        queue: JobQueue instance for enqueueing HTTP request tasks
        operations_manager: OperationsManager for tracking request operations
    """

    def __init__(self, queue: JobQueue, operations_manager: OperationsManager):
        """Initialize async HTTP executor.

        Args:
            queue: JobQueue instance for enqueuing HTTP request tasks
            operations_manager: OperationsManager for tracking operations
        """
        self.queue = queue
        self.operations_manager = operations_manager

    async def get(
        self,
        platform: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """Execute GET request via task queue.

        This method:
        1. Creates an operation to track the HTTP request
        2. Enqueues an http_request_task
        3. Polls for completion
        4. Returns the response data

        Args:
            platform: Platform code (e.g., "gcd", "locg", "ccl", "aa", "cpg", "hip")
            url: URL to request
            headers: Optional HTTP headers
            params: Optional query parameters
            timeout: Max wait time in seconds (default: 30)

        Returns:
            Response dict with keys:
                - url: str - The requested URL
                - status_code: int - HTTP status code
                - content: str - Response body text
                - elapsed_ms: int - Request duration in milliseconds
                - success: bool - True if 2xx status code
                - error: str | None - Error message if failed

        Raises:
            TimeoutError: If request doesn't complete within timeout seconds
            Exception: If HTTP request fails
        """
        async with AsyncSessionLocal() as session:
            operations_manager = OperationsManager(session)

            operation = await operations_manager.create_operation(
                operation_type="http_request",
                input_data={"platform": platform, "url": url, "method": "GET"},
            )
            await session.commit()

            logger.debug(
                "Enqueueing HTTP GET request",
                operation_id=str(operation.id),
                platform=platform,
                url=url,
            )

            job = await self.queue.enqueue_http_request(
                url=url,
                method="GET",
                operation_id=operation.id,
                platform=platform,
                headers=headers,
                params=params,
                verify_ssl=platform != "ccl",
            )

            logger.debug(
                "HTTP GET request enqueued",
                operation_id=str(operation.id),
                job_id=str(job.job_id),
            )

            start_time = time.time()
            poll_interval = 0.1

            while time.time() - start_time < timeout:
                result_op = await operations_manager.get_operation(operation.id)

                if result_op is not None and result_op.status in ("completed", "failed"):
                    if result_op.result:
                        return result_op.result
                    elif result_op.error_message:
                        raise Exception(result_op.error_message)
                    else:
                        raise Exception(f"HTTP request failed: {result_op.status}")

                await asyncio.sleep(poll_interval)

            raise TimeoutError(f"HTTP request timeout after {timeout}s")

    async def post(
        self,
        platform: str,
        url: str,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """Execute POST request via task queue.

        Args:
            platform: Platform code
            url: URL to request
            json_data: Request body as dict
            headers: Optional HTTP headers
            params: Optional query parameters
            timeout: Max wait time in seconds

        Returns:
            Response dict (same format as get())
        """
        async with AsyncSessionLocal() as session:
            operations_manager = OperationsManager(session)

            operation = await operations_manager.create_operation(
                operation_type="http_request",
                input_data={"platform": platform, "url": url, "method": "POST"},
            )
            await session.commit()

            logger.debug(
                "Enqueueing HTTP POST request",
                operation_id=str(operation.id),
                platform=platform,
                url=url,
            )

            await self.queue.enqueue_http_request(
                url=url,
                method="POST",
                operation_id=operation.id,
                platform=platform,
                headers=headers,
                params=params,
                json_data=json_data,
                verify_ssl=platform != "ccl",
            )

            start_time = time.time()
            poll_interval = 0.1

            while time.time() - start_time < timeout:
                result_op = await operations_manager.get_operation(operation.id)

                if result_op is not None and result_op.status in ("completed", "failed"):
                    if result_op.result:
                        return result_op.result
                    elif result_op.error_message:
                        raise Exception(result_op.error_message)
                    else:
                        raise Exception(f"HTTP request failed: {result_op.status}")

                await asyncio.sleep(poll_interval)

            raise TimeoutError(f"HTTP request timeout after {timeout}s")
