"""Pytest configuration for Comic Identity Engine tests."""

import os
from unittest.mock import AsyncMock, Mock

import pytest

# Set default DATABASE_URL before any imports
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/test_db")


@pytest.fixture
def mock_http_client():
    """Async mock HTTP client for testing."""
    client = AsyncMock()
    client.get = AsyncMock()
    return client


@pytest.fixture
def mock_response():
    """Mock response fixture for HTTP testing."""
    response = AsyncMock()
    response.json = AsyncMock()
    response.raise_for_status = Mock()
    return response


@pytest.fixture
async def db_session():
    """Async database session for integration tests."""
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        create_async_engine,
        async_sessionmaker,
    )
    from sqlalchemy import text

    DATABASE_URL = os.environ.get(
        "DATABASE_URL", "postgresql://user:pass@localhost/test_db"
    )
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

    engine = create_async_engine(ASYNC_DATABASE_URL, echo=False)
    async_session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_factory() as session:
        # Clean up any existing test data before starting
        await session.execute(text("DELETE FROM mapping_corrections"))
        await session.execute(text("DELETE FROM external_mappings"))
        await session.execute(text("DELETE FROM variants"))
        await session.execute(text("DELETE FROM issues"))
        await session.execute(text("DELETE FROM series_runs"))
        await session.commit()

        # Begin transaction for test isolation
        await session.begin()

        yield session

        # Rollback transaction to clean up test data
        await session.rollback()
