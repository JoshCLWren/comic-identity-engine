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
