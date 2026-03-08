"""Import router for Comic Identity Engine HTTP API.

This module provides endpoints for importing comic collections from CSV files,
following AIP-151 for long-running operations.

USAGE:
    from comic_identity_engine.api.main import create_app
    from comic_identity_engine.api.routers import import_router

    app = create_app()
    app.include_router(import_router)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from comic_identity_engine.api.dependencies import (
    get_job_queue,
    get_operations_manager,
)
from comic_identity_engine.api.schemas import (
    ImportClzRequest,
    OperationResponse,
)
from comic_identity_engine.errors import ValidationError
from comic_identity_engine.jobs.queue import JobQueue
from comic_identity_engine.services.imports import prepare_clz_import_from_path
from comic_identity_engine.services.operations import OperationsManager

router = APIRouter(prefix="/import", tags=["Import"])


@router.post(
    "/clz",
    response_model=OperationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Import CLZ collection CSV",
    description="Enqueue a CLZ CSV import job. Returns an operation ID for polling.",
    responses={
        400: {"description": "Validation error"},
        500: {"description": "Server error"},
    },
)
async def import_clz(
    request: ImportClzRequest,
    queue: Annotated[JobQueue, Depends(get_job_queue)],
    operations_manager: Annotated[OperationsManager, Depends(get_operations_manager)],
) -> OperationResponse:
    """Import comic data from a CLZ CSV export file.

    This endpoint enqueues a background job to import CLZ CSV data
    and returns immediately with an operation ID for polling status.

    Args:
        request: Import request containing the CSV file path
        queue: Job queue dependency for enqueueing jobs
        operations_manager: Operations manager for tracking operation

    Returns:
        OperationResponse with operation name for polling

    Raises:
        HTTPException: 400 for validation errors, 500 for server errors
    """
    try:
        prepared_import = prepare_clz_import_from_path(request.file_path)
        (
            operation,
            should_enqueue,
        ) = await operations_manager.create_or_resume_import_operation(
            operation_type="import_clz",
            file_checksum=prepared_import.file_checksum,
            initial_result=prepared_import.to_operation_result(),
        )

        if should_enqueue:
            await queue.enqueue_import_clz(
                csv_path=request.file_path,
                operation_id=operation.id,
            )

        is_done = operation.status in ("completed", "failed")

        return OperationResponse(
            name=f"operations/{operation.id}",
            done=is_done,
            metadata={
                "operation_type": "import_clz",
                "csv_path": request.file_path,
                "file_checksum": prepared_import.file_checksum,
                "file_size": prepared_import.file_size,
                "total_rows": prepared_import.total_rows,
                "resume_count": (
                    operation.result.get("resume_count", 0)
                    if isinstance(operation.result, dict)
                    else 0
                ),
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


@router.get(
    "/clz/{operation_id}",
    response_model=OperationResponse,
    summary="Get CLZ import status",
    description="Get the status of a CLZ import operation by ID.",
    responses={
        404: {"description": "Operation not found"},
    },
)
async def get_import_clz_status(
    operation_id: str,
    operations_manager: Annotated[OperationsManager, Depends(get_operations_manager)],
) -> OperationResponse:
    """Get the status of a CLZ import operation.

    Args:
        operation_id: UUID of the operation to check
        operations_manager: Operations manager for retrieving operation

    Returns:
        OperationResponse with done status and result/error if completed

    Raises:
        HTTPException: 404 if operation not found
    """
    from uuid import UUID

    operation = await operations_manager.get_operation(UUID(operation_id))

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

    if isinstance(operation.result, dict):
        for key in ("file_checksum", "file_size", "total_rows", "resume_count"):
            if key in operation.result:
                response.metadata[key] = operation.result[key]

    if operation.result:
        response.response = operation.result

    if operation.status == "failed" and operation.error_message:
        error_code = 3
        response.error = {
            "code": error_code,
            "message": operation.error_message,
            "details": [],
        }

    return response
