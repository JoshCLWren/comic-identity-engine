"""Tests for the CLZ import router."""

import hashlib
from datetime import datetime, timezone
from pathlib import Path
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
async def test_import_clz_submits_checksum_addressed_operation(tmp_path: Path):
    csv_file = tmp_path / "collection.csv"
    csv_content = (
        "Series,Issue,Publisher,Year,Core ComicID\n"
        "X-Men,1,Marvel,1991,clz-001\n"
    )
    csv_file.write_text(csv_content, encoding="utf-8")

    mock_operation = create_mock_operation(
        status="pending",
        result={"resume_count": 0},
    )
    mock_ops = AsyncMock()
    mock_ops.create_or_resume_import_operation = AsyncMock(
        return_value=(mock_operation, True)
    )

    mock_queue = AsyncMock()
    mock_queue.enqueue_import_clz = AsyncMock()

    app = create_test_app(mock_ops=mock_ops, mock_queue=mock_queue)
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/import/clz",
            json={"file_path": str(csv_file)},
        )

    assert response.status_code == 202
    create_call = mock_ops.create_or_resume_import_operation.await_args.kwargs
    assert create_call["operation_type"] == "import_clz"
    assert create_call["file_checksum"] == hashlib.sha256(
        csv_content.encode("utf-8")
    ).hexdigest()
    assert create_call["initial_result"]["total_rows"] == 1
    assert create_call["initial_result"]["row_manifest"] == [
        {
            "row_index": 1,
            "source_issue_id": "clz-001",
            "row_key": "clz-001:1",
        }
    ]
    mock_queue.enqueue_import_clz.assert_awaited_once_with(
        csv_path=str(csv_file),
        operation_id=mock_operation.id,
    )

    data = response.json()
    assert data["metadata"]["file_checksum"] == create_call["file_checksum"]
    assert data["metadata"]["total_rows"] == 1
    assert data["metadata"]["resume_count"] == 0


@pytest.mark.asyncio
async def test_import_clz_returns_existing_running_operation_without_requeue(
    tmp_path: Path,
):
    csv_file = tmp_path / "collection.csv"
    csv_content = (
        "Series,Issue,Publisher,Year,Core ComicID\n"
        "X-Men,1,Marvel,1991,clz-001\n"
    )
    csv_file.write_text(csv_content, encoding="utf-8")

    mock_operation = create_mock_operation(
        status="running",
        result={"resume_count": 2},
    )
    mock_ops = AsyncMock()
    mock_ops.create_or_resume_import_operation = AsyncMock(
        return_value=(mock_operation, False)
    )

    mock_queue = AsyncMock()
    mock_queue.enqueue_import_clz = AsyncMock()

    app = create_test_app(mock_ops=mock_ops, mock_queue=mock_queue)
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/import/clz",
            json={"file_path": str(csv_file)},
        )

    assert response.status_code == 202
    mock_queue.enqueue_import_clz.assert_not_awaited()
    assert response.json()["metadata"]["resume_count"] == 2
