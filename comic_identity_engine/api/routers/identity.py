"""Identity resolution router for Comic Identity Engine HTTP API.

This module provides endpoints for resolving comic identities from URLs,
following AIP-151 for long-running operations.

USAGE:
    from comic_identity_engine.api.main import create_app
    from comic_identity_engine.api.routers import identity

    app = create_app()
    app.include_router(identity.router)
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from comic_identity_engine.api.dependencies import (
    get_job_queue,
    get_operations_manager,
)
from comic_identity_engine.api.schemas import (
    OperationResponse,
    ResolveIdentityRequest,
)
from comic_identity_engine.errors import (
    AdapterError,
    ParseError,
    ValidationError,
)
from comic_identity_engine.jobs.queue import JobQueue
from comic_identity_engine.services.operations import OperationsManager

router = APIRouter(prefix="/identity", tags=["Identity Resolution"])


@router.post(
    "/resolve",
    response_model=OperationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Resolve identity from URL",
    description="Enqueue an identity resolution job for the given URL. Returns an operation ID for polling.",
    responses={
        400: {"description": "Validation error"},
        422: {"description": "Parse error"},
        500: {"description": "Adapter error"},
    },
)
async def resolve_identity(
    request: ResolveIdentityRequest,
    queue: Annotated[JobQueue, Depends(get_job_queue)],
    operations_manager: Annotated[OperationsManager, Depends(get_operations_manager)],
) -> OperationResponse:
    """Resolve a comic identity from a URL.

    This endpoint enqueues a background job to resolve the identity
    and returns immediately with an operation ID for polling status.

    Args:
        request: Resolution request containing the URL
        queue: Job queue dependency for enqueueing jobs
        operations_manager: Operations manager for tracking operation

    Returns:
        OperationResponse with operation name for polling

    Raises:
        HTTPException: 400 for validation errors, 422 for parse errors,
            500 for adapter errors
    """
    try:
        operation = await operations_manager.create_operation(
            operation_type="resolve",
            input_data={"url": request.url},
        )

        # Only enqueue job if operation is not already completed
        if operation.status not in ("completed", "failed"):
            await queue.enqueue_resolve(
                url=request.url,
                operation_id=operation.id,
            )

        # Return operation response with correct done status
        is_done = operation.status in ("completed", "failed")

        return OperationResponse(
            name=f"operations/{operation.id}",
            done=is_done,
            metadata={
                "operation_type": "resolve",
                "url": request.url,
                "status": operation.status,
            },
        )

    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_ERROR",
                "message": str(e),
            },
        ) from e

    except ParseError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "PARSE_ERROR",
                "message": str(e),
            },
        ) from e

    except AdapterError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "ADAPTER_ERROR",
                "message": str(e),
                "source": e.source,
            },
        ) from e


@router.get(
    "/resolve/{operation_id}",
    response_model=OperationResponse,
    summary="Get identity resolution status",
    description="Get the status of an identity resolution operation by ID.",
    responses={
        404: {"description": "Operation not found"},
    },
)
async def get_resolve_status(
    operation_id: UUID,
    operations_manager: Annotated[OperationsManager, Depends(get_operations_manager)],
) -> OperationResponse:
    """Get the status of an identity resolution operation.

    Args:
        operation_id: UUID of the operation to check
        operations_manager: Operations manager for retrieving operation

    Returns:
        OperationResponse with done status and result/error if completed

    Raises:
        HTTPException: 404 if operation not found
    """
    operation = await operations_manager.get_operation(operation_id)

    if operation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "OPERATION_NOT_FOUND",
                "message": f"Operation not found: {operation_id}",
            },
        )

    is_done = operation.status in ("completed", "failed")

    response: OperationResponse = OperationResponse(
        name=f"operations/{operation.id}",
        done=is_done,
        metadata={
            "operation_type": operation.operation_type,
            "status": operation.status,
            "created_at": operation.created_at.isoformat()
            if operation.created_at
            else None,
            "updated_at": operation.updated_at.isoformat()
            if operation.updated_at
            else None,
        },
    )

    if is_done and operation.status == "completed" and operation.result:
        response.response = operation.result

    if operation.status == "failed" and operation.error_message:
        error_code = 3
        if "parse" in operation.error_message.lower():
            error_code = 3
        elif "resolution" in operation.error_message.lower():
            error_code = 3
        elif "validation" in operation.error_message.lower():
            error_code = 3

        response.error = {
            "code": error_code,
            "message": operation.error_message,
            "details": [],
        }

    return response
