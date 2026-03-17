"""Pytest configuration for Comic Identity Engine tests."""

import os
from unittest.mock import AsyncMock, Mock

import pytest

# Set default DATABASE_URL before any imports
# Prefer TEST_DATABASE_URL for tests, fall back to DATABASE_URL
test_db_url = os.environ.get("TEST_DATABASE_URL")
if test_db_url:
    os.environ.setdefault("DATABASE_URL", test_db_url)
else:
    os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/test_db")


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests that require external services (database, redis, etc.)",
    )


def _is_database_available():
    """Check if database is available for integration tests."""
    test_db_url = os.environ.get("TEST_DATABASE_URL")
    if not test_db_url:
        return False

    try:
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine

        async def check():
            engine = create_async_engine(test_db_url)
            try:
                async with engine.connect():
                    return True
            except Exception:
                return False
            finally:
                await engine.dispose()

        return asyncio.run(check())
    except Exception:
        return False


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
    """Async database session for integration tests.

    Requires database to be available. Tests using this fixture will be skipped
    if the database is not accessible.
    """
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
        try:
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
        except Exception as e:
            pytest.skip(f"Database not available: {e}")
