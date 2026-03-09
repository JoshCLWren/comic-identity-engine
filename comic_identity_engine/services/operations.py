"""Operations Manager (AIP-151 compliant).

This module provides async operation tracking for long-running tasks
such as bulk resolution, imports, and exports, following AIP-151
specification.

USAGE:
    from comic_identity_engine.services import OperationsManager

    manager = OperationsManager(session)
    operation = await manager.create_operation("resolve", input_hash)
    # ... do work ...
    await manager.update_operation(operation.id, "completed", result)
"""

import hashlib
import json
import uuid
from typing import Any, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from comic_identity_engine.database.models import Operation
from comic_identity_engine.database.repositories import OperationRepository
from comic_identity_engine.services.imports import apply_clz_import_visibility


logger = structlog.get_logger(__name__)

VALID_OPERATION_TYPES = [
    "resolve",
    "bulk_resolve",
    "import_clz",
    "import_csv",
    "export",
    "reconcile",
]

VALID_STATUSES = [
    "pending",
    "running",
    "completed",
    "failed",
]


class OperationsManager:
    """Manager for async operations tracking (AIP-151).

    This class provides methods to create, update, and query long-running
    async operations with status tracking and result storage.

    Attributes:
        session: Async database session
        operation_repo: Operation repository
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize operations manager.

        Args:
            session: Async database session
        """
        self.session = session
        self.operation_repo = OperationRepository(session)

    async def create_operation(
        self,
        operation_type: str,
        input_data: Optional[dict[str, Any]] = None,
        force: bool = False,
        idempotency_key: str | None = None,
        initial_result: Optional[dict[str, Any]] = None,
    ) -> Operation:
        """Create a new async operation.

        Args:
            operation_type: Type of operation (resolve, bulk_resolve, import_clz, etc.)
            input_data: Optional input data for idempotency check
            force: If True, bypass idempotency check and create a new operation

        Returns:
            Created Operation entity

        Raises:
            RepositoryError: If database operation fails
            ValueError: If operation_type is invalid

        Examples:
            >>> op = await manager.create_operation("resolve", {"url": "https://..."})
            >>> print(op.id)
            uuid.UUID('...')
        """
        if operation_type not in VALID_OPERATION_TYPES:
            raise ValueError(
                f"Invalid operation_type: {operation_type}. "
                f"Must be one of: {', '.join(VALID_OPERATION_TYPES)}"
            )

        computed_idempotency_key = idempotency_key
        if computed_idempotency_key is None and input_data:
            computed_idempotency_key = self._compute_idempotency_key(
                operation_type, input_data
            )

        if computed_idempotency_key and not force:
            existing = await self.operation_repo.find_by_input_hash(
                computed_idempotency_key
            )
            if existing:
                logger.info(
                    "Found existing operation for idempotency key",
                    operation_id=str(existing.id),
                    operation_type=existing.operation_type,
                    status=existing.status,
                )
                return existing

        operation = await self.operation_repo.create_operation(
            operation_type=operation_type,
            input_hash=computed_idempotency_key,
            result=initial_result,
        )

        logger.info(
            "Created operation",
            operation_id=str(operation.id),
            operation_type=operation.operation_type,
            idempotency_key=computed_idempotency_key,
        )

        return operation

    async def create_or_resume_import_operation(
        self,
        *,
        operation_type: str,
        file_checksum: str,
        initial_result: dict[str, Any],
        retry_failed_only: bool = False,
    ) -> tuple[Operation, bool]:
        """Create or resume a checksum-addressed import operation.

        Returns:
            Tuple of the operation and whether the caller should enqueue work.
        """
        if operation_type not in VALID_OPERATION_TYPES:
            raise ValueError(
                f"Invalid operation_type: {operation_type}. "
                f"Must be one of: {', '.join(VALID_OPERATION_TYPES)}"
            )

        idempotency_key = self._compute_idempotency_key(
            operation_type,
            {"file_checksum": file_checksum},
        )
        existing = await self.operation_repo.find_by_input_hash(idempotency_key)
        if existing is None:
            operation = await self.operation_repo.create_operation(
                operation_type=operation_type,
                input_hash=idempotency_key,
                result=initial_result,
            )
            logger.info(
                "Created checksum-addressed import operation",
                operation_id=str(operation.id),
                operation_type=operation.operation_type,
                file_checksum=file_checksum,
            )
            return operation, True

        merged_result = self._merge_import_result(existing.result, initial_result)
        operation = existing
        should_enqueue = False

        if retry_failed_only and existing.status in {"completed", "failed"}:
            retried_result = self._build_retry_failed_result(merged_result)
            if retried_result is not None:
                operation = await self.operation_repo.update_status(
                    existing,
                    status="pending",
                    result=retried_result,
                    clear_error_message=True,
                )
                logger.info(
                    "Requeued failed CLZ rows on checksum-addressed import",
                    operation_id=str(operation.id),
                    operation_type=operation.operation_type,
                    status=operation.status,
                    file_checksum=file_checksum,
                )
                return operation, True

        if merged_result != (existing.result or {}):
            operation = await self.operation_repo.update_status(
                existing,
                status=existing.status,
                result=merged_result,
            )

        if existing.status == "failed":
            resumed_result = dict(operation.result or {})
            row_results = resumed_result.get("row_results", {})
            if retry_failed_only:
                failed_row_count = sum(
                    1
                    for row_result in row_results.values()
                    if row_result and not row_result.get("resolved")
                )
                if failed_row_count == 0:
                    logger.info(
                        "No failed rows to retry in checksum-addressed import",
                        operation_id=str(operation.id),
                        file_checksum=file_checksum,
                    )
                    return operation, False

            resumed_result["active_row_keys"] = []
            resumed_result["resume_count"] = (
                int(resumed_result.get("resume_count", 0) or 0) + 1
            )
            resumed_result["summary"] = self._build_resume_summary(resumed_result)
            resumed_result = apply_clz_import_visibility(resumed_result)
            operation = await self.operation_repo.update_status(
                operation,
                status="pending",
                result=resumed_result,
                clear_error_message=True,
            )
            should_enqueue = True

        logger.info(
            "Reused checksum-addressed import operation",
            operation_id=str(operation.id),
            operation_type=operation.operation_type,
            status=operation.status,
            file_checksum=file_checksum,
            should_enqueue=should_enqueue,
        )
        return operation, should_enqueue

    async def update_operation(
        self,
        operation_id: uuid.UUID,
        status: str,
        result: Optional[dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> Operation:
        """Update operation status and result.

        Args:
            operation_id: UUID of the operation to update
            status: New status (pending, running, completed, failed)
            result: Optional result data as dictionary
            error_message: Optional error message if failed

        Returns:
            Updated Operation entity

        Raises:
            RepositoryError: If database operation fails
            ValueError: If status is invalid or operation not found or transition invalid

        Examples:
            >>> await manager.update_operation(
            ...     op.id,
            ...     "completed",
            ...     {"issue_id": "...", "confidence": 0.95}
            ... )
        """
        if status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status: {status}. Must be one of: {', '.join(VALID_STATUSES)}"
            )

        operation = await self.operation_repo.get_operation(operation_id)
        if not operation:
            raise ValueError(f"Operation not found: {operation_id}")

        is_progress_update = (
            operation.status == status
            and status == "running"
            and (result is not None or error_message is not None)
        )

        if not is_progress_update:
            self._validate_status_transition(operation.status, status)

        updated = await self.operation_repo.update_status(
            operation,
            status=status,
            result=result,
            error_message=error_message,
        )

        logger.info(
            "Updated operation",
            operation_id=str(operation_id),
            status=status,
            has_error=error_message is not None,
        )

        return updated

    def _validate_status_transition(self, current_status: str, new_status: str) -> None:
        """Validate that status transition is allowed.

        Args:
            current_status: Current operation status
            new_status: Desired new status

        Raises:
            ValueError: If transition is not allowed
        """
        valid_transitions = {
            "pending": ["running", "failed"],
            "running": ["completed", "failed"],
            "completed": [],
            "failed": [],
        }

        allowed_transitions = valid_transitions.get(current_status, [])
        if new_status not in allowed_transitions:
            raise ValueError(
                f"Invalid status transition: {current_status} -> {new_status}. "
                f"Allowed transitions: {', '.join(allowed_transitions) or 'none'}"
            )

    async def get_operation(self, operation_id: uuid.UUID) -> Optional[Operation]:
        """Get operation by ID.

        Args:
            operation_id: UUID of the operation

        Returns:
            Operation entity or None if not found

        Examples:
            >>> op = await manager.get_operation(operation_id)
            >>> print(op.status)
            'completed'
        """
        return await self.operation_repo.get_operation(operation_id)

    async def get_operation_by_hash(self, input_hash: str) -> Optional[Operation]:
        """Get operation by input hash (idempotency check).

        Args:
            input_hash: Hash of input data

        Returns:
            Operation entity or None if not found

        Examples:
            >>> op = await manager.get_operation_by_hash("abc123...")
            >>> if op:
            ...     print(f"Operation exists: {op.id}")
        """
        return await self.operation_repo.find_by_input_hash(input_hash)

    async def get_pending_operations(self, limit: int = 100) -> list[Operation]:
        """Get all pending operations.

        Args:
            limit: Maximum number of operations to return

        Returns:
            List of pending Operation entities

        Examples:
            >>> pending = await manager.get_pending_operations()
            >>> for op in pending:
            ...     print(f"Process {op.id}")
        """
        return await self.operation_repo.find_by_status("pending", limit)

    async def get_running_operations(self, limit: int = 100) -> list[Operation]:
        """Get all running operations.

        Args:
            limit: Maximum number of operations to return

        Returns:
            List of running Operation entities

        Examples:
            >>> running = await manager.get_running_operations()
            >>> print(f"{len(running)} operations running")
        """
        return await self.operation_repo.find_by_status("running", limit)

    async def get_failed_operations(self, limit: int = 100) -> list[Operation]:
        """Get all failed operations.

        Args:
            limit: Maximum number of operations to return

        Returns:
            List of failed Operation entities

        Examples:
            >>> failed = await manager.get_failed_operations()
            >>> for op in failed:
            ...     print(f"Retry {op.id}: {op.error_message}")
        """
        return await self.operation_repo.find_by_status("failed", limit)

    def _merge_import_result(
        self,
        existing_result: Optional[dict[str, Any]],
        incoming_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge persisted import state with the latest fingerprint metadata."""
        merged = dict(existing_result or {})
        persisted_keys = {
            "row_results",
            "processed",
            "resolved",
            "failed",
            "errors",
            "progress",
            "summary",
            "resume_count",
            "retry_failed_count",
            "active_row_keys",
            "active_row_count",
            "pending_row_count",
            "failed_row_count",
        }

        for key, value in incoming_result.items():
            if key in persisted_keys and key in merged:
                continue
            merged[key] = value

        if "resume_count" not in merged:
            merged["resume_count"] = int(incoming_result.get("resume_count", 0) or 0)

        return apply_clz_import_visibility(merged)

    def _build_resume_summary(self, result: dict[str, Any]) -> str:
        """Build a summary message for a resumed import operation."""
        total_rows = int(result.get("total_rows", 0) or 0)
        processed = int(result.get("processed", 0) or 0)
        remaining = max(total_rows - processed, 0)
        if processed:
            return (
                f"Resuming CLZ import with {remaining} rows remaining "
                f"out of {total_rows}."
            )
        return f"Resuming CLZ import for {total_rows} rows."

    def _build_retry_failed_result(
        self,
        result: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Clear failed row results so the import task can enqueue them again."""
        row_results = dict(result.get("row_results", {}) or {})
        if not row_results:
            return None

        preserved_row_results = {
            row_key: row_result
            for row_key, row_result in row_results.items()
            if row_result.get("resolved")
        }
        retried_failed_rows = len(row_results) - len(preserved_row_results)
        if retried_failed_rows <= 0:
            return None

        total_rows = int(result.get("total_rows", 0) or 0)
        preserved_resolved_rows = len(preserved_row_results)
        retry_result = dict(result)
        retry_result["row_results"] = preserved_row_results
        retry_result["processed"] = preserved_resolved_rows
        retry_result["resolved"] = preserved_resolved_rows
        retry_result["failed"] = 0
        retry_result["errors"] = []
        retry_result["progress"] = (
            preserved_resolved_rows / total_rows if total_rows else 0.0
        )
        retry_result["active_row_keys"] = []
        retry_result["retry_failed_count"] = (
            int(retry_result.get("retry_failed_count", 0) or 0) + 1
        )
        retry_result["summary"] = self._build_retry_failed_summary(
            total_rows=total_rows,
            preserved_resolved_rows=preserved_resolved_rows,
            retried_failed_rows=retried_failed_rows,
        )
        return apply_clz_import_visibility(retry_result)

    def _build_retry_failed_summary(
        self,
        *,
        total_rows: int,
        preserved_resolved_rows: int,
        retried_failed_rows: int,
    ) -> str:
        """Build a summary message for a failed-row-only retry."""
        return (
            f"Retrying {retried_failed_rows} failed CLZ rows while preserving "
            f"{preserved_resolved_rows} resolved rows out of {total_rows}."
        )

    def _compute_idempotency_key(
        self, operation_type: str, input_data: dict[str, Any]
    ) -> str:
        """Compute idempotency key including operation type and input data.

        Args:
            operation_type: Type of operation
            input_data: Input data dictionary

        Returns:
            SHA256 hash as hexadecimal string

        Examples:
            >>> key = manager._compute_idempotency_key("resolve", {"url": "https://..."})
            >>> print(key)
            'abc123...'
        """
        normalized = json.dumps(
            {"operation_type": operation_type, "input": input_data}, sort_keys=True
        )
        return hashlib.sha256(normalized.encode()).hexdigest()

    def _compute_input_hash(self, input_data: dict[str, Any]) -> str:
        """Compute hash of input data for idempotency (deprecated, use _compute_idempotency_key).

        Args:
            input_data: Input data dictionary

        Returns:
            SHA256 hash as hexadecimal string

        Examples:
            >>> hash = manager._compute_input_hash({"url": "https://..."})
            >>> print(hash)
            'abc123...'
        """
        normalized = json.dumps(input_data, sort_keys=True)
        return hashlib.sha256(normalized.encode()).hexdigest()

    async def mark_running(self, operation_id: uuid.UUID) -> Operation:
        """Mark operation as running.

        Convenience method for update_operation.

        Args:
            operation_id: UUID of the operation

        Returns:
            Updated Operation entity
        """
        return await self.update_operation(operation_id, "running")

    async def mark_completed(
        self,
        operation_id: uuid.UUID,
        result: dict[str, Any],
    ) -> Operation:
        """Mark operation as completed.

        Convenience method for update_operation.

        Args:
            operation_id: UUID of the operation
            result: Result data

        Returns:
            Updated Operation entity
        """
        return await self.update_operation(operation_id, "completed", result=result)

    async def mark_failed(
        self,
        operation_id: uuid.UUID,
        error_message: str,
    ) -> Operation:
        """Mark operation as failed.

        Convenience method for update_operation.

        Args:
            operation_id: UUID of the operation
            error_message: Error message

        Returns:
            Updated Operation entity
        """
        return await self.update_operation(
            operation_id,
            "failed",
            error_message=error_message,
        )
