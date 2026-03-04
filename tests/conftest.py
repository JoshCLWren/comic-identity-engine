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
