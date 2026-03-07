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
import signal
import sys
from typing import Any

import structlog
from arq import create_pool
from arq.connections import RedisSettings as ArqRedisSettings
from arq.worker import Worker

from comic_identity_engine.config import get_settings
from comic_identity_engine.jobs.tasks import (
    bulk_resolve_task,
    export_task,
    import_clz_task,
    reconcile_task,
    resolve_identity_task,
)

logger = structlog.get_logger(__name__)

_received_signals = []


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

    # Class-level attributes required by arq CLI
    redis_settings = ArqRedisSettings.from_dsn(get_settings().arq.queue_url)
    max_jobs = get_settings().arq.arq_max_jobs
    job_timeout = get_settings().arq.arq_job_timeout
    keep_result = get_settings().arq.arq_keep_result
    functions = [
        resolve_identity_task,
        bulk_resolve_task,
        import_clz_task,
        export_task,
        reconcile_task,
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
        redis_settings=settings_cls.redis_settings,
        max_jobs=settings_cls.max_jobs,
        job_timeout=settings_cls.job_timeout,
        keep_result=settings_cls.keep_result,
        functions=settings_cls.functions,
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
        max_jobs=WorkerSettings.max_jobs,
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
    try:
        run_worker()
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except (RuntimeError, asyncio.CancelledError) as e:
        logger.error("Worker failed", error=str(e))
        raise


if __name__ == "__main__":
    main()
