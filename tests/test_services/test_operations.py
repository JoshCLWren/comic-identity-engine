"""Tests for operations manager service."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from comic_identity_engine.services.operations import (
    OperationsManager,
    VALID_OPERATION_TYPES,
    VALID_STATUSES,
)


@pytest.fixture
def mock_session():
    """Create mock database session."""
    return AsyncMock()


@pytest.fixture
def sample_operation():
    """Create sample operation."""
    operation = MagicMock()
    operation.id = uuid.uuid4()
    operation.operation_type = "resolve"
    operation.status = "pending"
    operation.input_hash = "abc123"
    operation.result = None
    operation.error_message = None
    return operation


@pytest.fixture
def sample_pending_operation():
    """Create sample pending operation."""
    operation = MagicMock()
    operation.id = uuid.uuid4()
    operation.operation_type = "resolve"
    operation.status = "pending"
    operation.input_hash = "abc123"
    operation.result = None
    operation.error_message = None
    return operation


@pytest.fixture
def sample_running_operation():
    """Create sample running operation."""
    operation = MagicMock()
    operation.id = uuid.uuid4()
    operation.operation_type = "resolve"
    operation.status = "running"
    operation.input_hash = "abc123"
    operation.result = None
    operation.error_message = None
    return operation


@pytest.fixture
def sample_failed_import_operation():
    """Create sample failed import operation with resumable state."""
    operation = MagicMock()
    operation.id = uuid.uuid4()
    operation.operation_type = "import_clz"
    operation.status = "failed"
    operation.input_hash = "checksum-hash"
    operation.result = {
        "file_checksum": "checksum-123",
        "file_size": 128,
        "total_rows": 2,
        "row_manifest": [
            {
                "row_index": 1,
                "source_issue_id": "clz-001",
                "row_key": "clz-001:1",
            },
            {
                "row_index": 2,
                "source_issue_id": "clz-002",
                "row_key": "clz-002:2",
            },
        ],
        "row_results": {
            "clz-001:1": {
                "row_index": 1,
                "row_key": "clz-001:1",
                "source_issue_id": "clz-001",
                "resolved": True,
            }
        },
        "processed": 1,
        "resolved": 1,
        "failed": 0,
        "errors": [],
        "progress": 0.5,
        "resume_count": 1,
        "retry_failed_count": 0,
        "summary": "Processed 1/2 CLZ rows: 1 resolved, 0 failed. 0 errors so far.",
    }
    operation.error_message = "worker crashed"
    return operation


@pytest.fixture
def sample_completed_import_with_failed_rows():
    """Create a completed import with one failed row to retry."""
    operation = MagicMock()
    operation.id = uuid.uuid4()
    operation.operation_type = "import_clz"
    operation.status = "completed"
    operation.input_hash = "checksum-hash"
    operation.result = {
        "file_checksum": "checksum-123",
        "file_size": 128,
        "total_rows": 2,
        "row_manifest": [
            {
                "row_index": 1,
                "source_issue_id": "clz-001",
                "row_key": "clz-001:1",
            },
            {
                "row_index": 2,
                "source_issue_id": "clz-002",
                "row_key": "clz-002:2",
            },
        ],
        "row_results": {
            "clz-001:1": {
                "row_index": 1,
                "row_key": "clz-001:1",
                "source_issue_id": "clz-001",
                "resolved": True,
            },
            "clz-002:2": {
                "row_index": 2,
                "row_key": "clz-002:2",
                "source_issue_id": "clz-002",
                "resolved": False,
                "error": "Row 2 error: Series not found",
            },
        },
        "processed": 2,
        "resolved": 1,
        "failed": 1,
        "errors": [
            {
                "row": 2,
                "row_key": "clz-002:2",
                "source_issue_id": "clz-002",
                "error": "Row 2 error: Series not found",
            }
        ],
        "progress": 1.0,
        "resume_count": 0,
        "retry_failed_count": 0,
        "summary": "Processed 2 CLZ rows: 1 resolved, 1 failed. 1 errors.",
    }
    operation.error_message = None
    return operation


@pytest.mark.asyncio
class TestOperationsManager:
    """Tests for OperationsManager class."""

    @patch("comic_identity_engine.services.operations.OperationRepository")
    async def test_create_operation(
        self, mock_repo_cls, mock_session, sample_operation
    ):
        """Test creating a new operation."""
        mock_repo = MagicMock()
        mock_repo.create_operation = AsyncMock(return_value=sample_operation)
        mock_repo.find_by_input_hash = AsyncMock(return_value=None)
        mock_repo_cls.return_value = mock_repo

        manager = OperationsManager(mock_session)
        result = await manager.create_operation("resolve", {"url": "https://..."})

        assert result.operation_type == "resolve"
        assert result.status == "pending"

    @patch("comic_identity_engine.services.operations.OperationRepository")
    async def test_create_operation_with_idempotency(
        self, mock_repo_cls, mock_session, sample_operation
    ):
        """Test operation creation with idempotency check."""
        mock_repo = MagicMock()
        mock_repo.find_by_input_hash = AsyncMock(return_value=sample_operation)
        mock_repo_cls.return_value = mock_repo

        manager = OperationsManager(mock_session)
        result = await manager.create_operation("resolve", {"url": "https://..."})

        assert result == sample_operation
        mock_repo.create_operation.assert_not_called()

    @patch("comic_identity_engine.services.operations.OperationRepository")
    async def test_create_operation_supports_initial_result_and_explicit_key(
        self, mock_repo_cls, mock_session, sample_operation
    ):
        """Test operation creation with explicit idempotency key and initial result."""
        mock_repo = MagicMock()
        mock_repo.create_operation = AsyncMock(return_value=sample_operation)
        mock_repo.find_by_input_hash = AsyncMock(return_value=None)
        mock_repo_cls.return_value = mock_repo

        manager = OperationsManager(mock_session)
        initial_result = {"file_checksum": "checksum-123"}

        await manager.create_operation(
            "import_clz",
            idempotency_key="custom-key",
            initial_result=initial_result,
        )

        mock_repo.find_by_input_hash.assert_awaited_once_with("custom-key")
        mock_repo.create_operation.assert_awaited_once_with(
            operation_type="import_clz",
            input_hash="custom-key",
            result=initial_result,
        )

    @patch("comic_identity_engine.services.operations.OperationRepository")
    async def test_create_or_resume_import_operation_creates_new_operation(
        self, mock_repo_cls, mock_session
    ):
        """Test checksum-addressed import creation for a new file."""
        created_operation = MagicMock()
        created_operation.id = uuid.uuid4()
        created_operation.operation_type = "import_clz"
        created_operation.status = "pending"
        created_operation.result = {"resume_count": 0}

        mock_repo = MagicMock()
        mock_repo.find_by_input_hash = AsyncMock(return_value=None)
        mock_repo.create_operation = AsyncMock(return_value=created_operation)
        mock_repo_cls.return_value = mock_repo

        manager = OperationsManager(mock_session)
        initial_result = {
            "file_checksum": "checksum-123",
            "file_size": 128,
            "total_rows": 1,
            "row_manifest": [
                {
                    "row_index": 1,
                    "source_issue_id": "clz-001",
                    "row_key": "clz-001:1",
                }
            ],
            "row_results": {},
            "processed": 0,
            "resolved": 0,
            "failed": 0,
            "errors": [],
            "progress": 0.0,
            "resume_count": 0,
            "retry_failed_count": 0,
            "summary": "Prepared 1 CLZ rows for processing",
        }

        operation, should_enqueue = await manager.create_or_resume_import_operation(
            operation_type="import_clz",
            file_checksum="checksum-123",
            initial_result=initial_result,
        )

        assert operation is created_operation
        assert should_enqueue is True
        mock_repo.create_operation.assert_awaited_once()

    @patch("comic_identity_engine.services.operations.OperationRepository")
    async def test_create_or_resume_import_operation_reuses_running_operation(
        self, mock_repo_cls, mock_session
    ):
        """Test same-file import returns the current running operation."""
        existing_operation = MagicMock()
        existing_operation.id = uuid.uuid4()
        existing_operation.operation_type = "import_clz"
        existing_operation.status = "running"
        existing_operation.result = {
            "file_checksum": "checksum-123",
            "file_size": 128,
            "total_rows": 1,
            "row_manifest": [
                {
                    "row_index": 1,
                    "source_issue_id": "clz-001",
                    "row_key": "clz-001:1",
                }
            ],
            "row_results": {},
            "processed": 0,
            "resolved": 0,
            "failed": 0,
            "errors": [],
            "progress": 0.0,
            "resume_count": 0,
            "summary": "Prepared 1 CLZ rows for processing",
        }

        mock_repo = MagicMock()
        mock_repo.find_by_input_hash = AsyncMock(return_value=existing_operation)
        mock_repo.update_status = AsyncMock(return_value=existing_operation)
        mock_repo_cls.return_value = mock_repo

        manager = OperationsManager(mock_session)
        operation, should_enqueue = await manager.create_or_resume_import_operation(
            operation_type="import_clz",
            file_checksum="checksum-123",
            initial_result=dict(existing_operation.result),
        )

        assert operation is existing_operation
        assert should_enqueue is False
        mock_repo.create_operation.assert_not_called()
        mock_repo.update_status.assert_not_called()

    @patch("comic_identity_engine.services.operations.OperationRepository")
    async def test_create_or_resume_import_operation_resumes_failed_operation(
        self, mock_repo_cls, mock_session, sample_failed_import_operation
    ):
        """Test same-file retry reuses the failed operation id and resets it."""
        resumed_operation = MagicMock()
        resumed_operation.id = sample_failed_import_operation.id
        resumed_operation.operation_type = "import_clz"
        resumed_operation.status = "pending"
        resumed_operation.result = {
            **sample_failed_import_operation.result,
            "resume_count": 2,
            "summary": "Resuming CLZ import with 1 rows remaining out of 2.",
        }
        resumed_operation.input_hash = sample_failed_import_operation.input_hash
        resumed_operation.error_message = None

        mock_repo = MagicMock()
        mock_repo.find_by_input_hash = AsyncMock(
            return_value=sample_failed_import_operation
        )
        mock_repo.update_status = AsyncMock(return_value=resumed_operation)
        mock_repo_cls.return_value = mock_repo

        manager = OperationsManager(mock_session)
        operation, should_enqueue = await manager.create_or_resume_import_operation(
            operation_type="import_clz",
            file_checksum="checksum-123",
            initial_result=dict(sample_failed_import_operation.result),
        )

        assert operation is resumed_operation
        assert should_enqueue is True
        mock_repo.update_status.assert_awaited_once_with(
            sample_failed_import_operation,
            status="pending",
            result=resumed_operation.result,
            clear_error_message=True,
        )

    @patch("comic_identity_engine.services.operations.OperationRepository")
    async def test_create_or_resume_import_operation_retries_only_failed_rows(
        self,
        mock_repo_cls,
        mock_session,
        sample_completed_import_with_failed_rows,
    ):
        """Test same-file retry-failed-only preserves resolved rows and requeues failures."""
        retried_operation = MagicMock()
        retried_operation.id = sample_completed_import_with_failed_rows.id
        retried_operation.operation_type = "import_clz"
        retried_operation.status = "pending"
        retried_operation.result = {
            **sample_completed_import_with_failed_rows.result,
            "row_results": {
                "clz-001:1": {
                    "row_index": 1,
                    "row_key": "clz-001:1",
                    "source_issue_id": "clz-001",
                    "resolved": True,
                }
            },
            "processed": 1,
            "resolved": 1,
            "failed": 0,
            "errors": [],
            "progress": 0.5,
            "retry_failed_count": 1,
            "summary": (
                "Retrying 1 failed CLZ rows while preserving 1 resolved rows out of 2."
            ),
        }
        retried_operation.input_hash = (
            sample_completed_import_with_failed_rows.input_hash
        )
        retried_operation.error_message = None

        mock_repo = MagicMock()
        mock_repo.find_by_input_hash = AsyncMock(
            return_value=sample_completed_import_with_failed_rows
        )
        mock_repo.update_status = AsyncMock(return_value=retried_operation)
        mock_repo_cls.return_value = mock_repo

        manager = OperationsManager(mock_session)
        operation, should_enqueue = await manager.create_or_resume_import_operation(
            operation_type="import_clz",
            file_checksum="checksum-123",
            initial_result=dict(sample_completed_import_with_failed_rows.result),
            retry_failed_only=True,
        )

        assert operation is retried_operation
        assert should_enqueue is True
        mock_repo.update_status.assert_awaited_once_with(
            sample_completed_import_with_failed_rows,
            status="pending",
            result=retried_operation.result,
            clear_error_message=True,
        )

    @patch("comic_identity_engine.services.operations.OperationRepository")
    async def test_create_operation_invalid_type(self, mock_repo_cls, mock_session):
        """Test creating operation with invalid type raises ValueError."""
        mock_repo = MagicMock()
        mock_repo.find_by_input_hash = AsyncMock(return_value=None)
        mock_repo_cls.return_value = mock_repo

        manager = OperationsManager(mock_session)

        with pytest.raises(ValueError, match="Invalid operation_type"):
            await manager.create_operation("invalid_type")

    @patch("comic_identity_engine.services.operations.OperationRepository")
    async def test_update_operation(
        self, mock_repo_cls, mock_session, sample_pending_operation
    ):
        """Test updating operation status."""
        mock_repo = MagicMock()
        mock_repo.get_operation = AsyncMock(return_value=sample_pending_operation)
        mock_repo.update_status = AsyncMock(return_value=sample_pending_operation)
        mock_repo_cls.return_value = mock_repo

        manager = OperationsManager(mock_session)
        result = await manager.update_operation(sample_pending_operation.id, "running")

        assert result == sample_pending_operation

    @patch("comic_identity_engine.services.operations.OperationRepository")
    async def test_update_operation_allows_running_progress_updates(
        self, mock_repo_cls, mock_session, sample_running_operation
    ):
        """Test updating progress without changing running status."""
        mock_repo = MagicMock()
        mock_repo.get_operation = AsyncMock(return_value=sample_running_operation)
        mock_repo.update_status = AsyncMock(return_value=sample_running_operation)
        mock_repo_cls.return_value = mock_repo

        manager = OperationsManager(mock_session)
        result = await manager.update_operation(
            sample_running_operation.id,
            "running",
            result={"platform_status": {"gcd": "found"}},
        )

        assert result == sample_running_operation
        mock_repo.update_status.assert_awaited_once_with(
            sample_running_operation,
            status="running",
            result={"platform_status": {"gcd": "found"}},
            error_message=None,
        )

    @patch("comic_identity_engine.services.operations.OperationRepository")
    async def test_update_operation_invalid_status(self, mock_repo_cls, mock_session):
        """Test updating operation with invalid status raises ValueError."""
        mock_repo = MagicMock()
        mock_repo.get_operation = AsyncMock(return_value=None)
        mock_repo_cls.return_value = mock_repo

        manager = OperationsManager(mock_session)

        with pytest.raises(ValueError, match="Invalid status"):
            await manager.update_operation(uuid.uuid4(), "invalid_status")

    @patch("comic_identity_engine.services.operations.OperationRepository")
    async def test_update_operation_not_found(self, mock_repo_cls, mock_session):
        """Test updating non-existent operation raises ValueError."""
        mock_repo = MagicMock()
        mock_repo.get_operation = AsyncMock(return_value=None)
        mock_repo_cls.return_value = mock_repo

        manager = OperationsManager(mock_session)

        with pytest.raises(ValueError, match="Operation not found"):
            await manager.update_operation(uuid.uuid4(), "running")

    @patch("comic_identity_engine.services.operations.OperationRepository")
    async def test_get_operation(self, mock_repo_cls, mock_session, sample_operation):
        """Test getting operation by ID."""
        mock_repo = MagicMock()
        mock_repo.get_operation = AsyncMock(return_value=sample_operation)
        mock_repo_cls.return_value = mock_repo

        manager = OperationsManager(mock_session)
        result = await manager.get_operation(sample_operation.id)

        assert result == sample_operation

    @patch("comic_identity_engine.services.operations.OperationRepository")
    async def test_get_operation_not_found(self, mock_repo_cls, mock_session):
        """Test getting non-existent operation returns None."""
        mock_repo = MagicMock()
        mock_repo.get_operation = AsyncMock(return_value=None)
        mock_repo_cls.return_value = mock_repo

        manager = OperationsManager(mock_session)
        result = await manager.get_operation(uuid.uuid4())

        assert result is None

    @patch("comic_identity_engine.services.operations.OperationRepository")
    async def test_get_operation_by_hash(
        self, mock_repo_cls, mock_session, sample_operation
    ):
        """Test getting operation by input hash."""
        mock_repo = MagicMock()
        mock_repo.find_by_input_hash = AsyncMock(return_value=sample_operation)
        mock_repo_cls.return_value = mock_repo

        manager = OperationsManager(mock_session)
        result = await manager.get_operation_by_hash("abc123")

        assert result == sample_operation

    @patch("comic_identity_engine.services.operations.OperationRepository")
    async def test_get_pending_operations(self, mock_repo_cls, mock_session):
        """Test getting pending operations."""
        mock_repo = MagicMock()
        mock_repo.find_by_status = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        manager = OperationsManager(mock_session)
        result = await manager.get_pending_operations()

        assert isinstance(result, list)

    @patch("comic_identity_engine.services.operations.OperationRepository")
    async def test_get_running_operations(self, mock_repo_cls, mock_session):
        """Test getting running operations."""
        mock_repo = MagicMock()
        mock_repo.find_by_status = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        manager = OperationsManager(mock_session)
        result = await manager.get_running_operations()

        assert isinstance(result, list)

    @patch("comic_identity_engine.services.operations.OperationRepository")
    async def test_get_failed_operations(self, mock_repo_cls, mock_session):
        """Test getting failed operations."""
        mock_repo = MagicMock()
        mock_repo.find_by_status = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        manager = OperationsManager(mock_session)
        result = await manager.get_failed_operations()

        assert isinstance(result, list)

    @patch("comic_identity_engine.services.operations.OperationRepository")
    async def test_mark_running(
        self, mock_repo_cls, mock_session, sample_pending_operation
    ):
        """Test marking operation as running."""
        mock_repo = MagicMock()
        mock_repo.get_operation = AsyncMock(return_value=sample_pending_operation)
        mock_repo.update_status = AsyncMock(return_value=sample_pending_operation)
        mock_repo_cls.return_value = mock_repo

        manager = OperationsManager(mock_session)
        result = await manager.mark_running(sample_pending_operation.id)

        assert result == sample_pending_operation

    @patch("comic_identity_engine.services.operations.OperationRepository")
    async def test_mark_completed(
        self, mock_repo_cls, mock_session, sample_running_operation
    ):
        """Test marking operation as completed."""
        mock_repo = MagicMock()
        mock_repo.get_operation = AsyncMock(return_value=sample_running_operation)
        mock_repo.update_status = AsyncMock(return_value=sample_running_operation)
        mock_repo_cls.return_value = mock_repo

        manager = OperationsManager(mock_session)
        result = await manager.mark_completed(
            sample_running_operation.id, {"status": "success"}
        )

        assert result == sample_running_operation

    @patch("comic_identity_engine.services.operations.OperationRepository")
    async def test_mark_failed(self, mock_repo_cls, mock_session, sample_operation):
        """Test marking operation as failed."""
        mock_repo = MagicMock()
        mock_repo.get_operation = AsyncMock(return_value=sample_operation)
        mock_repo.update_status = AsyncMock(return_value=sample_operation)
        mock_repo_cls.return_value = mock_repo

        manager = OperationsManager(mock_session)
        result = await manager.mark_failed(sample_operation.id, "Test error")

        assert result == sample_operation

    async def test_compute_input_hash(self, mock_session):
        """Test input hash computation."""
        manager = OperationsManager(mock_session)
        hash1 = manager._compute_input_hash({"url": "https://..."})
        hash2 = manager._compute_input_hash({"url": "https://..."})
        hash3 = manager._compute_input_hash({"url": "https://...other"})

        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 64


class TestConstants:
    """Tests for module constants."""

    def test_valid_operation_types(self):
        """Test VALID_OPERATION_TYPES contains expected values."""
        assert "resolve" in VALID_OPERATION_TYPES
        assert "bulk_resolve" in VALID_OPERATION_TYPES
        assert "import_clz" in VALID_OPERATION_TYPES
        assert "import_csv" in VALID_OPERATION_TYPES

    def test_valid_statuses(self):
        """Test VALID_STATUSES contains expected values."""
        assert "pending" in VALID_STATUSES
        assert "running" in VALID_STATUSES
        assert "completed" in VALID_STATUSES
        assert "failed" in VALID_STATUSES
