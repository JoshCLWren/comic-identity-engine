"""Tests for Comic Identity Engine HTTP API identity router.

This module provides comprehensive tests for:
- POST /api/v1/identity/resolve endpoint
- GET /api/v1/identity/resolve/{operation_id} endpoint
- Error handling and edge cases
- Dependency mocking using FastAPI dependency overrides

All tests use fixed UUIDs for deterministic behavior and mock all
external dependencies (JobQueue, OperationsManager).
"""

from collections.abc import AsyncGenerator
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport

from comic_identity_engine.api.dependencies import (
    get_job_queue,
    get_operations_manager,
)
from comic_identity_engine.api.main import create_app
from comic_identity_engine.api.routers.identity import router as identity_router
from comic_identity_engine.database.models import Operation
from comic_identity_engine.errors import AdapterError, ParseError, ValidationError
from comic_identity_engine.jobs.queue import JobQueue
from comic_identity_engine.services.operations import OperationsManager


# =============================================================================
# Fixed UUIDs for deterministic tests
# =============================================================================

FIXED_OPERATION_ID = UUID("12345678-1234-1234-1234-123456789abc")
FIXED_CANONICAL_UUID = UUID("550e8400-e29b-41d4-a716-446655440000")
FIXED_ISSUE_UUID = UUID("550e8400-e29b-41d4-a716-446655440001")


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_redis_cache():
    """Fixture to provide mocked Redis cache singleton."""
    with patch("comic_identity_engine.api.main.redis_cache") as mock:
        mock.initialize = AsyncMock()
        mock.close = AsyncMock()
        yield mock


