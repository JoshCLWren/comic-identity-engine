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
    ) -> Operation:
        """Create a new async operation.

        Args:
            operation_type: Type of operation (resolve, bulk_resolve, import_clz, etc.)
            input_data: Optional input data for idempotency check

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

        idempotency_key = (
            self._compute_idempotency_key(operation_type, input_data)
            if input_data
            else None
        )

        if idempotency_key:
            existing = await self.operation_repo.find_by_input_hash(idempotency_key)
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
            input_hash=idempotency_key,
        )

        logger.info(
            "Created operation",
            operation_id=str(operation.id),
            operation_type=operation.operation_type,
            idempotency_key=idempotency_key,
        )

        return operation

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
