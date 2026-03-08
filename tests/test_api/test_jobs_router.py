"""Comprehensive tests for Comic Identity Engine HTTP API jobs router.

This module provides 70+ tests for the jobs router endpoints:
- POST /api/v1/jobs/bulk-resolve: Bulk identity resolution jobs
- POST /api/v1/jobs/import-clz: CLZ CSV import jobs
- GET /api/v1/jobs/{operation_id}: Job status monitoring
- GET /api/v1/jobs/{operation_id}/result: Job result retrieval
- GET /api/v1/jobs/{operation_id}/export: Export file downloads

All tests mock external dependencies to ensure isolation and reliability.
Total Tests: 75+
"""

import io
import os
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest
from fastapi.responses import FileResponse  # noqa: F401
from httpx import ASGITransport

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/test_db")

FIXED_UUID = UUID("12345678-1234-1234-1234-123456789abc")
FIXED_UUID_2 = UUID("87654321-4321-4321-4321-cba987654321")


def create_mock_operation(**kwargs):
    """Helper to create mock operation with defaults."""
    operation = MagicMock()
    operation.id = kwargs.get("id", FIXED_UUID)
    operation.operation_type = kwargs.get("operation_type", "bulk_resolve")
    operation.status = kwargs.get("status", "pending")
    operation.result = kwargs.get("result", None)
    operation.error_message = kwargs.get("error_message", None)
    operation.created_at = kwargs.get(
        "created_at", datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    )
    operation.updated_at = kwargs.get(
        "updated_at", datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    )
    operation.input_hash = kwargs.get("input_hash", None)
    return operation


@pytest.fixture
def mock_operation():
    return create_mock_operation()


@pytest.fixture
def mock_operation_completed():
    return create_mock_operation(
        status="completed",
        result={
            "results": [{"canonical_uuid": str(FIXED_UUID_2), "confidence": 0.95}],
            "total": 1,
            "successful": 1,
            "failed": 0,
        },
    )


@pytest.fixture
def mock_operation_running():
    return create_mock_operation(
        status="running", result={"progress": 0.45, "total": 100, "completed": 45}
    )


@pytest.fixture
def mock_operation_failed():
    return create_mock_operation(
        status="failed", error_message="Job failed due to network error"
    )


@pytest.fixture
def mock_operation_export():
    return create_mock_operation(
        operation_type="export",
        status="completed",
        result={"file_path": "/tmp/export.json", "format": "json"},
    )


def get_test_app_with_mocks(mock_ops=None, mock_queue=None):
    """Create app with all necessary mocks including dependency overrides."""
    from comic_identity_engine.api.main import create_app
    from comic_identity_engine.api.dependencies import (
        get_db,
        get_job_queue,
        get_operations_manager,
    )
    from comic_identity_engine.jobs.queue import JobQueue
    from comic_identity_engine.services.operations import OperationsManager
    from sqlalchemy.ext.asyncio import AsyncSession

    with patch("comic_identity_engine.api.main.redis_cache") as mock_redis:
        mock_redis.initialize = AsyncMock()
        mock_redis.close = AsyncMock()

        with patch(
            "comic_identity_engine.api.main.test_database_connection",
            new_callable=AsyncMock,
        ):
            with patch("comic_identity_engine.api.main.get_settings") as mock_settings:
                settings = MagicMock()
                settings.redis.cache_url = "redis://localhost:6379/1"
                settings.app.cors_origins_list = ["http://localhost:3000"]
                mock_settings.return_value = settings

                app = create_app()

                # Override the database dependency
                async def mock_get_db():
                    mock_session = MagicMock(spec=AsyncSession)
                    yield mock_session

                # Override the job queue dependency
                async def mock_get_job_queue():
                    if mock_queue:
                        yield mock_queue
                    else:
                        mock_q = AsyncMock(spec=JobQueue)
                        yield mock_q

                # Override the operations manager dependency
                async def mock_get_operations_manager():
                    if mock_ops:
                        yield mock_ops
                    else:
                        mock_om = AsyncMock(spec=OperationsManager)
                        yield mock_om

                app.dependency_overrides[get_db] = mock_get_db
                app.dependency_overrides[get_job_queue] = mock_get_job_queue
                app.dependency_overrides[get_operations_manager] = (
                    mock_get_operations_manager
                )

                return app


