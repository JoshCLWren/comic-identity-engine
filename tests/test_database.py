"""Tests for database connection and session management."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(scope="module", autouse=True)
def set_database_url():
    """Set DATABASE_URL before importing database module."""
    old_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost/test_db"
    yield
    if old_url:
        os.environ["DATABASE_URL"] = old_url
    else:
        os.environ.pop("DATABASE_URL", None)


from comic_identity_engine.database import (  # noqa: E402 - Import after env var set
    ASYNC_DATABASE_URL,
    DATABASE_URL,
    AsyncSessionLocal,
    Base,
    async_engine,
    get_db,
    test_database_connection,
)


class TestDatabaseConfiguration:
    """Tests for database engine configuration."""

    def test_database_url_exists(self):
        """Test DATABASE_URL is defined."""
        assert DATABASE_URL is not None
        assert "postgresql://" in DATABASE_URL

    def test_async_database_url_exists(self):
        """Test ASYNC_DATABASE_URL is defined."""
        assert ASYNC_DATABASE_URL is not None
        assert "asyncpg" in ASYNC_DATABASE_URL

    def test_async_engine_exists(self):
        """Test async_engine is defined."""
        assert async_engine is not None

    def test_session_factory_exists(self):
        """Test AsyncSessionLocal is defined."""
        assert AsyncSessionLocal is not None


class TestGetDb:
    """Tests for get_db dependency injection."""

    @pytest.mark.asyncio
    async def test_get_db_yields_session(self):
        """Test get_db yields a session."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.close = AsyncMock()

        with patch(
            "comic_identity_engine.database.AsyncSessionLocal"
        ) as mock_session_local:
            mock_session_local.return_value.__aenter__.return_value = mock_session

            async for session in get_db():
                assert session is mock_session
                break

    @pytest.mark.asyncio
    async def test_get_db_closes_session_on_success(self):
        """Test get_db closes session after successful use."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.close = AsyncMock()

        with patch(
            "comic_identity_engine.database.AsyncSessionLocal"
        ) as mock_session_local:
            mock_session_local.return_value.__aenter__.return_value = mock_session

            async for _ in get_db():
                pass

            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_db_closes_session_on_exception(self):
        """Test get_db closes session even if exception occurs."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.close = AsyncMock()

        with patch(
            "comic_identity_engine.database.AsyncSessionLocal"
        ) as mock_session_local:
            mock_session_local.return_value.__aenter__.return_value = mock_session
            mock_session_local.return_value.__aexit__.return_value = None

            gen = get_db()
            await gen.__anext__()
            with pytest.raises(ValueError):
                await gen.athrow(ValueError("Test error"))
            await gen.aclose()

            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_db_context_manager_pattern(self):
        """Test get_db works as async context manager."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.close = AsyncMock()

        with patch(
            "comic_identity_engine.database.AsyncSessionLocal"
        ) as mock_session_local:
            mock_session_local.return_value.__aenter__.return_value = mock_session

            session_gen = get_db()
            session = await session_gen.__anext__()
            assert session is mock_session
            await session_gen.aclose()
            mock_session.close.assert_called_once()


class TestDatabaseConnection:
    """Tests for database connection testing."""

    @pytest.mark.asyncio
    async def test_test_database_connection_success(self):
        """Test test_database_connection returns True on success."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_session.execute.return_value = mock_result

        with patch(
            "comic_identity_engine.database.AsyncSessionLocal"
        ) as mock_session_local:
            mock_session_local.return_value.__aenter__.return_value = mock_session

            result = await test_database_connection()
            assert result is True
            mock_session.execute.assert_called_once()
            call_args = mock_session.execute.call_args[0][0]
            assert "SELECT 1" in str(call_args)

    @pytest.mark.asyncio
    async def test_test_database_connection_failure(self):
        """Test test_database_connection returns False on failure."""
        with patch(
            "comic_identity_engine.database.AsyncSessionLocal"
        ) as mock_session_local:
            mock_session_local.return_value.__aenter__.side_effect = Exception(
                "Connection failed"
            )

            result = await test_database_connection()
            assert result is False

    @pytest.mark.asyncio
    async def test_test_database_connection_query_error(self):
        """Test test_database_connection returns False on query error."""
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("Query failed")

        with patch(
            "comic_identity_engine.database.AsyncSessionLocal"
        ) as mock_session_local:
            mock_session_local.return_value.__aenter__.return_value = mock_session

            result = await test_database_connection()
            assert result is False

    @pytest.mark.asyncio
    async def test_test_database_connection_session_cleanup(self):
        """Test test_database_connection properly closes session."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_session.execute.return_value = mock_result

        with patch(
            "comic_identity_engine.database.AsyncSessionLocal"
        ) as mock_session_local:
            context_manager = MagicMock()
            context_manager.__aenter__.return_value = mock_session
            context_manager.__aexit__.return_value = None
            mock_session_local.return_value = context_manager

            await test_database_connection()
            context_manager.__aenter__.assert_called_once()
            context_manager.__aexit__.assert_called_once()


class TestBase:
    """Tests for Base ORM class."""

    def test_base_is_declarative(self):
        """Test Base is a DeclarativeBase."""

        assert isinstance(Base, type)
        assert hasattr(Base, "registry")

    def test_base_metadata(self):
        """Test Base has metadata attribute."""
        assert hasattr(Base, "metadata")


class TestDatabaseUrlRedaction:
    """Tests for URL redaction in logs."""

    def test_database_url_redaction(self):
        """Test database URL can be redacted."""
        from sqlalchemy.engine import make_url

        test_url = "postgresql://user:password@localhost/test_db"
        redacted_url = make_url(test_url).render_as_string(hide_password=True)
        assert "***" in redacted_url
        assert "password" not in redacted_url

    def test_async_database_url_redaction(self):
        """Test async database URL can be redacted."""
        from sqlalchemy.engine import make_url

        test_url = "postgresql+asyncpg://user:password@localhost/test_db"
        redacted_url = make_url(test_url).render_as_string(hide_password=True)
        assert "***" in redacted_url
        assert "password" not in redacted_url


@pytest.mark.asyncio
class TestDatabaseIntegration:
    """Integration tests for database operations."""

    async def test_get_db_with_real_session_usage(self):
        """Test get_db with simulated real session usage."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = {"id": 1, "name": "test"}
        mock_session.execute.return_value = mock_result

        with patch(
            "comic_identity_engine.database.AsyncSessionLocal"
        ) as mock_session_local:
            mock_session_local.return_value.__aenter__.return_value = mock_session

            async for session in get_db():
                result = await session.execute(MagicMock())
                data = result.scalar_one_or_none()
                assert data == {"id": 1, "name": "test"}
                break

            mock_session_local.return_value.__aenter__.assert_called_once()