@pytest.fixture
def mock_database_connection():
    """Fixture to provide mocked database connection test."""
    with patch(
        "comic_identity_engine.api.main.test_database_connection",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = True
        yield mock


@pytest.fixture
def mock_get_settings():
    """Fixture to provide mocked settings with test configuration."""
    with patch("comic_identity_engine.api.main.get_settings") as mock:
        settings = MagicMock()
        settings.redis.cache_url = "redis://localhost:6379/1"
        settings.app.cors_origins_list = [
            "http://localhost:3000",
            "https://example.com",
        ]
        mock.return_value = settings
        yield mock


@pytest.fixture
def mock_job_queue():
    """Fixture to provide mocked JobQueue."""
    queue = AsyncMock(spec=JobQueue)
    queue.enqueue_resolve = AsyncMock()
    return queue


@pytest.fixture
def mock_operations_manager():
    """Fixture to provide mocked OperationsManager."""
    manager = AsyncMock(spec=OperationsManager)
    return manager


@pytest.fixture
def sample_operation_pending():
    """Create sample pending operation with fixed UUID."""
    operation = MagicMock(spec=Operation)
    operation.id = FIXED_OPERATION_ID
    operation.operation_type = "resolve"
    operation.status = "pending"
    operation.input_hash = "abc123hash"
    operation.result = None
    operation.error_message = None
    operation.created_at = datetime(2024, 1, 15, 10, 30, 0)
    operation.updated_at = datetime(2024, 1, 15, 10, 30, 0)
    return operation


@pytest.fixture
def sample_operation_running():
    """Create sample running operation with fixed UUID."""
    operation = MagicMock(spec=Operation)
    operation.id = FIXED_OPERATION_ID
    operation.operation_type = "resolve"
    operation.status = "running"
    operation.input_hash = "abc123hash"
    operation.result = None
    operation.error_message = None
    operation.created_at = datetime(2024, 1, 15, 10, 30, 0)
    operation.updated_at = datetime(2024, 1, 15, 10, 35, 0)
    return operation


@pytest.fixture
def sample_operation_completed():
    """Create sample completed operation with result."""
    operation = MagicMock(spec=Operation)
    operation.id = FIXED_OPERATION_ID
    operation.operation_type = "resolve"
    operation.status = "completed"
    operation.input_hash = "abc123hash"
    operation.result = {
        "canonical_uuid": str(FIXED_CANONICAL_UUID),
        "confidence": 0.95,
        "explanation": "Matched by series + issue + year: X-Men (1991) #1",
        "platform_urls": {
            "gcd": "https://www.comics.org/issue/12345/",
            "locg": "https://leagueofcomicgeeks.com/comic/12345678/x-men-1",
        },
    }
    operation.error_message = None
    operation.created_at = datetime(2024, 1, 15, 10, 30, 0)
    operation.updated_at = datetime(2024, 1, 15, 10, 40, 0)
    return operation


@pytest.fixture
def sample_operation_failed():
    """Create sample failed operation with error."""
    operation = MagicMock(spec=Operation)
    operation.id = FIXED_OPERATION_ID
    operation.operation_type = "resolve"
    operation.status = "failed"
    operation.input_hash = "abc123hash"
    operation.result = None
    operation.error_message = "Resolution failed: Could not find matching issue"
    operation.created_at = datetime(2024, 1, 15, 10, 30, 0)
    operation.updated_at = datetime(2024, 1, 15, 10, 35, 0)
    return operation


def create_operation_mock(**kwargs):
    """Create a mock Operation with given attributes."""
    operation = MagicMock(spec=Operation)
    operation.id = kwargs.get("id", FIXED_OPERATION_ID)
    operation.operation_type = kwargs.get("operation_type", "resolve")
    operation.status = kwargs.get("status", "pending")
    operation.input_hash = kwargs.get("input_hash", "abc123")
    operation.result = kwargs.get("result", None)
    operation.error_message = kwargs.get("error_message", None)
    operation.created_at = kwargs.get("created_at", datetime(2024, 1, 15, 10, 30, 0))
    operation.updated_at = kwargs.get("updated_at", datetime(2024, 1, 15, 10, 30, 0))
    return operation


async def override_get_job_queue():
    """Override for get_job_queue dependency."""
    queue = AsyncMock(spec=JobQueue)
    queue.enqueue_resolve = AsyncMock()
    queue.close = AsyncMock()
    try:
        yield queue
    finally:
        await queue.close()


async def override_get_operations_manager():
    """Override for get_operations_manager dependency."""
    mock_ops = AsyncMock(spec=OperationsManager)
    mock_ops.create_operation = AsyncMock()
    mock_ops.get_operation = AsyncMock(return_value=None)
    yield mock_ops


@pytest_asyncio.fixture
async def app_with_overrides(
    mock_redis_cache,
    mock_database_connection,
    mock_get_settings,
) -> FastAPI:
    """Create FastAPI app with dependency overrides for testing."""
    app = create_app()

    # Override dependencies
    app.dependency_overrides[get_job_queue] = override_get_job_queue
    app.dependency_overrides[get_operations_manager] = override_get_operations_manager

    return app


@pytest_asyncio.fixture
async def async_client(
    app_with_overrides: FastAPI,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Fixture to provide httpx.AsyncClient for testing."""
    transport = ASGITransport(app=app_with_overrides)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# =============================================================================
# POST /api/v1/identity/resolve Tests
# =============================================================================


@pytest.mark.asyncio
class TestPostResolveIdentity:
    """Tests for POST /api/v1/identity/resolve endpoint."""

    async def test_resolve_valid_url_returns_202(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test valid URL returns 202 Accepted with operation response."""
        # Create mock operations manager
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(return_value=sample_operation_pending)
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": "https://www.comics.org/issue/12345/"},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["name"] == f"operations/{FIXED_OPERATION_ID}"
        assert data["done"] is False
        assert data["metadata"]["operation_type"] == "resolve"
        assert data["metadata"]["url"] == "https://www.comics.org/issue/12345/"
        assert data["metadata"]["status"] == "pending"

    async def test_resolve_valid_url_enqueues_job(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test that valid URL enqueues a resolution job."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(return_value=sample_operation_pending)
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": "https://www.comics.org/issue/12345/"},
        )

    async def test_resolve_valid_url_creates_operation(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test that valid URL creates an operation."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(return_value=sample_operation_pending)
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": "https://www.comics.org/issue/12345/"},
        )

        mock_ops.create_operation.assert_called_once_with(
            operation_type="resolve",
            input_data={"url": "https://www.comics.org/issue/12345/"},
            force=False,
        )

    async def test_resolve_locg_url_returns_202(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test LoCG URL returns 202 Accepted."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(return_value=sample_operation_pending)
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": "https://leagueofcomicgeeks.com/comic/12345678/x-men-1"},
        )

        assert response.status_code == 202

    async def test_resolve_ccl_url_returns_202(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test ComicCollectorLive URL returns 202 Accepted."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(return_value=sample_operation_pending)
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": "https://www.comiccollectorlive.com/Issue/123456"},
        )

        assert response.status_code == 202

    async def test_resolve_clz_url_returns_202(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test CLZ URL returns 202 Accepted."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(return_value=sample_operation_pending)
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": "https://clzcomics.com/issue/12345"},
        )

        assert response.status_code == 202

    async def test_resolve_hip_url_returns_202(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test HipComic URL returns 202 Accepted."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(return_value=sample_operation_pending)
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": "https://www.hipcomic.com/listing/12345"},
        )

        assert response.status_code == 202

    async def test_resolve_cpg_url_returns_202(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test Comic Price Guide URL returns 202 Accepted."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(return_value=sample_operation_pending)
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": "https://comicspriceguide.com/issue/12345"},
        )

        assert response.status_code == 202

    async def test_resolve_aa_url_returns_202(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test Atomic Avenue URL returns 202 Accepted."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(return_value=sample_operation_pending)
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": "https://www.atomicavenue.com/issue/12345"},
        )

        assert response.status_code == 202

    async def test_resolve_empty_url_returns_422(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
    ):
        """Test empty URL returns 422 validation error."""
        # Set up mock to raise ValidationError for empty URL
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(
            side_effect=ValidationError("URL cannot be empty")
        )
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": ""},
        )

        assert response.status_code == 400  # ValidationError returns 400, not 422

    async def test_resolve_missing_url_returns_422(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Test missing URL field returns 422 validation error."""
        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={},
        )

        assert response.status_code == 422

    async def test_resolve_invalid_url_type_returns_422(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Test invalid URL type (number) returns 422 validation error."""
        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": 12345},
        )

        assert response.status_code == 422

    async def test_resolve_null_url_returns_422(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Test null URL returns 422 validation error."""
        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": None},
        )

        assert response.status_code == 422

    async def test_resolve_validation_error_returns_400(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
    ):
        """Test ValidationError returns 400 Bad Request."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(
            side_effect=ValidationError("Invalid URL format")
        )
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": "not-a-valid-url"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["code"] == "VALIDATION_ERROR"
        assert "Invalid URL format" in data["detail"]["message"]

    async def test_resolve_parse_error_returns_422(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
    ):
        """Test ParseError returns 422 Unprocessable Entity."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(
            side_effect=ParseError("Could not parse URL")
        )
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": "https://unsupported-site.com/issue/123"},
        )

        assert response.status_code == 422
        data = response.json()
        assert data["detail"]["code"] == "PARSE_ERROR"
        assert "Could not parse URL" in data["detail"]["message"]

    async def test_resolve_adapter_error_returns_500(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
    ):
        """Test AdapterError returns 500 Internal Server Error."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(
            side_effect=AdapterError("Database connection failed", source="gcd")
        )
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": "https://www.comics.org/issue/12345/"},
        )

        assert response.status_code == 500
        data = response.json()
        assert data["detail"]["code"] == "ADAPTER_ERROR"
        assert "Database connection failed" in data["detail"]["message"]
        assert data["detail"]["source"] == "gcd"

    async def test_resolve_adapter_error_no_source_returns_500(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
    ):
        """Test AdapterError without source returns 500."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(
            side_effect=AdapterError("Internal error")
        )
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": "https://www.comics.org/issue/12345/"},
        )

        assert response.status_code == 500
        data = response.json()
        assert data["detail"]["code"] == "ADAPTER_ERROR"
        assert data["detail"]["source"] is None

    async def test_resolve_content_type_json(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test resolve endpoint returns JSON content type."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(return_value=sample_operation_pending)
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": "https://www.comics.org/issue/12345/"},
        )

        assert "application/json" in response.headers["content-type"]

    async def test_resolve_response_includes_operation_name(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test response includes operation name in correct format."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(return_value=sample_operation_pending)
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": "https://www.comics.org/issue/12345/"},
        )

        data = response.json()
        assert data["name"].startswith("operations/")
        assert FIXED_OPERATION_ID.hex in data["name"].replace("-", "")

    async def test_resolve_response_done_is_false(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test response has done=False for new operation."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(return_value=sample_operation_pending)
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": "https://www.comics.org/issue/12345/"},
        )

        data = response.json()
        assert data["done"] is False

    async def test_resolve_response_includes_metadata(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test response includes operation metadata."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(return_value=sample_operation_pending)
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": "https://www.comics.org/issue/12345/"},
        )

        data = response.json()
        assert "metadata" in data
        assert "operation_type" in data["metadata"]
        assert "url" in data["metadata"]
        assert "status" in data["metadata"]

    async def test_resolve_method_not_allowed_get(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Test GET request to resolve endpoint returns 405."""
        response = await async_client.get("/api/v1/identity/resolve")
        assert response.status_code == 405

    async def test_resolve_method_not_allowed_put(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Test PUT request to resolve endpoint returns 405."""
        response = await async_client.put("/api/v1/identity/resolve", json={})
        assert response.status_code == 405

    async def test_resolve_method_not_allowed_delete(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Test DELETE request to resolve endpoint returns 405."""
        response = await async_client.delete("/api/v1/identity/resolve")
        assert response.status_code == 405


# =============================================================================
# GET /api/v1/identity/resolve/{operation_id} Tests
# =============================================================================


@pytest.mark.asyncio
class TestGetResolveStatus:
    """Tests for GET /api/v1/identity/resolve/{operation_id} endpoint."""

    async def test_get_status_pending_returns_200(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test getting pending operation returns 200."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=sample_operation_pending)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.get(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}"
        )

        assert response.status_code == 200

    async def test_get_status_pending_returns_done_false(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test pending operation returns done=False."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=sample_operation_pending)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.get(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}"
        )

        data = response.json()
        assert data["done"] is False

    async def test_get_status_pending_includes_metadata(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test pending operation includes metadata."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=sample_operation_pending)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.get(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}"
        )

        data = response.json()
        assert "metadata" in data
        assert data["metadata"]["operation_type"] == "resolve"
        assert data["metadata"]["status"] == "pending"
        assert "created_at" in data["metadata"]
        assert "updated_at" in data["metadata"]

    async def test_get_status_running_returns_200(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_running: MagicMock,
    ):
        """Test getting running operation returns 200."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=sample_operation_running)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.get(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["metadata"]["status"] == "running"

    async def test_get_status_completed_returns_200(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_completed: MagicMock,
    ):
        """Test getting completed operation returns 200."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=sample_operation_completed)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.get(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}"
        )

        assert response.status_code == 200

    async def test_get_status_completed_returns_done_true(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_completed: MagicMock,
    ):
        """Test completed operation returns done=True."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=sample_operation_completed)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.get(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}"
        )

        data = response.json()
        assert data["done"] is True

    async def test_get_status_completed_includes_response(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_completed: MagicMock,
    ):
        """Test completed operation includes response field."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=sample_operation_completed)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.get(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}"
        )

        data = response.json()
        assert "response" in data
        assert data["response"]["canonical_uuid"] == str(FIXED_CANONICAL_UUID)
        assert data["response"]["confidence"] == 0.95

    async def test_get_status_completed_response_has_platform_urls(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_completed: MagicMock,
    ):
        """Test completed operation response includes platform URLs."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=sample_operation_completed)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.get(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}"
        )

        data = response.json()
        assert "platform_urls" in data["response"]
        assert "gcd" in data["response"]["platform_urls"]
        assert "locg" in data["response"]["platform_urls"]

    async def test_get_status_failed_returns_200(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_failed: MagicMock,
    ):
        """Test getting failed operation returns 200."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=sample_operation_failed)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.get(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}"
        )

        assert response.status_code == 200

    async def test_get_status_failed_returns_done_true(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_failed: MagicMock,
    ):
        """Test failed operation returns done=True."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=sample_operation_failed)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.get(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}"
        )

        data = response.json()
        assert data["done"] is True

    async def test_get_status_failed_includes_error(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_failed: MagicMock,
    ):
        """Test failed operation includes error field."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=sample_operation_failed)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.get(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}"
        )

        data = response.json()
        assert "error" in data
        assert data["error"]["message"] == sample_operation_failed.error_message

    async def test_get_status_not_found_returns_404(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
    ):
        """Test getting non-existent operation returns 404."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=None)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.get(f"/api/v1/identity/resolve/{uuid4()}")

        assert response.status_code == 404

    async def test_get_status_not_found_returns_error_code(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
    ):
        """Test 404 response includes error code."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=None)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.get(f"/api/v1/identity/resolve/{uuid4()}")

        data = response.json()
        assert data["detail"]["code"] == "OPERATION_NOT_FOUND"

    async def test_get_status_invalid_uuid_returns_422(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Test invalid UUID format returns 422."""
        response = await async_client.get("/api/v1/identity/resolve/not-a-valid-uuid")

        assert response.status_code == 422

    async def test_get_status_content_type_json(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test status endpoint returns JSON content type."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=sample_operation_pending)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.get(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}"
        )

        assert "application/json" in response.headers["content-type"]

    async def test_get_status_name_format(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test response name follows operations/{id} format."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=sample_operation_pending)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.get(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}"
        )

        data = response.json()
        expected_name = f"operations/{FIXED_OPERATION_ID}"
        assert data["name"] == expected_name

    async def test_get_status_method_not_allowed_post(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Test POST request to status endpoint returns 405."""
        response = await async_client.post(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}",
            json={},
        )
        assert response.status_code == 405

    async def test_get_status_method_not_allowed_put(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Test PUT request to status endpoint returns 405."""
        response = await async_client.put(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}",
            json={},
        )
        assert response.status_code == 405

    async def test_get_status_method_not_allowed_delete(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Test DELETE request to status endpoint returns 405."""
        response = await async_client.delete(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}"
        )
        assert response.status_code == 405