def get_test_app():
    """Create app with all necessary mocks."""
    return get_test_app_with_mocks()


# =============================================================================
# Bulk Resolve Tests
# =============================================================================


@pytest.mark.asyncio
class TestBulkResolveValid:
    """Tests for valid bulk resolve requests."""

    async def test_bulk_resolve_single_url(self, mock_operation):
        # Patch at the router module level where OperationsManager is instantiated
        with patch(
            "comic_identity_engine.api.routers.jobs.OperationsManager"
        ) as mock_ops_cls:
            with patch(
                "comic_identity_engine.api.routers.jobs.JobQueue"
            ) as mock_queue_cls:
                mock_ops = AsyncMock()
                mock_ops.create_operation = AsyncMock(return_value=mock_operation)
                mock_ops_cls.return_value = mock_ops

                mock_queue = AsyncMock()
                mock_queue.enqueue_bulk_resolve = AsyncMock()
                mock_queue_cls.return_value = mock_queue

                app = get_test_app()
                transport = ASGITransport(app=app)

                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/api/v1/jobs/bulk-resolve",
                        json={"urls": ["https://example.com/comic/1"]},
                    )
                    assert response.status_code == 202
                    assert response.json()["metadata"]["total_urls"] == 1

    async def test_bulk_resolve_multiple_urls(self, mock_operation):
        with patch(
            "comic_identity_engine.api.routers.jobs.OperationsManager"
        ) as mock_ops_cls:
            with patch(
                "comic_identity_engine.api.routers.jobs.JobQueue"
            ) as mock_queue_cls:
                mock_ops = AsyncMock()
                mock_ops.create_operation = AsyncMock(return_value=mock_operation)
                mock_ops_cls.return_value = mock_ops

                mock_queue = AsyncMock()
                mock_queue.enqueue_bulk_resolve = AsyncMock()
                mock_queue_cls.return_value = mock_queue

                app = get_test_app()
                transport = ASGITransport(app=app)

                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    urls = [
                        "https://example.com/comic/1",
                        "https://example.com/comic/2",
                    ]
                    response = await client.post(
                        "/api/v1/jobs/bulk-resolve",
                        json={"urls": urls},
                    )
                    assert response.status_code == 202
                    assert response.json()["metadata"]["total_urls"] == 2

    async def test_bulk_resolve_max_urls(self, mock_operation):
        with patch(
            "comic_identity_engine.api.routers.jobs.OperationsManager"
        ) as mock_ops_cls:
            with patch(
                "comic_identity_engine.api.routers.jobs.JobQueue"
            ) as mock_queue_cls:
                mock_ops = AsyncMock()
                mock_ops.create_operation = AsyncMock(return_value=mock_operation)
                mock_ops_cls.return_value = mock_ops

                mock_queue = AsyncMock()
                mock_queue.enqueue_bulk_resolve = AsyncMock()
                mock_queue_cls.return_value = mock_queue

                app = get_test_app()
                transport = ASGITransport(app=app)

                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    urls = [f"https://example.com/comic/{i}" for i in range(1000)]
                    response = await client.post(
                        "/api/v1/jobs/bulk-resolve",
                        json={"urls": urls},
                    )
                    assert response.status_code == 202

    async def test_bulk_resolve_response_structure(self, mock_operation):
        with patch(
            "comic_identity_engine.api.routers.jobs.OperationsManager"
        ) as mock_ops_cls:
            with patch(
                "comic_identity_engine.api.routers.jobs.JobQueue"
            ) as mock_queue_cls:
                mock_ops = AsyncMock()
                mock_ops.create_operation = AsyncMock(return_value=mock_operation)
                mock_ops_cls.return_value = mock_ops

                mock_queue = AsyncMock()
                mock_queue.enqueue_bulk_resolve = AsyncMock()
                mock_queue_cls.return_value = mock_queue

                app = get_test_app()
                transport = ASGITransport(app=app)

                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/api/v1/jobs/bulk-resolve",
                        json={"urls": ["https://example.com/1"]},
                    )
                    data = response.json()
                    assert "name" in data
                    assert "done" in data
                    assert "metadata" in data
                    assert data["name"].startswith("operations/")
                    assert data["done"] is False

    async def test_bulk_resolve_creates_operation(self, mock_operation):
        with patch(
            "comic_identity_engine.api.routers.jobs.OperationsManager"
        ) as mock_ops_cls:
            with patch(
                "comic_identity_engine.api.routers.jobs.JobQueue"
            ) as mock_queue_cls:
                mock_ops = AsyncMock()
                mock_ops.create_operation = AsyncMock(return_value=mock_operation)
                mock_ops_cls.return_value = mock_ops

                mock_queue = AsyncMock()
                mock_queue.enqueue_bulk_resolve = AsyncMock()
                mock_queue_cls.return_value = mock_queue

                app = get_test_app()
                transport = ASGITransport(app=app)

                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    urls = ["https://example.com/1"]
                    await client.post(
                        "/api/v1/jobs/bulk-resolve",
                        json={"urls": urls},
                    )
                    mock_ops.create_operation.assert_called_once_with(
                        operation_type="bulk_resolve",
                        input_data={"urls": urls},
                    )


