"""FastAPI dependencies for the Comic Identity Engine HTTP API.

This module provides dependency injection functions for FastAPI endpoints,
including database sessions, job queue, operations manager, and identity resolver.

USAGE:
    from fastapi import Depends
    from comic_identity_engine.api.dependencies import get_db, get_job_queue

    @app.get("/issues/{issue_id}")
    async def get_issue(
        issue_id: uuid.UUID,
        db: AsyncSession = Depends(get_db),
        queue: JobQueue = Depends(get_job_queue),
    ):
        ...
"""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from comic_identity_engine.database.connection import get_db
from comic_identity_engine.jobs.queue import JobQueue
from comic_identity_engine.services.identity_resolver import IdentityResolver
from comic_identity_engine.services.operations import OperationsManager


# Re-export get_db for convenience
__all__ = ["get_db", "get_job_queue", "get_operations_manager", "get_identity_resolver"]


async def get_job_queue() -> AsyncGenerator[JobQueue, None]:
    """Get the JobQueue instance for enqueueing background jobs.

    Returns:
        JobQueue instance for managing background job queue.

    Example:
        @app.post("/resolve")
        async def resolve_url(
            url: str,
            queue: JobQueue = Depends(get_job_queue),
        ):
            job = await queue.enqueue_resolve(url, operation_id)
            return {"job_id": job.job_id}
    """
    queue = JobQueue()
    try:
        yield queue
    finally:
        await queue.close()


async def get_operations_manager(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OperationsManager:
    """Get the OperationsManager instance for tracking async operations.

    Args:
        db: Database session from get_db dependency.

    Returns:
        OperationsManager instance for managing long-running operations.

    Example:
        @app.post("/operations")
        async def create_op(
            manager: OperationsManager = Depends(get_operations_manager),
        ):
            operation = await manager.create_operation("resolve", {"url": "..."})
            return {"operation_id": operation.id}
    """
    return OperationsManager(db)


async def get_identity_resolver(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IdentityResolver:
    """Get the IdentityResolver instance for cross-platform matching.

    Args:
        db: Database session from get_db dependency.

    Returns:
        IdentityResolver instance for resolving comic identities.

    Example:
        @app.post("/resolve")
        async def resolve(
            parsed_url: ParsedUrl,
            resolver: IdentityResolver = Depends(get_identity_resolver),
        ):
            result = await resolver.resolve_issue(parsed_url)
            return {"issue_id": result.issue_id}
    """
    return IdentityResolver(db)
