"""Import router for Comic Identity Engine HTTP API.

This module provides endpoints for importing comic collections from CSV files,
following AIP-151 for long-running operations.

USAGE:
    from comic_identity_engine.api.main import create_app
    from comic_identity_engine.api.routers import import_router

    app = create_app()
    app.include_router(import_router)
"""

import csv
import uuid
from pathlib import Path
from typing import Annotated, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from comic_identity_engine.api.dependencies import (
    get_job_queue,
    get_operations_manager,
)
from comic_identity_engine.api.schemas import (
    ImportClzRequest,
    OperationResponse,
)
from comic_identity_engine.database.connection import AsyncSessionLocal
from comic_identity_engine.database.repositories import ExternalMappingRepository
from comic_identity_engine.errors import ValidationError
from comic_identity_engine.jobs.queue import JobQueue
from comic_identity_engine.services.imports import (
    apply_clz_import_visibility,
    build_clz_import_health,
    prepare_clz_import_from_path,
)
from comic_identity_engine.services.operations import OperationsManager

router = APIRouter(prefix="/import", tags=["Import"])
logger = structlog.get_logger(__name__)


def _build_import_metadata(
    *,
    operation_status: str,
    operation_result: dict[str, object] | None,
    queue_depth: int | None = None,
) -> dict[str, object]:
    """Build import-specific metadata for operation responses."""
    metadata: dict[str, object] = {
        "status": operation_status,
    }
    if not isinstance(operation_result, dict):
        return metadata

    visible_result = apply_clz_import_visibility(operation_result)
    for key in (
        "file_checksum",
        "file_size",
        "total_rows",
        "resume_count",
        "retry_failed_count",
    ):
        if key in visible_result:
            metadata[key] = visible_result[key]

    metadata.update(build_clz_import_health(visible_result, queue_depth=queue_depth))
    return metadata


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
            retry_failed_only=request.retry_failed_only,
            force=request.force,
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
                "retry_failed_only": request.retry_failed_only,
                **_build_import_metadata(
                    operation_status=operation.status,
                    operation_result=(
                        operation.result if isinstance(operation.result, dict) else None
                    ),
                ),
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
    queue: Annotated[JobQueue, Depends(get_job_queue)],
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
    queue_depth: int | None = 0 if is_done else None
    if not is_done:
        # Queue depth is best-effort metadata, failures are not errors
        queue_depth = await queue.get_queue_depth(operation_id=operation.id)

    response: OperationResponse = OperationResponse(
        name=f"operations/{operation.id}",
        done=is_done,
        metadata={
            "operation_type": operation.operation_type,
            "created_at": operation.created_at.isoformat()
            if operation.created_at
            else None,
            "updated_at": operation.updated_at.isoformat()
            if operation.updated_at
            else None,
            **_build_import_metadata(
                operation_status=operation.status,
                operation_result=(
                    operation.result if isinstance(operation.result, dict) else None
                ),
                queue_depth=queue_depth,
            ),
        },
    )

    if isinstance(operation.result, dict):
        response.response = apply_clz_import_visibility(operation.result)
    elif operation.result:
        response.response = operation.result

    if operation.status == "failed" and operation.error_message:
        error_code = 3
        response.error = {
            "code": error_code,
            "message": operation.error_message,
            "details": [],
        }

    return response