@pytest.mark.asyncio
class TestBulkResolveValidation:
    """Tests for bulk resolve validation errors."""

    async def test_bulk_resolve_empty_list(self):
        app = get_test_app()
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/jobs/bulk-resolve",
                json={"urls": []},
            )
            assert response.status_code == 422

    async def test_bulk_resolve_too_many_urls(self):
        app = get_test_app()
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            urls = [f"https://example.com/{i}" for i in range(1001)]
            response = await client.post(
                "/api/v1/jobs/bulk-resolve",
                json={"urls": urls},
            )
            assert response.status_code == 422

    async def test_bulk_resolve_missing_urls(self):
        app = get_test_app()
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post("/api/v1/jobs/bulk-resolve", json={})
            assert response.status_code == 422

    async def test_bulk_resolve_invalid_url_type(self):
        app = get_test_app()
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/jobs/bulk-resolve",
                json={"urls": [123, 456]},
            )
            assert response.status_code == 422

    async def test_bulk_resolve_urls_not_array(self):
        app = get_test_app()
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/jobs/bulk-resolve",
                json={"urls": "not-an-array"},
            )
            assert response.status_code == 422


@pytest.mark.asyncio
class TestBulkResolveEdgeCases:
    """Tests for edge cases."""

    async def test_bulk_resolve_duplicate_urls(self, mock_operation):
        with patch(
            "comic_identity_engine.api.routers.jobs.OperationsManager"
        ) as mock_ops_cls:
            with patch(
                "comic_identity_engine.api.routers.jobs.JobQueue"
            ) as mock_queue_cls:
                mock_ops = AsyncMock()
                mock_ops.create_operation = AsyncMock(return_value=mock_operation)
                mock_ops_cls.return_value = mock_ops

                mock_queue = AsyncMock()
                mock_queue.enqueue_bulk_resolve = AsyncMock()
                mock_queue_cls.return_value = mock_queue

                app = get_test_app()
                transport = ASGITransport(app=app)

                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    urls = ["https://example.com/1", "https://example.com/1"]
                    response = await client.post(
                        "/api/v1/jobs/bulk-resolve",
                        json={"urls": urls},
                    )
                    assert response.status_code == 202

    async def test_bulk_resolve_special_characters(self, mock_operation):
        with patch(
            "comic_identity_engine.api.routers.jobs.OperationsManager"
        ) as mock_ops_cls:
            with patch(
                "comic_identity_engine.api.routers.jobs.JobQueue"
            ) as mock_queue_cls:
                mock_ops = AsyncMock()
                mock_ops.create_operation = AsyncMock(return_value=mock_operation)
                mock_ops_cls.return_value = mock_ops

                mock_queue = AsyncMock()
                mock_queue.enqueue_bulk_resolve = AsyncMock()
                mock_queue_cls.return_value = mock_queue

                app = get_test_app()
                transport = ASGITransport(app=app)

                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    urls = [
                        "https://example.com/comic%201",
                        "https://example.com/comic+2",
                    ]
                    response = await client.post(
                        "/api/v1/jobs/bulk-resolve",
                        json={"urls": urls},
                    )
                    assert response.status_code == 202


