"""Tests for URL builder service placeholder.

These tests verify the current placeholder behavior until authoritative
source URLs are persisted on external mappings.
"""

import uuid
from unittest.mock import AsyncMock

import pytest

from comic_identity_engine.services.url_builder import (
    SUPPORTED_PLATFORMS,
    build_urls,
    build_url_for_platform,
    get_all_platform_urls,
)


@pytest.fixture
def mock_session():
    """Create mock database session."""
    return AsyncMock()


@pytest.mark.asyncio
class TestBuildUrls:
    """Tests for build_urls function placeholder behavior."""

    async def test_build_urls_returns_empty_for_regular_platforms(self, mock_session):
        """Regular platforms return empty strings until URL storage is fixed."""
        result = await build_urls(uuid.uuid4(), ["gcd", "locg", "ccl"], mock_session)

        assert result["gcd"] == ""
        assert result["locg"] == ""
        assert result["ccl"] == ""

    async def test_build_urls_clz_platform(self, mock_session):
        """CLZ platform returns N/A message since it's CSV-only."""
        result = await build_urls(uuid.uuid4(), ["clz"], mock_session)

        assert "clz" in result
        assert "CSV import only" in result["clz"]

    async def test_build_urls_unsupported_platform(self, mock_session):
        """Unsupported platforms are skipped."""
        result = await build_urls(uuid.uuid4(), ["unsupported"], mock_session)

        assert "unsupported" not in result

    async def test_build_urls_empty_sources_list(self, mock_session):
        """Empty sources list raises ValueError."""
        with pytest.raises(ValueError, match="sources list cannot be empty"):
            await build_urls(uuid.uuid4(), [], mock_session)

    async def test_build_urls_none_issue_id(self, mock_session):
        """None issue_id raises ValueError."""
        with pytest.raises(ValueError, match="issue_id is required"):
            await build_urls(None, ["gcd"], mock_session)  # type: ignore[arg-type]


@pytest.mark.asyncio
class TestBuildUrlForPlatform:
    """Tests for build_url_for_platform function."""

    async def test_build_url_for_platform_returns_none_for_regular_platforms(
        self, mock_session
    ):
        """Regular platforms return None until URL storage is fixed."""
        url = await build_url_for_platform(uuid.uuid4(), "gcd", mock_session)

        assert url is None

    async def test_build_url_for_platform_clz_returns_message(self, mock_session):
        """CLZ platform returns the N/A message through build_url_for_platform."""
        url = await build_url_for_platform(uuid.uuid4(), "clz", mock_session)

        # CLZ returns the N/A message which is truthy, so it's returned as-is
        assert url == "N/A (CLZ is CSV import only)"

    async def test_build_url_for_platform_invalid_platform(self, mock_session):
        """Invalid platform raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported platform"):
            await build_url_for_platform(uuid.uuid4(), "invalid", mock_session)

    async def test_build_url_for_platform_none_platform(self, mock_session):
        """None platform raises ValueError."""
        with pytest.raises(ValueError, match="platform is required"):
            await build_url_for_platform(uuid.uuid4(), None, mock_session)  # type: ignore[arg-type]


@pytest.mark.asyncio
class TestGetAllPlatformUrls:
    """Tests for get_all_platform_urls function."""

    async def test_get_all_platform_urls(self, mock_session):
        """All supported platforms are included in result."""
        urls = await get_all_platform_urls(uuid.uuid4(), mock_session)

        assert len(urls) == len(SUPPORTED_PLATFORMS)
        for platform in SUPPORTED_PLATFORMS:
            assert platform in urls

    async def test_get_all_platform_urls_includes_clz_message(self, mock_session):
        """CLZ URL includes message about CSV import."""
        urls = await get_all_platform_urls(uuid.uuid4(), mock_session)

        assert "CSV import only" in urls["clz"]

    async def test_get_all_platform_urls_regular_platforms_empty(self, mock_session):
        """Regular platforms return empty strings until URL storage is fixed."""
        urls = await get_all_platform_urls(uuid.uuid4(), mock_session)

        for platform in ["gcd", "locg", "ccl", "aa", "cpg", "hip"]:
            assert urls[platform] == ""


class TestSupportedPlatforms:
    """Tests for SUPPORTED_PLATFORMS constant."""

    def test_supported_platforms_includes_all_expected(self):
        """All expected platforms are supported."""
        expected = {"gcd", "locg", "ccl", "aa", "cpg", "hip", "clz"}
        assert SUPPORTED_PLATFORMS == expected
