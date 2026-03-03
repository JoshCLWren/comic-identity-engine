"""arq worker configuration for background job processing.

This module provides the arq worker setup for processing background jobs
including identity resolution, imports, exports, and reconciliation.

USAGE:
    # Start the worker
    python -m comic_identity_engine.jobs.worker

    # Or use the CLI
    cie-worker
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from arq import create_pool
from arq.connections import RedisSettings as ArqRedisSettings
from arq.worker import Worker

from comic_identity_engine.config import get_settings

logger = structlog.get_logger(__name__)


async def create_redis_pool() -> Any:
    """Create a Redis connection pool for arq.

    Returns:
        Redis pool connection for arq operations.

    Examples:
        >>> redis = await create_redis_pool()
        >>> # Use with arq
    """
    settings = get_settings()
    redis_settings = ArqRedisSettings.from_dsn(settings.arq.queue_url)
    return await create_pool(redis_settings)


class WorkerSettings:
    """arq worker configuration settings.

    This class defines the configuration for the arq worker including
    Redis connection, job timeouts, concurrency limits, and registered
    task functions.

    Attributes:
        redis_settings: Redis connection settings
        max_jobs: Maximum concurrent jobs
        job_timeout: Default job timeout in seconds
        keep_result: How long to keep job results
        functions: List of registered task functions
    """

    def __init__(self) -> None:
        """Initialize worker settings from configuration."""
        settings = get_settings()
        self.redis_settings = ArqRedisSettings.from_dsn(settings.arq.queue_url)
        self.max_jobs = settings.arq.arq_max_jobs
        self.job_timeout = settings.arq.arq_job_timeout
        self.keep_result = settings.arq.arq_keep_result
        self.functions: list[Any] = self._get_task_functions()

    def _get_task_functions(self) -> list[Any]:
        """Get the list of task functions to register with the worker.

        Returns:
            List of task function coroutines.
        """
        try:
            from comic_identity_engine.jobs.tasks import (
                resolve_identity_task,
                bulk_resolve_task,
                import_clz_task,
                export_task,
                reconcile_task,
            )

            return [
                resolve_identity_task,
                bulk_resolve_task,
                import_clz_task,
                export_task,
                reconcile_task,
            ]
        except ImportError:
            logger.warning(
                "Task functions not yet implemented, starting with empty function list"
            )
            return []


def create_worker(settings: WorkerSettings | None = None) -> Worker:
    """Create an arq worker instance.

    Args:
        settings: Optional WorkerSettings instance (uses defaults if not provided)

    Returns:
        Configured arq Worker instance.

    Examples:
        >>> worker = create_worker()
        >>> # Run the worker
    """
    if settings is None:
        settings = WorkerSettings()

    return Worker(
        redis_settings=settings.redis_settings,
        max_jobs=settings.max_jobs,
        job_timeout=settings.job_timeout,
        keep_result=settings.keep_result,
        functions=settings.functions,
    )


async def run_worker() -> None:
    """Run the arq worker.

    This function starts the worker and runs until interrupted.
    """
    settings = WorkerSettings()
    worker = create_worker(settings)

    logger.info(
        "Starting arq worker",
        redis_url=settings.redis_settings.host,
        max_jobs=settings.max_jobs,
        job_timeout=settings.job_timeout,
        functions_count=len(settings.functions),
    )

    await worker.async_run()


def main() -> None:
    """Entry point for running the worker.

    This function is called by the cie-worker CLI command.
    """
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error("Worker failed", error=str(e))
        raise


if __name__ == "__main__":
    main()
