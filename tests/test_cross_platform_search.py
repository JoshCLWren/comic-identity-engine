"""Test cross-platform search integration.

This test verifies that the cross-platform search functionality
correctly searches other platforms after resolving a primary URL.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest


@pytest.mark.asyncio
async def test_cross_platform_search_with_mock_scrapers():
    """Test cross-platform search using mocked scrapers."""
    from comic_identity_engine.database.repositories import (
        ExternalMappingRepository,
        IssueRepository,
        SeriesRunRepository,
    )
    from comic_identity_engine.services import IdentityResolver

    session = AsyncMock()
    resolver = IdentityResolver(session)

    issue_id = uuid.uuid4()
    series_title = "X-Men"
    issue_number = "1"
    year = 1963
    publisher = "Marvel"

    mock_aa_scraper = MagicMock()
    mock_aa_scraper.search_comic = AsyncMock()
    mock_aa_scraper.close = AsyncMock()

    mock_search_result = MagicMock()
    mock_search_result.has_results = True
    mock_search_result.listings = [
        MagicMock(url="https://atomicavenue.com/atomic/item/12345/1/details")
    ]
    mock_aa_scraper.search_comic.return_value = mock_search_result

    def _get_scraper_side_effect(platform):
        if platform == "aa":
            return mock_aa_scraper
        return None

    with patch.object(resolver, "_get_scraper", side_effect=_get_scraper_side_effect):
        with patch.object(resolver.mapping_repo, "create_mapping", AsyncMock()):
            urls = await resolver.search_cross_platform(
                issue_id=issue_id,
                series_title=series_title,
                issue_number=issue_number,
                year=year,
                publisher=publisher,
                skip_platform="gcd",
            )

    assert "aa" in urls
    assert urls["aa"] == "https://atomicavenue.com/atomic/item/12345/1/details"
    mock_aa_scraper.search_comic.assert_called_once_with(
        title=series_title, issue=issue_number, year=year, publisher=publisher
    )
    mock_aa_scraper.close.assert_called_once()


def test_extract_ids_from_url():
    """Test URL parsing for each platform."""
    from comic_identity_engine.services import IdentityResolver

    session = MagicMock()
    resolver = IdentityResolver(session)

    # Test Atomic Avenue
    issue_id, series_id = resolver._extract_ids_from_url(
        "aa", "https://atomicavenue.com/atomic/item/12345/1/details"
    )
    assert issue_id == "12345"
    assert series_id is None

    # Test CCL
    issue_id, series_id = resolver._extract_ids_from_url(
        "ccl",
        "https://www.comiccollectorlive.com/issue/550e8400-e29b-41d4-a716-446655440000/12345",
    )
    assert issue_id == "12345"
    assert series_id == "550e8400-e29b-41d4-a716-446655440000"

    # Test HIP
    issue_id, series_id = resolver._extract_ids_from_url(
        "hip", "https://www.hipcomic.com/price-guide/us/marvel/comic/12345/67890/"
    )
    assert issue_id == "67890"
    assert series_id == "12345"

    # Test invalid URL
    issue_id, series_id = resolver._extract_ids_from_url("aa", "invalid-url")
    assert issue_id is None
    assert series_id is None


@pytest.mark.asyncio
async def test_select_best_listing():
    """Test listing selection from search results."""
    from comic_identity_engine.services import IdentityResolver

    session = MagicMock()
    resolver = IdentityResolver(session)

    mock_search_result = MagicMock()
    mock_listing_1 = MagicMock(url="https://example.com/listing1")
    mock_listing_2 = MagicMock(url=None)
    mock_search_result.listings = [mock_listing_1, mock_listing_2]

    best = resolver._select_best_listing(mock_search_result, "1")
    assert best is not None
    assert best.url == "https://example.com/listing1"

    # Test empty results
    mock_search_result.listings = []
    best = resolver._select_best_listing(mock_search_result, "1")
    assert best is None
