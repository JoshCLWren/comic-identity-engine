"""Jobs management router for Comic Identity Engine HTTP API.

This module provides FastAPI endpoints for managing background jobs including:
- Bulk identity resolution
- CLZ CSV imports
- Job status monitoring
- Result retrieval and export

All endpoints follow AIP-151 for long-running operations.

USAGE:
    from comic_identity_engine.api.main import create_app
    from comic_identity_engine.api.routers.jobs import router as jobs_router

    app = create_app()
    app.include_router(jobs_router)
"""

import os
import tempfile
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from comic_identity_engine.api.dependencies import (
    get_db,
    get_job_queue,
    get_operations_manager,
)
from comic_identity_engine.api.schemas import (
    BulkResolveRequest,
    JobStatusResponse,
    OperationResponse,
)

from comic_identity_engine.jobs.queue import JobQueue
from comic_identity_engine.services.operations import OperationsManager

router = APIRouter(prefix="/jobs", tags=["Job Management"])


@router.post(
    "/bulk-resolve",
    response_model=OperationResponse,
    status_code=202,
    summary="Enqueue bulk identity resolution",
    description="Enqueue a job to resolve multiple comic URLs in bulk.",
)
async def create_bulk_resolve_job(
    request: BulkResolveRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    queue: Annotated[JobQueue, Depends(get_job_queue)],
) -> OperationResponse:
    """Enqueue a bulk identity resolution job.

    Args:
        request: BulkResolveRequest containing list of URLs to resolve
        db: Database session
        queue: Job queue for enqueueing background jobs

    Returns:
        OperationResponse with operation ID and status

    Raises:
        HTTPException: If enqueueing fails
    """
    operations_manager = OperationsManager(db)

    operation = await operations_manager.create_operation(
        operation_type="bulk_resolve",
        input_data={"urls": request.urls},
    )

    await queue.enqueue_bulk_resolve(
        urls=request.urls,
        operation_id=operation.id,
    )

    return OperationResponse(
        name=f"operations/{operation.id}",
        done=False,
        metadata={
            "total_urls": len(request.urls),
            "processed_urls": 0,
        },
    )


@router.post(
    "/import-clz",
    response_model=OperationResponse,
    status_code=202,
    summary="Enqueue CLZ CSV import",
    description="Upload and enqueue a CLZ collection CSV file for import.",
)
async def create_import_clz_job(
    file: Annotated[UploadFile, File(description="CLZ collection CSV file")],
    db: Annotated[AsyncSession, Depends(get_db)],
    queue: Annotated[JobQueue, Depends(get_job_queue)],
) -> OperationResponse:
    """Enqueue a CLZ CSV import job.

    Args:
        file: Uploaded CLZ collection CSV file
        db: Database session
        queue: Job queue for enqueueing background jobs

    Returns:
        OperationResponse with operation ID and status

    Raises:
        HTTPException: If file upload or enqueueing fails
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=422,
            detail="Invalid file type. Only CSV files are supported.",
        )

    temp_file_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".csv",
            delete=False,
            prefix="clz_import_",
        ) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = Path(temp_file.name)

        operations_manager = OperationsManager(db)

        operation = await operations_manager.create_operation(
            operation_type="import_clz",
            input_data={"filename": file.filename},
            # Import retries for the same file should create fresh work instead
            # of reusing a stale operation record.
            force=True,
        )

        await queue.enqueue_import_clz(
            csv_path=str(temp_file_path),
            operation_id=operation.id,
        )

        return OperationResponse(
            name=f"operations/{operation.id}",
            done=False,
            metadata={
                "filename": file.filename,
                "file_size": len(content),
            },
        )

    except Exception as e:
        if temp_file_path and temp_file_path.exists():
            os.unlink(temp_file_path)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to enqueue import job: {e}",
        ) from e


@router.get(
    "/{operation_id}",
    response_model=JobStatusResponse,
    summary="Get job status",
    description="Get the current status of a background job.",
)
async def get_job_status(
    operation_id: uuid.UUID,
    operations_manager: Annotated[OperationsManager, Depends(get_operations_manager)],
) -> JobStatusResponse:
    """Get the status of a background job.

    Args:
        operation_id: UUID of the operation to check
        operations_manager: Operations manager for querying operation status

    Returns:
        JobStatusResponse with current status and progress

    Raises:
        HTTPException: 404 if operation not found
    """
    operation = await operations_manager.get_operation(operation_id)

    if operation is None:
        raise HTTPException(
            status_code=404,
            detail=f"Operation not found: {operation_id}",
        )

    progress = None
    if operation.result and isinstance(operation.result, dict):
        if "progress" in operation.result:
            progress = operation.result["progress"]
        elif "total" in operation.result and "completed" in operation.result:
            total = operation.result["total"]
            completed = operation.result["completed"]
            if total > 0:
                progress = completed / total
        elif "total_rows" in operation.result and "processed" in operation.result:
            total_rows = operation.result["total_rows"]
            processed = operation.result["processed"]
            if total_rows > 0:
                progress = processed / total_rows

    return JobStatusResponse(
        operation_id=operation.id,
        status=operation.status,
        progress=progress,
        created_at=operation.created_at,
        updated_at=operation.updated_at,
    )


@router.get(
    "/{operation_id}/result",
    summary="Get job result",
    description="Get the result of a completed background job.",
)
async def get_job_result(
    operation_id: uuid.UUID,
    operations_manager: Annotated[OperationsManager, Depends(get_operations_manager)],
) -> JSONResponse:
    """Get the result of a completed background job.

    Args:
        operation_id: UUID of the operation to get results for
        operations_manager: Operations manager for querying operation status

    Returns:
        JSONResponse with operation result data

    Raises:
        HTTPException:
            404 if operation not found
            409 if operation is not yet complete
    """
    operation = await operations_manager.get_operation(operation_id)

    if operation is None:
        raise HTTPException(
            status_code=404,
            detail=f"Operation not found: {operation_id}",
        )

    if operation.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Operation not complete. Current status: {operation.status}",
        )

    return JSONResponse(
        status_code=200,
        content=operation.result or {},
    )


@router.get(
    "/{operation_id}/export",
    summary="Download export file",
    description="Download the export file for a completed export job.",
)
async def download_export(
    operation_id: uuid.UUID,
    operations_manager: Annotated[OperationsManager, Depends(get_operations_manager)],
) -> FileResponse:
    """Download the export file for a completed export job.

    Args:
        operation_id: UUID of the export operation
        operations_manager: Operations manager for querying operation status

    Returns:
        FileResponse with the export file

    Raises:
        HTTPException:
            404 if operation not found
            409 if operation is not yet complete
            400 if operation is not an export or file not available
    """
    operation = await operations_manager.get_operation(operation_id)

    if operation is None:
        raise HTTPException(
            status_code=404,
            detail=f"Operation not found: {operation_id}",
        )

    if operation.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Operation not complete. Current status: {operation.status}",
        )

    if operation.operation_type != "export":
        raise HTTPException(
            status_code=422,
            detail="Operation is not an export job",
        )

    if not operation.result or not isinstance(operation.result, dict):
        raise HTTPException(
            status_code=422,
            detail="Export result not available",
        )

    file_path = operation.result.get("file_path")
    if not file_path:
        raise HTTPException(
            status_code=422,
            detail="Export file path not found in result",
        )

    path = Path(file_path)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Export file not found",
        )

    export_format = operation.result.get("format", "json")
    media_type = "text/csv" if export_format == "csv" else "application/json"
    filename = f"export_{operation_id}.{export_format}"

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
    )
