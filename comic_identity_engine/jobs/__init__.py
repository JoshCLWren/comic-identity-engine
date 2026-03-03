"""Job queue infrastructure for background processing.

This module provides the arq-based job queue infrastructure for Comic Identity
Engine, including worker configuration and job enqueueing.

USAGE:
    from comic_identity_engine.jobs import JobQueue, WorkerSettings

    # Enqueue jobs
    queue = JobQueue()
    job = await queue.enqueue_resolve("https://...", operation_id)

    # Run worker
    cie-worker
"""

from comic_identity_engine.jobs.queue import JobQueue
from comic_identity_engine.jobs.tasks import (
    bulk_resolve_task,
    export_task,
    import_clz_task,
    reconcile_task,
    resolve_identity_task,
)
from comic_identity_engine.jobs.worker import WorkerSettings, create_redis_pool

__all__ = [
    "JobQueue",
    "WorkerSettings",
    "create_redis_pool",
    "resolve_identity_task",
    "bulk_resolve_task",
    "import_clz_task",
    "export_task",
    "reconcile_task",
]
