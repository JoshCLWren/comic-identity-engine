"""Tests for League of Comic Geeks scraper."""

import pytest
from comic_search_lib.models.comic import Comic
from comic_search_lib.scrapers.locg import LoCGScraper


@pytest.mark.asyncio
async def test_locg_scraper_initialization():
    """Test that LoCG scraper initializes correctly."""
    scraper = LoCGScraper(timeout=30)
    assert scraper.timeout == 30
    await scraper.close()


@pytest.mark.asyncio
async def test_locg_scraper_context_manager():
    """Test that LoCG scraper works as async context manager."""
    async with LoCGScraper() as scraper:
        assert scraper is not None
        assert scraper.timeout == 30


@pytest.mark.asyncio
async def test_locg_search_comic_dict():
    """Test searching with dict input."""
    scraper = LoCGScraper()

    comic_dict = {
        "title": "X-Men",
        "issue": "1",
        "year": 1963,
        "publisher": "Marvel",
    }

    result = await scraper.search_comic(comic_dict)

    assert result is not None
    assert result.comic.title == "X-Men"
    assert result.comic.issue == "1"
    assert result.comic.year == 1963

    await scraper.close()


@pytest.mark.asyncio
async def test_locg_search_comic_object():
    """Test searching with Comic object."""
    scraper = LoCGScraper()

    comic = Comic(
        id="test-xmen-1",
        title="X-Men",
        issue="1",
        year=1963,
        publisher="Marvel",
    )

    result = await scraper.search_comic(comic)

    assert result is not None
    assert result.comic.title == "X-Men"
    assert result.comic.issue == "1"

    await scraper.close()


@pytest.mark.asyncio
async def test_locg_scraper_finds_results():
    """Test that LoCG scraper can find results for a popular comic."""
    scraper = LoCGScraper()

    comic = Comic(
        id="test-xmen-1",
        title="X-Men",
        issue="1",
        year=1963,
        publisher="Marvel",
    )

    result = await scraper.search_comic(comic)

    assert result is not None
    assert result.comic.title == "X-Men"
    assert result.comic.issue == "1"

    print(f"\nListings found: {len(result.listings)}")
    print(f"Prices found: {len(result.prices)}")

    if result.listings:
        print(f"\nFirst listing:")
        print(f"  Store: {result.listings[0].store}")
        print(f"  Title: {result.listings[0].title}")
        print(f"  URL: {result.listings[0].url}")

    await scraper.close()