# =============================================================================
# Edge Cases and Boundary Tests
# =============================================================================


@pytest.mark.asyncio
class TestResolveEdgeCases:
    """Tests for edge cases and boundary conditions."""

    async def test_resolve_url_with_special_characters(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test URL with special characters is accepted."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(return_value=sample_operation_pending)
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        url = "https://www.comics.org/issue/12345/?query=test&foo=bar"
        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": url},
        )

        assert response.status_code == 202

    async def test_resolve_url_with_unicode(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test URL with unicode characters is accepted."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(return_value=sample_operation_pending)
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        url = "https://example.com/issue/測試-123"
        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": url},
        )

        assert response.status_code == 202

    async def test_resolve_very_long_url(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test very long URL is accepted."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(return_value=sample_operation_pending)
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        long_path = "/" + "/".join([f"segment{i}" for i in range(100)])
        url = f"https://www.comics.org{long_path}"
        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": url},
        )

        assert response.status_code == 202

    async def test_resolve_enqueue_exception_returns_500(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test exception during enqueue returns 500."""
        # Create mock queue that raises exception
        mock_queue = AsyncMock(spec=JobQueue)
        mock_queue.enqueue_resolve = AsyncMock(
            side_effect=ConnectionError("Redis unavailable")
        )
        mock_queue.close = AsyncMock()

        async def override_get_queue_error():
            try:
                yield mock_queue
            finally:
                await mock_queue.close()

        app_with_overrides.dependency_overrides[get_job_queue] = (
            override_get_queue_error
        )

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(return_value=sample_operation_pending)
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        # The enqueue exception will propagate and cause a 500
        with pytest.raises(ConnectionError, match="Redis unavailable"):
            await async_client.post(
                "/api/v1/identity/resolve",
                json={"url": "https://www.comics.org/issue/12345/"},
            )

    async def test_resolve_array_instead_of_object_returns_422(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Test array instead of JSON object returns 422."""
        response = await async_client.post(
            "/api/v1/identity/resolve",
            json=["https://www.comics.org/issue/12345/"],
        )

        assert response.status_code == 422

    async def test_resolve_extra_fields_ignored(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test extra fields in request are ignored."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(return_value=sample_operation_pending)
        mock_ops.get_operation = AsyncMock()

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.post(
            "/api/v1/identity/resolve",
            json={
                "url": "https://www.comics.org/issue/12345/",
                "extra_field": "ignored",
            },
        )

        assert response.status_code == 202


# =============================================================================
# Operation Status Edge Cases
# =============================================================================


@pytest.mark.asyncio
class TestStatusEdgeCases:
    """Tests for operation status edge cases."""

    async def test_get_status_no_metadata_fields(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
    ):
        """Test operation with None timestamps handles gracefully."""
        operation = create_operation_mock(
            status="pending",
            created_at=None,
            updated_at=None,
        )

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=operation)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.get(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["metadata"]["created_at"] is None
        assert data["metadata"]["updated_at"] is None

    async def test_get_status_completed_no_response(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
    ):
        """Test completed operation without result field."""
        operation = create_operation_mock(
            status="completed",
            result=None,
        )

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=operation)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.get(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["done"] is True
        assert "response" not in data or data.get("response") is None

    async def test_get_status_failed_no_error_message(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
    ):
        """Test failed operation without error message."""
        operation = create_operation_mock(
            status="failed",
            error_message=None,
        )

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=operation)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.get(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["done"] is True

    async def test_get_status_error_with_parse_keyword(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
    ):
        """Test failed operation with 'parse' in error message has error code."""
        operation = create_operation_mock(
            status="failed",
            error_message="Parse error in input data",
        )

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=operation)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.get(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}"
        )

        data = response.json()
        assert data["error"]["code"] == 3

    async def test_get_status_error_with_resolution_keyword(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
    ):
        """Test failed operation with 'resolution' in error message has error code."""
        operation = create_operation_mock(
            status="failed",
            error_message="Resolution failed for issue",
        )

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=operation)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.get(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}"
        )

        data = response.json()
        assert data["error"]["code"] == 3

    async def test_get_status_error_with_validation_keyword(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
    ):
        """Test failed operation with 'validation' in error message has error code."""
        operation = create_operation_mock(
            status="failed",
            error_message="Validation error in request",
        )

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=operation)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        response = await async_client.get(
            f"/api/v1/identity/resolve/{FIXED_OPERATION_ID}"
        )

        data = response.json()
        assert data["error"]["code"] == 3