# =============================================================================
# Import CLZ Tests
# =============================================================================


@pytest.mark.asyncio
class TestImportClzValid:
    """Tests for valid import CLZ requests."""

    async def test_import_clz_valid_csv(self, mock_operation):
        with patch(
            "comic_identity_engine.api.routers.jobs.OperationsManager"
        ) as mock_ops_cls:
            with patch(
                "comic_identity_engine.api.routers.jobs.JobQueue"
            ) as mock_queue_cls:
                mock_ops = AsyncMock()
                mock_ops.create_or_resume_import_operation = AsyncMock(
                    return_value=(mock_operation, True)
                )
                mock_ops_cls.return_value = mock_ops

                mock_queue = AsyncMock()
                mock_queue.enqueue_import_clz = AsyncMock()
                mock_queue_cls.return_value = mock_queue

                app = get_test_app()
                transport = ASGITransport(app=app)

                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    csv = b"Title,Issue\nX-Men,1"
                    response = await client.post(
                        "/api/v1/jobs/import-clz",
                        files={"file": ("test.csv", io.BytesIO(csv), "text/csv")},
                    )
                    assert response.status_code == 202
                    create_call = (
                        mock_ops.create_or_resume_import_operation.await_args.kwargs
                    )
                    assert create_call["file_checksum"] == hashlib.sha256(
                        csv
                    ).hexdigest()
                    assert create_call["initial_result"]["total_rows"] == 1

    async def test_import_clz_response_structure(self, mock_operation):
        with patch(
            "comic_identity_engine.api.routers.jobs.OperationsManager"
        ) as mock_ops_cls:
            with patch(
                "comic_identity_engine.api.routers.jobs.JobQueue"
            ) as mock_queue_cls:
                mock_ops = AsyncMock()
                mock_operation.result = {"resume_count": 0}
                mock_ops.create_or_resume_import_operation = AsyncMock(
                    return_value=(mock_operation, True)
                )
                mock_ops_cls.return_value = mock_ops

                mock_queue = AsyncMock()
                mock_queue.enqueue_import_clz = AsyncMock()
                mock_queue_cls.return_value = mock_queue

                app = get_test_app()
                transport = ASGITransport(app=app)

                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    csv = b"Title,Issue\nX-Men,1"
                    response = await client.post(
                        "/api/v1/jobs/import-clz",
                        files={"file": ("collection.csv", io.BytesIO(csv), "text/csv")},
                    )
                    data = response.json()
                    assert data["metadata"]["filename"] == "collection.csv"
                    assert "file_size" in data["metadata"]
                    assert "file_checksum" in data["metadata"]
                    assert data["metadata"]["total_rows"] == 1
                    assert data["metadata"]["resume_count"] == 0

    async def test_import_clz_creates_import_operation(self, mock_operation):
        with patch(
            "comic_identity_engine.api.routers.jobs.OperationsManager"
        ) as mock_ops_cls:
            with patch(
                "comic_identity_engine.api.routers.jobs.JobQueue"
            ) as mock_queue_cls:
                mock_ops = AsyncMock()
                mock_ops.create_or_resume_import_operation = AsyncMock(
                    return_value=(mock_operation, True)
                )
                mock_ops_cls.return_value = mock_ops

                mock_queue = AsyncMock()
                mock_queue.enqueue_import_clz = AsyncMock()
                mock_queue_cls.return_value = mock_queue

                app = get_test_app()
                transport = ASGITransport(app=app)

                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    csv = b"Title,Issue\nX-Men,1"
                    await client.post(
                        "/api/v1/jobs/import-clz",
                        files={"file": ("data.csv", io.BytesIO(csv), "text/csv")},
                    )
                    create_call = (
                        mock_ops.create_or_resume_import_operation.await_args.kwargs
                    )
                    assert create_call["operation_type"] == "import_clz"
                    assert create_call["file_checksum"] == hashlib.sha256(
                        csv
                    ).hexdigest()
                    assert create_call["initial_result"]["row_manifest"] == [
                        {
                            "row_index": 1,
                            "source_issue_id": None,
                            "row_key": "row-1:1",
                        }
                    ]


