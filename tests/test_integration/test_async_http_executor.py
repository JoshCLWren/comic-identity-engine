"""Integration tests for AsyncHttpExecutor.

These tests verify AsyncHttpExecutor properly enqueues HTTP request tasks
and polls for completion.
"""

import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest

from comic_identity_engine.core.async_http import AsyncHttpExecutor


TEST_OPERATION_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")


@pytest.fixture
def mock_queue():
    """Mock JobQueue."""
    queue = Mock()
    queue.enqueue_http_request = AsyncMock()
    return queue


@pytest.fixture
def mock_operations_manager():
    """Mock OperationsManager."""
    manager = Mock()
    manager.create_operation = AsyncMock()
    manager.get_operation = AsyncMock()
    return manager


@pytest.fixture
def mock_session():
    """Mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
class TestAsyncHttpExecutor:
    """Integration tests for AsyncHttpExecutor."""

    async def test_get_request_success(
        self, mock_queue, mock_operations_manager, mock_session
    ):
        """Test AsyncHttpExecutor successfully executes GET request."""
        mock_operation = Mock()
        mock_operation.id = TEST_OPERATION_ID
        mock_operation.status = "completed"
        mock_operation.result = {
            "status_code": 200,
            "content": "<html>Success</html>",
            "elapsed_ms": 150,
        }
        mock_operations_manager.create_operation.return_value = mock_operation
        mock_operations_manager.get_operation.return_value = mock_operation

        mock_job = Mock()
        mock_job.job_id = "test-job-id"
        mock_queue.enqueue_http_request.return_value = mock_job

        executor = AsyncHttpExecutor(mock_queue, mock_operations_manager)

        with patch(
            "comic_identity_engine.core.async_http.AsyncSessionLocal"
        ) as mock_session_local:
            mock_session_local.return_value.__aenter__.return_value = mock_session
            mock_session_local.return_value.__aexit__.return_value = False

            result = await executor.get("gcd", "https://www.comics.org/issue/125295/")

        assert result["status_code"] == 200
        assert result["content"] == "<html>Success</html>"
        assert result["elapsed_ms"] == 150
        mock_queue.enqueue_http_request.assert_called_once()
        mock_operations_manager.create_operation.assert_called_once()

    async def test_get_request_with_timeout(
        self, mock_queue, mock_operations_manager, mock_session
    ):
        """Test AsyncHttpExecutor handles timeout correctly."""
        mock_operation = Mock()
        mock_operation.id = TEST_OPERATION_ID
        mock_operation.status = "running"
        mock_operations_manager.create_operation.return_value = mock_operation
        mock_operations_manager.get_operation.return_value = mock_operation

        mock_job = Mock()
        mock_job.job_id = "test-job-id"
        mock_queue.enqueue_http_request.return_value = mock_job

        executor = AsyncHttpExecutor(mock_queue, mock_operations_manager)

        with patch(
            "comic_identity_engine.core.async_http.AsyncSessionLocal"
        ) as mock_session_local:
            mock_session_local.return_value.__aenter__.return_value = mock_session
            mock_session_local.return_value.__aexit__.return_value = False

            with patch("comic_identity_engine.core.async_http.time") as mock_time:
                mock_time.time.return_value = 0
                mock_time.sleep = AsyncMock()

                with pytest.raises(TimeoutError, match="HTTP request timeout"):
                    await executor.get(
                        "gcd", "https://www.comics.org/issue/125295/", timeout=1
                    )

    async def test_get_request_handles_error_response(
        self, mock_queue, mock_operations_manager, mock_session
    ):
        """Test AsyncHttpExecutor handles failed operations correctly."""
        mock_operation = Mock()
        mock_operation.id = TEST_OPERATION_ID
        mock_operation.status = "completed"
        mock_operation.result = None
        mock_operation.error_message = "HTTP request failed: Connection refused"
        mock_operations_manager.create_operation.return_value = mock_operation
        mock_operations_manager.get_operation.return_value = mock_operation

        mock_job = Mock()
        mock_job.job_id = "test-job-id"
        mock_queue.enqueue_http_request.return_value = mock_job

        executor = AsyncHttpExecutor(mock_queue, mock_operations_manager)

        with patch(
            "comic_identity_engine.core.async_http.AsyncSessionLocal"
        ) as mock_session_local:
            mock_session_local.return_value.__aenter__.return_value = mock_session
            mock_session_local.return_value.__aexit__.return_value = False

            with pytest.raises(Exception, match="Connection refused"):
                await executor.get("gcd", "https://www.comics.org/issue/125295/")

    async def test_post_request_with_json_data(
        self, mock_queue, mock_operations_manager, mock_session
    ):
        """Test AsyncHttpExecutor successfully executes POST request."""
        mock_operation = Mock()
        mock_operation.id = TEST_OPERATION_ID
        mock_operation.status = "completed"
        mock_operation.result = {
            "status_code": 201,
            "content": '{"created": true}',
            "elapsed_ms": 200,
        }
        mock_operations_manager.create_operation.return_value = mock_operation
        mock_operations_manager.get_operation.return_value = mock_operation

        mock_job = Mock()
        mock_job.job_id = "test-job-id"
        mock_queue.enqueue_http_request.return_value = mock_job

        executor = AsyncHttpExecutor(mock_queue, mock_operations_manager)

        with patch(
            "comic_identity_engine.core.async_http.AsyncSessionLocal"
        ) as mock_session_local:
            mock_session_local.return_value.__aenter__.return_value = mock_session
            mock_session_local.return_value.__aexit__.return_value = False

            result = await executor.post(
                "gcd", "https://api.example.com/comics", json={"title": "Test Comic"}
            )

        assert result["status_code"] == 201
        assert result["content"] == '{"created": true}'
        mock_queue.enqueue_http_request.assert_called_once()
