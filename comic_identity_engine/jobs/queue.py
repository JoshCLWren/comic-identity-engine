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
                        self._redis_pool = await create_pool(self._redis_settings)
                        logger.debug("Created Redis connection pool for job queue")
                    except (ConnectionError, TimeoutError, OSError) as e:
                        logger.error("Failed to connect to Redis", error=str(e))
                        raise ConnectionError(f"Failed to connect to Redis: {e}") from e
        return self._redis_pool

    async def enqueue_resolve(
        self,
        url: str,
        operation_id: uuid.UUID,
    ) -> Job:
        """Enqueue an identity resolution job.

        Args:
            url: URL to resolve (e.g., GCD, LoCG, etc.)
            operation_id: UUID of the operation tracking this job

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
        )

        return await pool.enqueue_job(
            "resolve_identity_task",
            url=url,
            operation_id=str(operation_id),
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

    async def close(self) -> None:
        """Close the Redis connection pool.

        This should be called when the application shuts down to properly
        clean up resources.
        """
        if self._redis_pool is not None:
            await self._redis_pool.close()
            self._redis_pool = None
            logger.debug("Closed Redis connection pool")

    async def __aenter__(self) -> JobQueue:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()