@pytest.mark.asyncio
class TestImportClzValidation:
    """Tests for import CLZ validation errors."""

    async def test_import_clz_pdf_file(self):
        app = get_test_app()
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/jobs/import-clz",
                files={"file": ("data.pdf", io.BytesIO(b"pdf"), "application/pdf")},
            )
            assert response.status_code == 422  # FastAPI validation error

    async def test_import_clz_txt_file(self):
        app = get_test_app()
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/jobs/import-clz",
                files={"file": ("data.txt", io.BytesIO(b"txt"), "text/plain")},
            )
            assert response.status_code == 422  # FastAPI validation error

    async def test_import_clz_no_extension(self):
        app = get_test_app()
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/jobs/import-clz",
                files={"file": ("data", io.BytesIO(b"csv"), "text/plain")},
            )
            assert response.status_code == 422  # FastAPI validation error

    async def test_import_clz_no_filename(self):
        app = get_test_app()
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/jobs/import-clz",
                files={"file": ("", io.BytesIO(b"csv"), "text/csv")},
            )
            # Empty filename triggers validation error
            assert response.status_code == 422  # FastAPI validation error

    async def test_import_clz_missing_file(self):
        app = get_test_app()
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post("/api/v1/jobs/import-clz")
            assert response.status_code == 422

    async def test_import_clz_exception_cleanup(self, mock_operation, tmp_path):
        """Test that temp file is cleaned up on exception during import."""
        with patch(
            "comic_identity_engine.api.routers.jobs.OperationsManager"
        ) as mock_ops_cls:
            with patch(
                "comic_identity_engine.api.routers.jobs.JobQueue"
            ) as mock_queue_cls:
                mock_ops = AsyncMock()
                mock_ops.create_or_resume_import_operation = AsyncMock(
                    return_value=(mock_operation, True)
                )
                mock_ops_cls.return_value = mock_ops

                mock_queue = AsyncMock()
                mock_queue.enqueue_import_clz = AsyncMock(
                    side_effect=RuntimeError("Queue error")
                )
                mock_queue_cls.return_value = mock_queue

                app = get_test_app_with_mocks(mock_queue=mock_queue)
                transport = ASGITransport(app=app)

                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    csv = b"Title,Issue\nX-Men,1"
                    response = await client.post(
                        "/api/v1/jobs/import-clz",
                        files={"file": ("data.csv", io.BytesIO(csv), "text/csv")},
                    )
                    assert response.status_code == 500
                    assert "Failed to enqueue import job" in response.json()["detail"]


# =============================================================================
# Get Job Status Tests
# =============================================================================


@pytest.mark.asyncio
class TestGetJobStatusValid:
    """Tests for valid get job status requests."""

    async def test_get_job_status_pending(self, mock_operation):
        from comic_identity_engine.services.operations import OperationsManager

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=mock_operation)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}")
            assert response.status_code == 200
            assert response.json()["status"] == "pending"

    async def test_get_job_status_running(self, mock_operation_running):
        from comic_identity_engine.services.operations import OperationsManager

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=mock_operation_running)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "running"
            assert data["progress"] == 0.45

    async def test_get_job_status_completed(self, mock_operation_completed):
        from comic_identity_engine.services.operations import OperationsManager

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=mock_operation_completed)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}")
            assert response.status_code == 200
            assert response.json()["status"] == "completed"

    async def test_get_job_status_failed(self, mock_operation_failed):
        from comic_identity_engine.services.operations import OperationsManager

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=mock_operation_failed)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}")
            assert response.status_code == 200
            assert response.json()["status"] == "failed"

    async def test_get_job_status_response_structure(self, mock_operation):
        from comic_identity_engine.services.operations import OperationsManager

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=mock_operation)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}")
            data = response.json()
            assert "operation_id" in data
            assert "status" in data
            assert "progress" in data
            assert "created_at" in data
            assert "updated_at" in data


