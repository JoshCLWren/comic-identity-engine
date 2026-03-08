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
import logging
import signal
from typing import Any

import structlog
from arq import create_pool
from arq.connections import RedisSettings as ArqRedisSettings
from arq.worker import Worker

from comic_identity_engine.config import get_database_settings, get_settings
from comic_identity_engine.jobs.tasks import (
    bulk_resolve_task,
    export_task,
    http_request_task,
    import_clz_task,
    reconcile_task,
    resolve_clz_row_task,
    resolve_identity_task,
)


def _configure_logging() -> None:
    """Configure structlog for console output.

    This must be called before any loggers are created to ensure
    log messages appear in console output.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


logger = structlog.get_logger(__name__)

_received_signals = []


def cap_worker_max_jobs(configured_max_jobs: int, db_pool_capacity: int) -> int:
    """Cap worker concurrency so it cannot exceed DB pool capacity."""
    return min(configured_max_jobs, db_pool_capacity)


async def _on_worker_startup(ctx: dict[str, Any]) -> None:
    """Log when the arq worker has fully initialized and is ready for jobs."""
    logger.info(
        "Worker started successfully",
        queue_name=WorkerSettings.queue_name,
        max_jobs=WorkerSettings.max_jobs,
        configured_max_jobs=WorkerSettings.configured_max_jobs,
        db_pool_capacity=WorkerSettings.db_pool_capacity,
        job_timeout=WorkerSettings.job_timeout,
        functions_count=len(WorkerSettings.functions),
        redis_host=WorkerSettings.redis_settings.host,
    )


def _signal_handler(signum: int, frame) -> None:
    """Handle signals by logging them."""
    _received_signals.append(signum)
    logger.warning(
        "Received signal", signum=signum, signal_name=signal.Signals(signum).name
    )


def _setup_signal_handlers() -> None:
    """Set up signal handlers for debugging."""
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(sig, _signal_handler)
            logger.info("Registered signal handler", signal=signal.Signals(sig).name)
        except ValueError:
            pass


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
    return await create_pool(
        redis_settings,
        default_queue_name=settings.arq.arq_queue_name,
    )


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

    # Class-level attributes required by arq CLI
    _settings = get_settings()
    _database_settings = get_database_settings()
    redis_settings = ArqRedisSettings.from_dsn(_settings.arq.queue_url)
    queue_name = _settings.arq.arq_queue_name
    configured_max_jobs = _settings.arq.arq_max_jobs
    db_pool_capacity = _database_settings.pool_capacity
    max_jobs = cap_worker_max_jobs(configured_max_jobs, db_pool_capacity)
    job_timeout = _settings.arq.arq_job_timeout
    keep_result = _settings.arq.arq_keep_result
    functions = [
        resolve_identity_task,
        bulk_resolve_task,
        import_clz_task,
        resolve_clz_row_task,
        export_task,
        reconcile_task,
        http_request_task,
    ]


def create_worker(settings_cls: type[WorkerSettings] = WorkerSettings) -> Worker:
    """Create an arq worker instance.

    Args:
        settings_cls: WorkerSettings class to use (uses default if not provided)

    Returns:
        Configured arq Worker instance.

    Examples:
        >>> worker = create_worker()
        >>> # Run the worker
    """
    return Worker(
        queue_name=settings_cls.queue_name,
        redis_settings=settings_cls.redis_settings,
        max_jobs=settings_cls.max_jobs,
        job_timeout=settings_cls.job_timeout,
        keep_result=settings_cls.keep_result,
        functions=settings_cls.functions,
        on_startup=_on_worker_startup,
    )


def run_worker() -> None:
    """Run the arq worker.

    This function starts the worker and runs until interrupted.
    """
    _setup_signal_handlers()

    worker = create_worker()

    logger.info(
        "Starting arq worker",
        redis_url=WorkerSettings.redis_settings.host,
        queue_name=WorkerSettings.queue_name,
        max_jobs=WorkerSettings.max_jobs,
        configured_max_jobs=WorkerSettings.configured_max_jobs,
        db_pool_capacity=WorkerSettings.db_pool_capacity,
        job_timeout=WorkerSettings.job_timeout,
        functions_count=len(WorkerSettings.functions),
    )

    try:
        worker.run()
    except BaseException as e:
        logger.error(
            "Worker crashed",
            exception_type=type(e).__name__,
            exception_message=str(e),
            received_signals=_received_signals,
        )
        raise


def main() -> None:
    """Entry point for running the worker.

    This function is called by the cie-worker CLI command.
    """
    _configure_logging()

    try:
        run_worker()
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except (RuntimeError, asyncio.CancelledError) as e:
        logger.error("Worker failed", error=str(e))
        raise


if __name__ == "__main__":
    main()