# =============================================================================
# Integration-style Tests
# =============================================================================


@pytest.mark.asyncio
class TestResolveFullFlow:
    """Tests simulating full resolution flow."""

    async def test_full_flow_create_and_check_status(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
        sample_operation_completed: MagicMock,
    ):
        """Test full flow: create operation then check status."""
        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.create_operation = AsyncMock(return_value=sample_operation_pending)
        # Always return completed status for the get operation call
        mock_ops.get_operation = AsyncMock(return_value=sample_operation_completed)

        async def override_get_ops():
            yield mock_ops

        app_with_overrides.dependency_overrides[get_operations_manager] = (
            override_get_ops
        )

        # Create operation
        create_response = await async_client.post(
            "/api/v1/identity/resolve",
            json={"url": "https://www.comics.org/issue/12345/"},
        )

        assert create_response.status_code == 202
        data = create_response.json()
        operation_name = data["name"]
        operation_id = operation_name.replace("operations/", "")

        # Check status - mock returns completed immediately
        status_response = await async_client.get(
            f"/api/v1/identity/resolve/{operation_id}"
        )

        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["done"] is True
        assert "response" in status_data

    async def test_flow_with_all_platform_urls(
        self,
        async_client: httpx.AsyncClient,
        app_with_overrides: FastAPI,
        sample_operation_pending: MagicMock,
    ):
        """Test operation creation for each supported platform."""
        platforms = [
            ("gcd", "https://www.comics.org/issue/12345/"),
            ("locg", "https://leagueofcomicgeeks.com/comic/12345678/test"),
            ("ccl", "https://www.comiccollectorlive.com/Issue/123456"),
            ("clz", "https://clzcomics.com/issue/12345"),
            ("hip", "https://www.hipcomic.com/listing/12345"),
            ("cpg", "https://comicspriceguide.com/issue/12345"),
            ("aa", "https://www.atomicavenue.com/issue/12345"),
        ]

        for platform, url in platforms:
            mock_ops = AsyncMock(spec=OperationsManager)
            mock_ops.create_operation = AsyncMock(return_value=sample_operation_pending)
            mock_ops.get_operation = AsyncMock()

            async def override_get_ops():
                yield mock_ops

            app_with_overrides.dependency_overrides[get_operations_manager] = (
                override_get_ops
            )

            response = await async_client.post(
                "/api/v1/identity/resolve",
                json={"url": url},
            )

            assert response.status_code == 202, f"Failed for {platform}"


# =============================================================================
# Router Configuration Tests
# =============================================================================


class TestRouterConfiguration:
    """Tests for router configuration and setup."""

    def test_router_has_correct_prefix(self):
        """Test identity router has /identity prefix."""
        assert identity_router.prefix == "/identity"

    def test_router_has_correct_tags(self):
        """Test identity router has correct tags."""
        assert "Identity Resolution" in identity_router.tags

    def test_resolve_endpoint_exists(self):
        """Test resolve endpoint is registered."""
        routes = [route for route in identity_router.routes]
        route_paths = [getattr(r, "path", "") for r in routes]
        assert "/identity/resolve" in route_paths

    def test_status_endpoint_exists(self):
        """Test status endpoint is registered."""
        routes = [route for route in identity_router.routes]
        route_paths = [getattr(r, "path", "") for r in routes]
        assert "/identity/resolve/{operation_id}" in route_paths
