"""Tests for URL builder service."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from comic_identity_engine.services.url_builder import (
    build_urls,
    build_url_for_platform,
    get_all_platform_urls,
)


@pytest.fixture
def mock_session():
    """Create mock database session."""
    return AsyncMock()


@pytest.fixture
def sample_mappings():
    """Create sample external mappings."""
    issue_id = uuid.uuid4()

    mappings = []
    platforms_data = [
        ("gcd", "4254", "125295"),
        ("locg", "111275", "1169529"),
        ("ccl", "x-men-1991", "98ab98c9-a87a-4cd2-b49a-ee5232abc0ad"),
        ("aa", "217254", "217255"),
        ("cpg", "x-men", "phvpiu"),
        ("hip", "x-men-1991", "1-1"),
    ]

    for source, series_id, issue_id in platforms_data:
        mapping = MagicMock()
        mapping.issue_id = issue_id
        mapping.source = source
        mapping.source_series_id = series_id
        mapping.source_issue_id = issue_id
        mappings.append(mapping)

    return mappings


@pytest.mark.asyncio
class TestBuildUrls:
    """Tests for build_urls function."""

    @patch("comic_identity_engine.services.url_builder.ExternalMappingRepository")
    async def test_build_urls_single_platform(
        self, mock_repo_cls, mock_session, sample_mappings
    ):
        """Test building URL for single platform."""
        mock_repo = MagicMock()
        mock_repo.find_by_issue = AsyncMock(return_value=[sample_mappings[0]])
        mock_repo_cls.return_value = mock_repo

        result = await build_urls(uuid.uuid4(), ["gcd"], mock_session)

        assert "gcd" in result
        assert result["gcd"] == "https://www.comics.org/issue/125295/"

    @patch("comic_identity_engine.services.url_builder.ExternalMappingRepository")
    async def test_build_urls_multiple_platforms(
        self, mock_repo_cls, mock_session, sample_mappings
    ):
        """Test building URLs for multiple platforms."""
        mock_repo = MagicMock()
        mock_repo.find_by_issue = AsyncMock(return_value=sample_mappings)
        mock_repo_cls.return_value = mock_repo

        result = await build_urls(uuid.uuid4(), ["gcd", "locg", "ccl"], mock_session)

        assert len(result) == 3
        assert result["gcd"] == "https://www.comics.org/issue/125295/"
        assert "leagueofcomicgeeks.com" in result["locg"]
        assert "comiccollectorlive.com" in result["ccl"]

    @patch("comic_identity_engine.services.url_builder.ExternalMappingRepository")
    async def test_build_urls_no_mapping(self, mock_repo_cls, mock_session):
        """Test building URL when no mapping exists."""
        mock_repo = MagicMock()
        mock_repo.find_by_issue = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        result = await build_urls(uuid.uuid4(), ["gcd"], mock_session)

        assert "gcd" in result
        assert result["gcd"] == ""

    @patch("comic_identity_engine.services.url_builder.ExternalMappingRepository")
    async def test_build_urls_clz_platform(self, mock_repo_cls, mock_session):
        """Test building URL for CLZ platform returns N/A message."""
        mock_repo = MagicMock()
        mock_repo.find_by_issue = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        result = await build_urls(uuid.uuid4(), ["clz"], mock_session)

        assert "clz" in result
        assert "CSV import only" in result["clz"]

    @patch("comic_identity_engine.services.url_builder.ExternalMappingRepository")
    async def test_build_urls_unsupported_platform(self, mock_repo_cls, mock_session):
        """Test building URL for unsupported platform."""
        mock_repo = MagicMock()
        mock_repo.find_by_issue = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        result = await build_urls(uuid.uuid4(), ["unsupported"], mock_session)

        assert "unsupported" not in result

    async def test_build_urls_empty_sources_list(self, mock_session):
        """Test building URLs with empty sources list raises ValueError."""
        with pytest.raises(ValueError, match="sources list cannot be empty"):
            await build_urls(uuid.uuid4(), [], mock_session)

    async def test_build_urls_none_issue_id(self, mock_session):
        """Test building URLs with None issue_id raises ValueError."""
        with pytest.raises(ValueError, match="issue_id is required"):
            await build_urls(None, ["gcd"], mock_session)


@pytest.mark.asyncio
class TestBuildUrlForPlatform:
    """Tests for build_url_for_platform function."""

    @patch("comic_identity_engine.services.url_builder.ExternalMappingRepository")
    async def test_build_url_for_platform_success(
        self, mock_repo_cls, mock_session, sample_mappings
    ):
        """Test building single platform URL."""
        mock_repo = MagicMock()
        mock_repo.find_by_issue = AsyncMock(return_value=[sample_mappings[0]])
        mock_repo_cls.return_value = mock_repo

        url = await build_url_for_platform(uuid.uuid4(), "gcd", mock_session)

        assert url == "https://www.comics.org/issue/125295/"

    @patch("comic_identity_engine.services.url_builder.ExternalMappingRepository")
    async def test_build_url_for_platform_not_found(self, mock_repo_cls, mock_session):
        """Test building single platform URL when not found."""
        mock_repo = MagicMock()
        mock_repo.find_by_issue = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        url = await build_url_for_platform(uuid.uuid4(), "gcd", mock_session)

        assert url == ""

    async def test_build_url_for_platform_invalid_platform(self, mock_session):
        """Test building URL for invalid platform raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported platform"):
            await build_url_for_platform(uuid.uuid4(), "invalid", mock_session)

    async def test_build_url_for_platform_none_platform(self, mock_session):
        """Test building URL with None platform raises ValueError."""
        with pytest.raises(ValueError, match="platform is required"):
            await build_url_for_platform(uuid.uuid4(), None, mock_session)


@pytest.mark.asyncio
class TestGetAllPlatformUrls:
    """Tests for get_all_platform_urls function."""

    @patch("comic_identity_engine.services.url_builder.ExternalMappingRepository")
    async def test_get_all_platform_urls(
        self, mock_repo_cls, mock_session, sample_mappings
    ):
        """Test getting URLs for all platforms."""
        mock_repo = MagicMock()
        mock_repo.find_by_issue = AsyncMock(return_value=sample_mappings)
        mock_repo_cls.return_value = mock_repo

        urls = await get_all_platform_urls(uuid.uuid4(), mock_session)

        assert len(urls) == 7
        assert "gcd" in urls
        assert "locg" in urls
        assert "ccl" in urls
        assert "aa" in urls
        assert "cpg" in urls
        assert "hip" in urls
        assert "clz" in urls

    @patch("comic_identity_engine.services.url_builder.ExternalMappingRepository")
    async def test_get_all_platform_urls_includes_clz_message(
        self, mock_repo_cls, mock_session, sample_mappings
    ):
        """Test CLZ URL includes message about CSV import."""
        mock_repo = MagicMock()
        mock_repo.find_by_issue = AsyncMock(return_value=sample_mappings)
        mock_repo_cls.return_value = mock_repo

        urls = await get_all_platform_urls(uuid.uuid4(), mock_session)

        assert "CSV import only" in urls["clz"]
