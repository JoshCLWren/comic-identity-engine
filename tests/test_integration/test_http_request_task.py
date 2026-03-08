"""Integration tests for HTTP request tasks.

These tests verify the http_request_task function executes properly
and integrates with the operations tracking system.
"""

import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest

from comic_identity_engine.jobs.tasks import http_request_task


TEST_OPERATION_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")


@pytest.fixture
def mock_async_session_local():
    """Mock AsyncSessionLocal context manager."""
    session = AsyncMock()
    with patch("comic_identity_engine.jobs.tasks.AsyncSessionLocal") as mock:
        mock.return_value.__aenter__ = AsyncMock(return_value=session)
        mock.return_value.__aexit__ = AsyncMock(return_value=False)
        yield session


@pytest.mark.asyncio
class TestHttpRequestTask:
    """Integration tests for http_request_task."""

    async def test_http_request_task_success_get_request(
        self, mock_async_session_local
    ):
        """Test http_request_task successfully executes GET request."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.HttpClient"
            ) as mock_http_client:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.text = "<html>Test content</html>"
                mock_client_instance = AsyncMock()
                mock_client_instance.__aenter__ = AsyncMock(
                    return_value=mock_client_instance
                )
                mock_client_instance.__aexit__ = AsyncMock(return_value=False)
                mock_client_instance.get = AsyncMock(return_value=mock_response)
                mock_http_client.return_value = mock_client_instance

                result = await http_request_task(
                    {},
                    "https://www.comics.org/issue/125295/?format=json",
                    "GET",
                    operation_id=str(TEST_OPERATION_ID),
                    platform="gcd",
                )

        assert result["success"] is True
        assert result["status_code"] == 200
        assert result["content"] == "<html>Test content</html>"
        assert result["error"] is None
        assert result["operation_id"] == str(TEST_OPERATION_ID)
        assert "elapsed_ms" in result
        mock_ops_manager.mark_running.assert_called_once_with(TEST_OPERATION_ID)
        mock_ops_manager.mark_completed.assert_called_once()

    async def test_http_request_task_handles_404_not_found(
        self, mock_async_session_local
    ):
        """Test http_request_task handles 404 responses correctly."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.HttpClient"
            ) as mock_http_client:
                mock_response = Mock()
                mock_response.status_code = 404
                mock_response.text = "Not Found"
                mock_client_instance = AsyncMock()
                mock_client_instance.__aenter__ = AsyncMock(
                    return_value=mock_client_instance
                )
                mock_client_instance.__aexit__ = AsyncMock(return_value=False)
                mock_client_instance.get = AsyncMock(return_value=mock_response)
                mock_http_client.return_value = mock_client_instance

                result = await http_request_task(
                    {},
                    "https://www.comics.org/issue/999999/?format=json",
                    "GET",
                    operation_id=str(TEST_OPERATION_ID),
                    platform="gcd",
                )

        assert result["success"] is False
        assert result["status_code"] == 404
        assert result["content"] == "Not Found"
        mock_ops_manager.mark_completed.assert_called_once()

    async def test_http_request_task_handles_network_error(
        self, mock_async_session_local
    ):
        """Test http_request_task handles network errors gracefully."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_failed = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.HttpClient"
            ) as mock_http_client:
                mock_client_instance = AsyncMock()
                mock_client_instance.__aenter__ = AsyncMock(
                    return_value=mock_client_instance
                )
                mock_client_instance.__aexit__ = AsyncMock(return_value=False)
                mock_client_instance.get = AsyncMock(
                    side_effect=Exception("Connection refused")
                )
                mock_http_client.return_value = mock_client_instance

                result = await http_request_task(
                    {},
                    "https://invalid-domain-test.local/",
                    "GET",
                    operation_id=str(TEST_OPERATION_ID),
                    platform="gcd",
                )

        assert result["success"] is False
        assert result["status_code"] is None
        assert result["content"] is None
        assert "error" in result
        assert "Connection refused" in result["error"]
        mock_ops_manager.mark_failed.assert_called_once()

    async def test_http_request_task_auto_generates_operation_id(
        self, mock_async_session_local
    ):
        """Test http_request_task auto-generates operation_id if not provided."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.HttpClient"
            ) as mock_http_client:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.text = "OK"
                mock_client_instance = AsyncMock()
                mock_client_instance.__aenter__ = AsyncMock(
                    return_value=mock_client_instance
                )
                mock_client_instance.__aexit__ = AsyncMock(return_value=False)
                mock_client_instance.get = AsyncMock(return_value=mock_response)
                mock_http_client.return_value = mock_client_instance

                result = await http_request_task(
                    {},
                    "https://www.comics.org/issue/125295/?format=json",
                    "GET",
                    operation_id=None,
                    platform="gcd",
                )

        assert result["success"] is True
        assert result["operation_id"] is not None
        assert isinstance(result["operation_id"], str)
        mock_ops_manager.mark_running.assert_called_once()

    async def test_http_request_task_post_request_with_json(
        self, mock_async_session_local
    ):
        """Test http_request_task executes POST request with JSON body."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.HttpClient"
            ) as mock_http_client:
                mock_response = Mock()
                mock_response.status_code = 201
                mock_response.text = '{"created": true}'
                mock_client_instance = AsyncMock()
                mock_client_instance.__aenter__ = AsyncMock(
                    return_value=mock_client_instance
                )
                mock_client_instance.__aexit__ = AsyncMock(return_value=False)
                mock_client_instance.post = AsyncMock(return_value=mock_response)
                mock_http_client.return_value = mock_client_instance

                result = await http_request_task(
                    {},
                    "https://api.example.com/comics",
                    "POST",
                    operation_id=str(TEST_OPERATION_ID),
                    platform="gcd",
                    json_data={"title": "Test Comic"},
                )

        assert result["success"] is True
        assert result["status_code"] == 201
        assert result["content"] == '{"created": true}'
        mock_client_instance.post.assert_called_once()
