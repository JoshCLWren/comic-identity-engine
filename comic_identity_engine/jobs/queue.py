"""Queue management for enqueueing background jobs.

This module provides the JobQueue class for enqueueing jobs to the arq
job queue, including identity resolution, imports, exports, and reconciliation.

USAGE:
    from comic_identity_engine.jobs.queue import JobQueue

    queue = JobQueue()
    job = await queue.enqueue_resolve("https://...", operation_id)
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog
from arq import create_pool
from arq.connections import RedisSettings as ArqRedisSettings
from arq.jobs import Job

from comic_identity_engine.config import get_settings

logger = structlog.get_logger(__name__)


class JobQueue:
    """Queue manager for enqueueing background jobs.

    This class provides methods to enqueue various types of jobs to the arq
    job queue, handling Redis connections and error handling.

    Attributes:
        _redis_pool: Redis connection pool (created on first use)
        _redis_settings: Redis connection settings
    """

    def __init__(self) -> None:
        """Initialize the job queue manager."""
        self._redis_pool: Any | None = None
        self._redis_init_lock = asyncio.Lock()
        settings = get_settings()
        self._redis_settings = ArqRedisSettings.from_dsn(settings.arq.queue_url)
        self._queue_name = settings.arq.arq_queue_name

    async def _get_pool(self) -> Any:
        """Get or create the Redis connection pool.

        Returns:
            Redis connection pool.

        Raises:
            ConnectionError: If unable to connect to Redis.
        """
        if self._redis_pool is None:
            async with self._redis_init_lock:
                if self._redis_pool is None:
                    try:
                        self._redis_pool = await create_pool(
                            self._redis_settings,
                            default_queue_name=self._queue_name,
                        )
                        logger.debug(
                            "Created Redis connection pool for job queue",
                            queue_name=self._queue_name,
                        )
                    except (ConnectionError, TimeoutError, OSError) as e:
                        logger.error("Failed to connect to Redis", error=str(e))
                        raise ConnectionError(f"Failed to connect to Redis: {e}") from e
        return self._redis_pool

    async def enqueue_resolve(
        self,
        url: str,
        operation_id: uuid.UUID,
        force: bool = False,
        clear_mappings: str | None = None,
        dry_run: bool = False,
    ) -> Job:
        """Enqueue an identity resolution job.

        Args:
            url: URL to resolve (e.g., GCD, LoCG, etc.)
            operation_id: UUID of the operation tracking this job
            force: Skip existing mapping cache and always fetch from platform
            clear_mappings: Delete all external mappings for this source_issue_id before searching
            dry_run: Show what would happen without executing

        Returns:
            arq Job instance.

        Raises:
            ConnectionError: If unable to connect to Redis.

        Examples:
            >>> job = await queue.enqueue_resolve(
            ...     "https://www.comics.org/issue/123/",
            ...     operation_id
            ... )
            >>> print(job.job_id)
        """
        pool = await self._get_pool()

        logger.info(
            "Enqueueing identity resolution job",
            url=url,
            operation_id=str(operation_id),
            force=force,
            clear_mappings=clear_mappings,
            dry_run=dry_run,
        )

        return await pool.enqueue_job(
            "resolve_identity_task",
            url=url,
            operation_id=str(operation_id),
            force=force,
            clear_mappings=clear_mappings,
            dry_run=dry_run,
        )

    async def enqueue_bulk_resolve(
        self,
        urls: list[str],
        operation_id: uuid.UUID,
    ) -> Job:
        """Enqueue a bulk identity resolution job.

        Args:
            urls: List of URLs to resolve
            operation_id: UUID of the operation tracking this job

        Returns:
            arq Job instance.

        Raises:
            ConnectionError: If unable to connect to Redis.

        Examples:
            >>> urls = ["https://...", "https://..."]
            >>> job = await queue.enqueue_bulk_resolve(urls, operation_id)
        """
        pool = await self._get_pool()

        logger.info(
            "Enqueueing bulk identity resolution job",
            url_count=len(urls),
            operation_id=str(operation_id),
        )

        return await pool.enqueue_job(
            "bulk_resolve_task",
            urls=urls,
            operation_id=str(operation_id),
        )

    async def enqueue_import_clz(
        self,
        csv_path: str,
        operation_id: uuid.UUID,
    ) -> Job:
        """Enqueue a CLZ CSV import job.

        Args:
            csv_path: Path to the CLZ CSV file to import
            operation_id: UUID of the operation tracking this job

        Returns:
            arq Job instance.

        Raises:
            ConnectionError: If unable to connect to Redis.

        Examples:
            >>> job = await queue.enqueue_import_clz(
            ...     "/path/to/collection.csv",
            ...     operation_id
            ... )
        """
        pool = await self._get_pool()

        logger.info(
            "Enqueueing CLZ CSV import job",
            csv_path=csv_path,
            operation_id=str(operation_id),
        )

        return await pool.enqueue_job(
            "import_clz_task",
            csv_path=csv_path,
            operation_id=str(operation_id),
        )

    async def enqueue_export(
        self,
        issue_ids: list[uuid.UUID],
        format: str,
        operation_id: uuid.UUID,
    ) -> Job:
        """Enqueue an export job.

        Args:
            issue_ids: List of issue UUIDs to export
            format: Export format (e.g., "csv", "json")
            operation_id: UUID of the operation tracking this job

        Returns:
            arq Job instance.

        Raises:
            ConnectionError: If unable to connect to Redis.

        Examples:
            >>> issue_ids = [uuid.uuid4(), uuid.uuid4()]
            >>> job = await queue.enqueue_export(issue_ids, "csv", operation_id)
        """
        pool = await self._get_pool()

        logger.info(
            "Enqueueing export job",
            issue_count=len(issue_ids),
            format=format,
            operation_id=str(operation_id),
        )

        issue_id_strs = [str(issue_id) for issue_id in issue_ids]

        return await pool.enqueue_job(
            "export_task",
            issue_ids=issue_id_strs,
            format=format,
            operation_id=str(operation_id),
        )

    async def enqueue_reconcile(
        self,
        issue_id: uuid.UUID,
        operation_id: uuid.UUID,
    ) -> Job:
        """Enqueue a reconciliation job for an issue.

        Args:
            issue_id: UUID of the issue to reconcile
            operation_id: UUID of the operation tracking this job

        Returns:
            arq Job instance.

        Raises:
            ConnectionError: If unable to connect to Redis.

        Examples:
            >>> job = await queue.enqueue_reconcile(issue_id, operation_id)
        """
        pool = await self._get_pool()

        logger.info(
            "Enqueueing reconciliation job",
            issue_id=str(issue_id),
            operation_id=str(operation_id),
        )

        return await pool.enqueue_job(
            "reconcile_task",
            issue_id=str(issue_id),
            operation_id=str(operation_id),
        )

    async def enqueue_resolve_clz_row(
        self,
        row_data: dict[str, str],
        row_index: int,
        operation_id: uuid.UUID,
    ) -> Job:
        """Enqueue a CLZ CSV row resolution job.

        Args:
            row_data: Single CSV row as dictionary
            row_index: Row index (1-based) for error reporting
            operation_id: UUID of the parent import operation

        Returns:
            arq Job instance.

        Raises:
            ConnectionError: If unable to connect to Redis.

        Examples:
            >>> job = await queue.enqueue_resolve_clz_row(
            ...     {"Core ComicID": "123", "Series": "X-Men"},
            ...     1,
            ...     operation_id
            ... )
        """
        pool = await self._get_pool()

        logger.info(
            "Enqueueing CLZ row resolution job",
            row_index=row_index,
            source_issue_id=row_data.get("Core ComicID"),
            operation_id=str(operation_id),
        )

        return await pool.enqueue_job(
            "resolve_clz_row_task",
            row_data=row_data,
            row_index=row_index,
            operation_id=str(operation_id),
        )

    async def enqueue_http_request(
        self,
        url: str,
        method: str = "GET",
        operation_id: uuid.UUID | None = None,
        platform: str | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        verify_ssl: bool = True,
    ) -> Job:
        """Enqueue an HTTP request job.

        This method enqueues a single HTTP request as an independent task,
        allowing for fine-grained parallelism and error handling.

        Args:
            url: URL to request
            method: HTTP method (default: "GET")
            operation_id: UUID of the operation tracking this job (auto-generated if not provided)
            platform: Platform identifier for rate limiting (optional)
            headers: Optional HTTP headers
            params: Optional query parameters
            json_data: Optional JSON body for POST/PUT/PATCH requests
            verify_ssl: Whether to verify SSL certificates (default: True)

        Returns:
            arq Job instance.

        Raises:
            ConnectionError: If unable to connect to Redis.

        Examples:
            >>> job = await queue.enqueue_http_request(
            ...     "https://www.comics.org/issue/123/?format=json"
            ... )
            >>> print(job.job_id)
        """
        pool = await self._get_pool()

        op_id = operation_id or uuid.uuid4()

        logger.info(
            "Enqueueing HTTP request job",
            url=url,
            method=method,
            operation_id=str(op_id),
            platform=platform,
            verify_ssl=verify_ssl,
        )

        return await pool.enqueue_job(
            "http_request_task",
            url=url,
            method=method,
            operation_id=str(op_id),
            platform=platform,
            headers=headers,
            params=params,
            json_data=json_data,
            verify_ssl=verify_ssl,
        )

    async def get_queue_depth(
        self,
        *,
        operation_id: uuid.UUID | None = None,
    ) -> int:
        """Return queued job depth, optionally scoped to a specific operation.

        Returns 0 if queue is empty or if jobs race with completion during inspection.
        """
        try:
            pool = await self._get_pool()
            queued_jobs = await pool.queued_jobs(queue_name=self._queue_name)

            if operation_id is None:
                return len(queued_jobs)

            operation_id_str = str(operation_id)
            return sum(
                1
                for job in queued_jobs
                if getattr(job, "kwargs", {}).get("operation_id") == operation_id_str
            )
        except RuntimeError:
            # Jobs were processed while we were inspecting the queue
            # This is a race condition, not an error
            return 0

    async def close(self) -> None:
        """Close the Redis connection pool.

        This should be called when the application shuts down to properly
        clean up resources.
        """
        if self._redis_pool is not None:
            close = getattr(self._redis_pool, "close", None)
            if callable(close):
                await self._redis_pool.close()
            else:
                aclose = getattr(self._redis_pool, "aclose", None)
                if callable(aclose):
                    await aclose()
            self._redis_pool = None
            logger.debug("Closed Redis connection pool")

    async def __aenter__(self) -> JobQueue:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()
