"""Tests for the CLZ import router."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from comic_identity_engine.api.dependencies import (
    get_job_queue,
    get_operations_manager,
)
from comic_identity_engine.api.routers.import_router import router


FIXED_UUID = UUID("12345678-1234-1234-1234-123456789abc")


def create_mock_operation(**kwargs):
    """Create a mock operation entity for API tests."""
    operation = MagicMock()
    operation.id = kwargs.get("id", FIXED_UUID)
    operation.operation_type = kwargs.get("operation_type", "import_clz")
    operation.status = kwargs.get("status", "pending")
    operation.result = kwargs.get("result", None)
    operation.error_message = kwargs.get("error_message", None)
    operation.created_at = kwargs.get(
        "created_at", datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    )
    operation.updated_at = kwargs.get(
        "updated_at", datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    )
    return operation


def create_test_app(mock_ops: AsyncMock, mock_queue: AsyncMock) -> FastAPI:
    """Create a lightweight app with dependency overrides for the import router."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def override_get_operations_manager():
        yield mock_ops

    async def override_get_job_queue():
        yield mock_queue

    app.dependency_overrides[get_operations_manager] = override_get_operations_manager
    app.dependency_overrides[get_job_queue] = override_get_job_queue
    return app


@pytest.mark.asyncio
async def test_import_clz_creates_fresh_operation_for_same_path():
    mock_operation = create_mock_operation(status="pending")
    mock_ops = AsyncMock()
    mock_ops.create_operation = AsyncMock(return_value=mock_operation)

    mock_queue = AsyncMock()
    mock_queue.enqueue_import_clz = AsyncMock()

    app = create_test_app(mock_ops=mock_ops, mock_queue=mock_queue)
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/import/clz",
            json={"file_path": "/tmp/collection.csv"},
        )

    assert response.status_code == 202
    mock_ops.create_operation.assert_called_once_with(
        operation_type="import_clz",
        input_data={"csv_path": "/tmp/collection.csv"},
        force=True,
    )
    mock_queue.enqueue_import_clz.assert_awaited_once_with(
        csv_path="/tmp/collection.csv",
        operation_id=mock_operation.id,
    )