@router.post(
    "/clz/{operation_id}/refresh-mappings",
    response_model=OperationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Refresh missing platform mappings",
    description="Re-run cross-platform search for issues that are missing mappings.",
    responses={
        404: {"description": "Operation not found"},
        400: {"description": "Operation is not a CLZ import or is still running"},
    },
)
async def refresh_clz_mappings(
    operation_id: uuid.UUID,
    queue: Annotated[JobQueue, Depends(get_job_queue)],
    operations_manager: Annotated[OperationsManager, Depends(get_operations_manager)],
    platforms: Annotated[
        Optional[list[str]],
        Query(
            description="Specific platforms to refresh (default: all missing platforms)"
        ),
    ] = None,
) -> OperationResponse:
    """Re-run cross-platform search for issues from this import that are missing mappings.

    This endpoint finds all issues from the specified import operation,
    checks which platforms are missing mappings, and enqueues platform-only
    search tasks to find the missing mappings.

    Args:
        operation_id: UUID of the original CLZ import operation
        platforms: Optional list of specific platforms to refresh
            (default: refresh all missing platforms)
        queue: Job queue dependency for enqueueing jobs
        operations_manager: Operations manager for tracking operation

    Returns:
        OperationResponse with operation name for polling

    Raises:
        HTTPException: 404 if operation not found, 400 if not a CLZ import
    """
    original_operation = await operations_manager.get_operation(operation_id)

    if original_operation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "OPERATION_NOT_FOUND",
                "message": f"Operation not found: {operation_id}",
            },
        )

    if original_operation.operation_type != "import_clz":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_OPERATION_TYPE",
                "message": "This operation is not a CLZ import",
            },
        )

    if original_operation.status not in ("completed", "failed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "OPERATION_STILL_RUNNING",
                "message": "Cannot refresh mappings while import is still running",
            },
        )

    original_result = original_operation.result or {}
    row_results = original_result.get("row_results", {})
    csv_path = original_result.get("csv_path") or original_result.get("file_path")

    if not csv_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "CSV_PATH_NOT_FOUND",
                "message": "Original CSV path not found in operation result",
            },
        )

    csv_file = Path(csv_path)
    if not csv_file.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "CSV_FILE_NOT_FOUND",
                "message": f"Original CSV file not found: {csv_path}",
            },
        )

    async with AsyncSessionLocal() as session:
        mapping_repo = ExternalMappingRepository(session)

        issues_to_refresh = []
        all_platforms = {"gcd", "locg", "ccl", "aa", "cpg", "hip"}

        for row_key, row_result in row_results.items():
            if not row_result.get("resolved"):
                continue

            issue_id_str = row_result.get("issue_id")
            if not issue_id_str:
                continue

            issue_id = uuid.UUID(issue_id_str)
            external_mappings = await mapping_repo.find_by_issue(issue_id)
            mapped_platforms = {m.source for m in external_mappings}

            if platforms:
                target_platforms = set(platforms)
                missing = target_platforms - mapped_platforms
            else:
                missing = all_platforms - mapped_platforms

            if missing:
                issues_to_refresh.append(
                    {
                        "row_key": row_key,
                        "row_index": row_result.get("row_index"),
                        "issue_id": issue_id_str,
                        "source_issue_id": row_result.get("source_issue_id"),
                        "missing_platforms": sorted(missing),
                    }
                )

    if not issues_to_refresh:
        return OperationResponse(
            name=f"operations/{operation_id}",
            done=True,
            metadata={
                "operation_type": "refresh_clz_mappings",
                "original_operation_id": str(operation_id),
                "issues_checked": len(row_results),
                "issues_refreshed": 0,
                "message": "All issues already have all platform mappings",
            },
            response={
                "issues_checked": len(row_results),
                "issues_refreshed": 0,
                "message": "No missing platform mappings found",
            },
        )

    refresh_operation = await operations_manager.create_operation(
        operation_type="refresh_clz_mappings",
        initial_result={
            "original_operation_id": str(operation_id),
            "csv_path": csv_path,
            "total_rows": len(issues_to_refresh),
            "processed": 0,
            "resolved": 0,
            "failed": 0,
            "errors": [],
            "progress": 0.0,
            "issues_to_refresh": issues_to_refresh,
        },
    )

    rows = []
    with open(csv_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    row_by_index = {idx: row for idx, row in enumerate(rows, start=1)}
    row_by_clz_id = {}
    for row in rows:
        clz_id = (row.get("Core ComicID") or "").strip()
        if clz_id:
            row_by_clz_id[clz_id] = row

    enqueued_count = 0
    for issue_info in issues_to_refresh:
        row_index = issue_info.get("row_index")
        source_issue_id = issue_info.get("source_issue_id")

        row_data = None
        if row_index and row_index in row_by_index:
            row_data = row_by_index[row_index]
        elif source_issue_id and source_issue_id in row_by_clz_id:
            row_data = row_by_clz_id[source_issue_id]

        if row_data:
            await queue.enqueue_resolve_clz_row_platforms_only(
                row_data=row_data,
                row_index=row_index or 0,
                operation_id=refresh_operation.id,
            )
            enqueued_count += 1

    return OperationResponse(
        name=f"operations/{refresh_operation.id}",
        done=False,
        metadata={
            "operation_type": "refresh_clz_mappings",
            "original_operation_id": str(operation_id),
            "issues_checked": len(row_results),
            "issues_to_refresh": len(issues_to_refresh),
            "enqueued": enqueued_count,
            "target_platforms": platforms,
        },
    )
