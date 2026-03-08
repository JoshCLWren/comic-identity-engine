"""Tests configuration."""

import pytest
import asyncio


@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def sample_comic():
    """Sample comic for testing."""
    from comic_search_lib.models import Comic

    return Comic(
        id="test-1",
        title="X-Men",
        issue="1",
        year=1991,
        publisher="Marvel",
    )
