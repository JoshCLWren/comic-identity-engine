"""Tests for CPG scraper."""

import pytest
from comic_search_lib.scrapers.cpg import CPGScraper


@pytest.mark.asyncio
async def test_cpg_scraper_initialization():
    """Test that CPGScraper can be initialized."""
    scraper = CPGScraper(timeout=30)
    assert scraper.timeout == 30
    assert scraper.BASE_URL == "https://comicspriceguide.com"


@pytest.mark.asyncio
async def test_cpg_scraper_search_no_results():
    """Test CPG scraper search when API returns no results (expected for broken API)."""
    scraper = CPGScraper(timeout=30)

    # CPG API is currently broken, so we expect empty results
    # but the scraper should not crash
    result = await scraper.search_comic(title="X-Men", issue="1", year=1963)

    assert result is not None
    assert result.comic is not None
    assert result.comic.title == "X-Men"
    assert result.comic.issue == "1"
    assert result.comic.year == 1963
    # API is broken, so we don't expect results
    assert isinstance(result.listings, list)
    assert isinstance(result.prices, list)


@pytest.mark.asyncio
async def test_cpg_scraper_search_with_publisher():
    """Test CPG scraper search with publisher parameter."""
    scraper = CPGScraper(timeout=30)

    result = await scraper.search_comic(
        title="Amazing Spider-Man", issue="1", year=1963, publisher="Marvel"
    )

    assert result is not None
    assert result.comic.title == "Amazing Spider-Man"
    assert result.comic.issue == "1"
    assert result.comic.year == 1963
    assert result.comic.publisher == "Marvel"


@pytest.mark.asyncio
async def test_cpg_parse_price():
    """Test price parsing functionality."""
    scraper = CPGScraper(timeout=30)

    # Test valid price
    assert scraper._parse_price("$10.00") == 10.0
    assert scraper._parse_price("$1,234.56") == 1234.56
    assert scraper._parse_price("5.00") == 5.0

    # Test invalid price
    assert scraper._parse_price("") == 0.0
    assert scraper._parse_price("N/A") == 0.0
    assert scraper._parse_price("Free") == 0.0
