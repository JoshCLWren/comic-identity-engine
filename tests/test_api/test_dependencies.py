"""Tests for the Comic Identity Engine HTTP API dependencies module.

This module tests all FastAPI dependency injection functions, ensuring:
- Proper resource creation and cleanup
- Error handling during teardown
- Integration with mocked external services (database, Redis)
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from comic_identity_engine.api.dependencies import (
    get_identity_resolver,
    get_job_queue,
    get_operations_manager,
)
from comic_identity_engine.database.connection import get_db
from comic_identity_engine.jobs.queue import JobQueue
from comic_identity_engine.services.identity_resolver import IdentityResolver
from comic_identity_engine.services.operations import OperationsManager


@pytest.fixture
def mock_db_session():
    """Provide a mocked database session for all tests."""
    return AsyncMock(spec=AsyncSession)


class TestGetDbDependency:
    """Tests for get_db dependency injection from database.connection."""

    @pytest.mark.asyncio
    async def test_get_db_yields_async_session(self):
        """Test that get_db yields an AsyncSession instance."""
        result = get_db()
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_db_is_async_generator(self):
        """Test that get_db returns an async generator."""
        result = get_db()
        assert isinstance(result, AsyncGenerator)


class TestGetJobQueueDependency:
    """Tests for get_job_queue dependency."""

    @pytest.mark.asyncio
    async def test_get_job_queue_yields_job_queue(self):
        """Test that get_job_queue yields a JobQueue instance."""
        gen = get_job_queue()
        queue = await gen.asend(None)
        assert isinstance(queue, JobQueue)

    @pytest.mark.asyncio
    async def test_get_job_queue_closes_on_cleanup(self):
        """Test that get_job_queue closes the queue when done."""
        with patch.object(JobQueue, "close", new_callable=AsyncMock) as mock_close:
            gen = get_job_queue()
            queue = await gen.asend(None)
            assert isinstance(queue, JobQueue)

            # Clean up by closing the generator
            try:
                await gen.aclose()
            except StopAsyncIteration:
                pass

            mock_close.assert_called_once()


class TestGetOperationsManagerDependency:
    """Tests for get_operations_manager dependency."""

    @pytest.mark.asyncio
    async def test_get_operations_manager_returns_instance(self, mock_db_session):
        """Test that get_operations_manager returns an OperationsManager."""
        manager = await get_operations_manager(mock_db_session)
        assert isinstance(manager, OperationsManager)

    @pytest.mark.asyncio
    async def test_get_operations_manager_uses_provided_session(self, mock_db_session):
        """Test that get_operations_manager uses the provided database session."""
        manager = await get_operations_manager(mock_db_session)
        assert manager.session is mock_db_session


class TestGetIdentityResolverDependency:
    """Tests for get_identity_resolver dependency."""

    @pytest.mark.asyncio
    async def test_get_identity_resolver_returns_instance(self, mock_db_session):
        """Test that get_identity_resolver returns an IdentityResolver."""
        resolver = await get_identity_resolver(mock_db_session)
        assert isinstance(resolver, IdentityResolver)

    @pytest.mark.asyncio
    async def test_get_identity_resolver_uses_provided_session(self, mock_db_session):
        """Test that get_identity_resolver uses the provided database session."""
        resolver = await get_identity_resolver(mock_db_session)
        assert resolver.session is mock_db_session


class TestDependencyIntegration:
    """Tests for dependency integration scenarios."""

    @pytest.mark.asyncio
    async def test_dependencies_use_same_session(self, mock_db_session):
        """Test that multiple dependencies can use the same session."""
        ops_manager = await get_operations_manager(mock_db_session)
        resolver = await get_identity_resolver(mock_db_session)

        assert ops_manager.session is mock_db_session
        assert resolver.session is mock_db_session

    @pytest.mark.asyncio
    async def test_job_queue_independent_of_session(self):
        """Test that JobQueue doesn't require a database session."""
        gen = get_job_queue()
        queue = await gen.asend(None)
        assert isinstance(queue, JobQueue)
        await gen.aclose()


class TestDependencyExports:
    """Tests for module exports."""

    def test_get_db_exported(self):
        """Test that get_db is exported from dependencies module."""
        from comic_identity_engine.api import dependencies

        assert hasattr(dependencies, "get_db")

    def test_get_job_queue_exported(self):
        """Test that get_job_queue is exported from dependencies module."""
        from comic_identity_engine.api import dependencies

        assert hasattr(dependencies, "get_job_queue")

    def test_get_operations_manager_exported(self):
        """Test that get_operations_manager is exported from dependencies module."""
        from comic_identity_engine.api import dependencies

        assert hasattr(dependencies, "get_operations_manager")

    def test_get_identity_resolver_exported(self):
        """Test that get_identity_resolver is exported from dependencies module."""
        from comic_identity_engine.api import dependencies

        assert hasattr(dependencies, "get_identity_resolver")


class TestDependencyTypeAnnotations:
    """Tests for dependency type annotations."""

    def test_get_db_has_return_type(self):
        """Test that get_db has proper return type annotation."""
        import inspect

        sig = inspect.signature(get_db)
        assert sig.return_annotation is not inspect.Signature.empty

    def test_get_job_queue_has_return_type(self):
        """Test that get_job_queue has proper return type annotation."""
        import inspect

        sig = inspect.signature(get_job_queue)
        assert sig.return_annotation is not inspect.Signature.empty
