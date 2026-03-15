"""Tests for GCD scraper."""

import pytest
from comic_search_lib.scrapers.gcd import GCDScraper


@pytest.mark.asyncio
async def test_gcd_scraper_initialization():
    """Test that GCDScraper can be initialized."""
    scraper = GCDScraper(timeout=30)
    assert scraper.timeout == 30
    assert scraper.BASE_URL == "https://www.comics.org"
    assert scraper.API_BASE == "https://www.comics.org/api"


@pytest.mark.asyncio
async def test_gcd_scraper_search_xmen_1963():
    """Test GCD scraper search for X-Men #1 (1963)."""
    scraper = GCDScraper(timeout=30)

    result = await scraper.search_comic(
        title="X-Men",
        issue="1",
        year=1963,
        publisher="Marvel",
    )

    assert result is not None
    assert result.comic is not None
    assert result.comic.title == "X-Men"
    assert result.comic.issue == "1"
    assert result.comic.year == 1963
    assert result.comic.publisher == "Marvel"

    # GCD should return results for this well-known comic
    # Note: GCD is a database, not a marketplace, so results represent catalog entries
    if result.has_results:
        print("\n=== GCD RESULTS ===")
        print(f"Has results: {result.has_results}")
        print(f"URL: {result.url}")
        print(f"Listings found: {len(result.listings)}")
        for listing in result.listings[:3]:
            print(f"  - {listing.title} | {listing.url}")

    assert isinstance(result.listings, list)
    assert isinstance(result.prices, list)


@pytest.mark.asyncio
async def test_gcd_scraper_search_no_year():
    """Test GCD scraper search without year parameter."""
    scraper = GCDScraper(timeout=30)

    result = await scraper.search_comic(
        title="Amazing Spider-Man",
        issue="1",
    )

    assert result is not None
    assert result.comic is not None
    assert result.comic.title == "Amazing Spider-Man"
    assert result.comic.issue == "1"
    assert result.comic.year is None

    assert isinstance(result.listings, list)
    assert isinstance(result.prices, list)


@pytest.mark.asyncio
async def test_gcd_scraper_extract_issue_id_from_url():
    """Test issue ID extraction from GCD URLs."""
    scraper = GCDScraper(timeout=30)

    # Test valid URLs
    assert (
        scraper._extract_issue_id_from_url("https://www.comics.org/issue/125295/")
        == "125295"
    )
    assert (
        scraper._extract_issue_id_from_url("https://www.comics.org/issue/12345/")
        == "12345"
    )
    assert scraper._extract_issue_id_from_url("/issue/99999/") == "99999"

    # Test invalid URLs
    assert scraper._extract_issue_id_from_url("") == ""
    assert scraper._extract_issue_id_from_url("https://example.com") == ""
    assert (
        scraper._extract_issue_id_from_url("https://www.comics.org/series/123/") == ""
    )


@pytest.mark.asyncio
async def test_gcd_scraper_search_handles_no_results():
    """Test that GCD scraper handles searches with no results gracefully."""
    scraper = GCDScraper(timeout=30)

    # Search for a comic that's unlikely to exist
    result = await scraper.search_comic(
        title="NonExistentComicTitle12345",
        issue="999",
        year=2025,
    )

    assert result is not None
    assert result.comic is not None
    assert result.comic.title == "NonExistentComicTitle12345"

    # Should return empty lists, not crash
    assert isinstance(result.listings, list)
    assert isinstance(result.prices, list)
    # If no results, URL might be None
    if not result.has_results:
        assert result.url is None or result.url == ""


@pytest.mark.asyncio
async def test_gcd_scraper_result_structure():
    """Test that GCD scraper returns properly structured results."""
    scraper = GCDScraper(timeout=30)

    result = await scraper.search_comic(
        title="X-Men",
        issue="1",
        year=1991,
    )

    assert result is not None

    # Check result structure
    assert hasattr(result, "comic")
    assert hasattr(result, "listings")
    assert hasattr(result, "prices")
    assert hasattr(result, "url")
    assert hasattr(result, "has_results")

    # If we have listings, check their structure
    for listing in result.listings:
        assert listing.store == "GCD"
        assert listing.price == "N/A"  # GCD is a database, not a marketplace
        assert listing.store_type == "gcd"
        assert isinstance(listing.title, str)
        assert isinstance(listing.url, str)
        assert "metadata" in listing.__dict__ or hasattr(listing, "metadata")


@pytest.mark.asyncio
async def test_gcd_scraper_special_issue_numbers():
    """Test GCD scraper with special issue numbers like -1."""
    scraper = GCDScraper(timeout=30)

    result = await scraper.search_comic(
        title="X-Men",
        issue="-1",
        year=1997,
    )

    assert result is not None
    assert result.comic.issue == "-1"
    assert isinstance(result.listings, list)