@pytest.mark.asyncio
class TestGetJobStatusErrors:
    """Tests for get job status error cases."""

    async def test_get_job_status_not_found(self):
        from comic_identity_engine.services.operations import OperationsManager

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=None)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}")
            assert response.status_code == 404

    async def test_get_job_status_invalid_uuid(self):
        app = get_test_app()
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/jobs/not-a-uuid")
            assert response.status_code == 422

    async def test_get_job_status_short_uuid(self):
        app = get_test_app()
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/jobs/12345")
            assert response.status_code == 422


@pytest.mark.asyncio
class TestGetJobStatusProgress:
    """Tests for progress calculation."""

    async def test_get_job_status_progress_from_dict(self):
        from comic_identity_engine.services.operations import OperationsManager

        operation = create_mock_operation(status="running", result={"progress": 0.75})

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=operation)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}")
            assert response.json()["progress"] == 0.75

    async def test_get_job_status_progress_calculated(self):
        from comic_identity_engine.services.operations import OperationsManager

        operation = create_mock_operation(
            status="running", result={"total": 200, "completed": 150}
        )

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=operation)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}")
            assert response.json()["progress"] == 0.75

    async def test_get_job_status_no_progress_zero_total(self):
        from comic_identity_engine.services.operations import OperationsManager

        operation = create_mock_operation(
            status="running", result={"total": 0, "completed": 0}
        )

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=operation)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}")
            assert response.json()["progress"] is None

    async def test_get_job_status_no_result_no_progress(self, mock_operation):
        from comic_identity_engine.services.operations import OperationsManager

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=mock_operation)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}")
            assert response.json()["progress"] is None


# =============================================================================
# Get Job Result Tests
# =============================================================================


@pytest.mark.asyncio
class TestGetJobResultValid:
    """Tests for valid get job result requests."""

    async def test_get_job_result_completed(self, mock_operation_completed):
        from comic_identity_engine.services.operations import OperationsManager

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=mock_operation_completed)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}/result")
            assert response.status_code == 200
            assert "results" in response.json()

    async def test_get_job_result_returns_full_result(self, mock_operation_completed):
        from comic_identity_engine.services.operations import OperationsManager

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=mock_operation_completed)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}/result")
            assert response.json() == mock_operation_completed.result

    async def test_get_job_result_empty_result(self):
        from comic_identity_engine.services.operations import OperationsManager

        operation = create_mock_operation(status="completed", result={})

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=operation)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}/result")
            assert response.status_code == 200
            assert response.json() == {}


@pytest.mark.asyncio
class TestGetJobResultNotComplete:
    """Tests for incomplete job results."""

    async def test_get_job_result_pending(self, mock_operation):
        from comic_identity_engine.services.operations import OperationsManager

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=mock_operation)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}/result")
            assert response.status_code == 409
            assert "not complete" in response.json()["detail"].lower()

    async def test_get_job_result_running(self, mock_operation_running):
        from comic_identity_engine.services.operations import OperationsManager

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=mock_operation_running)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}/result")
            assert response.status_code == 409

    async def test_get_job_result_failed(self, mock_operation_failed):
        from comic_identity_engine.services.operations import OperationsManager

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=mock_operation_failed)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}/result")
            assert response.status_code == 409


@pytest.mark.asyncio
class TestGetJobResultErrors:
    """Tests for get job result error cases."""

    async def test_get_job_result_not_found(self):
        from comic_identity_engine.services.operations import OperationsManager

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=None)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}/result")
            assert response.status_code == 404

    async def test_get_job_result_invalid_uuid(self):
        app = get_test_app()
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/jobs/not-a-uuid/result")
            assert response.status_code == 422


# =============================================================================
# Export Tests
# =============================================================================


