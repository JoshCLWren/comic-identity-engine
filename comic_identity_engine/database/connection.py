"""Database connection and session management.

SOURCE: Derived from comic-pile/app/database.py
USAGE:
- SQLAlchemy async engine setup
- Connection pooling for PostgreSQL
- Async session factory for dependency injection
- Base class for ORM models
- Database connection testing

USED BY:
- All database operations
- API endpoints (via dependency injection)
- Tests (via fixtures)
- Alembic migrations
"""

import logging
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from comic_identity_engine.config import get_database_settings

logger = logging.getLogger(__name__)

_db_settings = get_database_settings()

DATABASE_URL = _db_settings.database_url
ASYNC_DATABASE_URL = _db_settings.async_url

_redacted_database_url = make_url(DATABASE_URL).render_as_string(hide_password=True)
_redacted_async_url = make_url(ASYNC_DATABASE_URL).render_as_string(hide_password=True)
logger.info(f"Database URL configured: {_redacted_database_url}")
logger.info(f"Async database URL: {_redacted_async_url}")

async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models.

    All ORM models should inherit from this class.
    """


async def get_db() -> AsyncIterator[AsyncSession]:
    """Get async database session.

    This is the primary dependency injection function for FastAPI endpoints.
    Yields a session that is automatically committed on success and closed after use.

    Yields:
        AsyncSession: Database session for use in dependency injection.

    Example:
        @app.get("/issues/{issue_id}")
        async def get_issue(issue_id: int, db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Issue).where(Issue.id == issue_id))
            return result.scalar_one_or_none()
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def test_database_connection() -> bool:
    """Test database connection.

    Returns:
        True if connection successful, False otherwise.

    Example:
        if await test_database_connection():
            print("Database connection OK")
        else:
            print("Database connection FAILED")
    """
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            return True
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False
