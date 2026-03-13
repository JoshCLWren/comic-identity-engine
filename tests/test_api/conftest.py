"""Pytest configuration for API tests."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

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
from comic_identity_engine.jobs.queue import JobQueue
from comic_identity_engine.services.operations import OperationsManager


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

    app.dependency_overrides[get_job_queue] = override_get_job_queue
    app.dependency_overrides[get_operations_manager] = override_get_operations_manager

    return app


@pytest_asyncio.fixture
async def client(
    app_with_overrides: FastAPI,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Fixture to provide httpx.AsyncClient for testing."""
    transport = ASGITransport(app=app_with_overrides)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as _client:
        yield _client