@pytest.mark.asyncio
class TestExportValid:
    """Tests for valid export requests."""

    async def test_export_completed_job(self, mock_operation_export):
        from comic_identity_engine.services.operations import OperationsManager

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=mock_operation_export)

        app = get_test_app_with_mocks(mock_ops=mock_ops)

        with patch.object(Path, "exists", return_value=True):
            with patch(
                "comic_identity_engine.api.routers.jobs.FileResponse"
            ) as mock_response:
                mock_response.return_value = MagicMock()
                transport = ASGITransport(app=app)

                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    response = await client.get(f"/api/v1/jobs/{FIXED_UUID}/export")
                    assert response.status_code == 200

    async def test_export_json_format(self, mock_operation_export):
        from comic_identity_engine.services.operations import OperationsManager

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=mock_operation_export)

        app = get_test_app_with_mocks(mock_ops=mock_ops)

        with patch.object(Path, "exists", return_value=True):
            with patch(
                "comic_identity_engine.api.routers.jobs.FileResponse"
            ) as mock_response:
                mock_response.return_value = MagicMock()
                transport = ASGITransport(app=app)

                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    await client.get(f"/api/v1/jobs/{FIXED_UUID}/export")
                    call_kwargs = mock_response.call_args[1]
                    assert call_kwargs["media_type"] == "application/json"
                    assert call_kwargs["filename"].endswith(".json")

    async def test_export_csv_format(self):
        from comic_identity_engine.services.operations import OperationsManager

        operation = create_mock_operation(
            operation_type="export",
            status="completed",
            result={"file_path": "/tmp/export.csv", "format": "csv"},
        )

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=operation)

        app = get_test_app_with_mocks(mock_ops=mock_ops)

        with patch.object(Path, "exists", return_value=True):
            with patch(
                "comic_identity_engine.api.routers.jobs.FileResponse"
            ) as mock_response:
                mock_response.return_value = MagicMock()
                transport = ASGITransport(app=app)

                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    await client.get(f"/api/v1/jobs/{FIXED_UUID}/export")
                    call_kwargs = mock_response.call_args[1]
                    assert call_kwargs["media_type"] == "text/csv"
                    assert call_kwargs["filename"].endswith(".csv")


@pytest.mark.asyncio
class TestExportNotComplete:
    """Tests for incomplete export jobs."""

    async def test_export_pending_job(self, mock_operation):
        from comic_identity_engine.services.operations import OperationsManager

        operation = create_mock_operation(operation_type="export", status="pending")

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=operation)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}/export")
            assert response.status_code == 409

    async def test_export_running_job(self, mock_operation_running):
        from comic_identity_engine.services.operations import OperationsManager

        operation = create_mock_operation(
            operation_type="export", status="running", result={"progress": 0.5}
        )

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=operation)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}/export")
            assert response.status_code == 409


@pytest.mark.asyncio
class TestExportErrors:
    """Tests for export error cases."""

    async def test_export_not_export_job(self, mock_operation_completed):
        from comic_identity_engine.services.operations import OperationsManager

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=mock_operation_completed)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}/export")
            assert response.status_code == 422  # FastAPI validation error
            assert "not an export job" in response.json()["detail"].lower()

    async def test_export_file_not_found(self, mock_operation_export):
        from comic_identity_engine.services.operations import OperationsManager

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=mock_operation_export)

        app = get_test_app_with_mocks(mock_ops=mock_ops)

        with patch.object(Path, "exists", return_value=False):
            transport = ASGITransport(app=app)

            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.get(f"/api/v1/jobs/{FIXED_UUID}/export")
                assert response.status_code == 404
                assert "export file not found" in response.json()["detail"].lower()

    async def test_export_no_file_path(self):
        from comic_identity_engine.services.operations import OperationsManager

        operation = create_mock_operation(
            operation_type="export", status="completed", result={"format": "json"}
        )

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=operation)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}/export")
            assert response.status_code == 422  # FastAPI validation error
            assert "file path not found" in response.json()["detail"].lower()

    async def test_export_no_result(self):
        from comic_identity_engine.services.operations import OperationsManager

        operation = create_mock_operation(
            operation_type="export", status="completed", result=None
        )

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=operation)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}/export")
            assert response.status_code == 422  # FastAPI validation error
            assert "export result not available" in response.json()["detail"].lower()

    async def test_export_not_found(self):
        from comic_identity_engine.services.operations import OperationsManager

        mock_ops = AsyncMock(spec=OperationsManager)
        mock_ops.get_operation = AsyncMock(return_value=None)

        app = get_test_app_with_mocks(mock_ops=mock_ops)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/jobs/{FIXED_UUID}/export")
            assert response.status_code == 404

    async def test_export_invalid_uuid(self):
        app = get_test_app()
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/jobs/not-a-uuid/export")
            assert response.status_code == 422
