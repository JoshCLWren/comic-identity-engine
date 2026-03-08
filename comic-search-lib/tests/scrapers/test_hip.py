"""Tests for HipComics scraper."""

import pytest
from comic_search_lib.models.comic import Comic
from comic_search_lib.scrapers.hip import HipScraper


@pytest.mark.asyncio
async def test_hip_scraper_initialization():
    """Test that HIP scraper initializes correctly."""
    scraper = HipScraper(timeout=30)
    assert scraper.timeout == 30
    assert scraper._max_retries == 3
    await scraper.close()


@pytest.mark.asyncio
async def test_hip_scraper_context_manager():
    """Test that HIP scraper works as async context manager."""
    async with HipScraper() as scraper:
        assert scraper is not None
        assert scraper.timeout == 30


@pytest.mark.asyncio
async def test_hip_search_comic_dict():
    """Test searching with dict input."""
    scraper = HipScraper()

    comic_dict = {
        "title": "Amazing Spider-Man",
        "issue": "300",
        "year": 1988,
        "publisher": "Marvel",
    }

    result = await scraper.search_comic(comic_dict)

    assert result is not None
    assert result.comic.title == "Amazing Spider-Man"
    assert result.comic.issue == "300"
    assert result.comic.year == 1988

    await scraper.close()


@pytest.mark.asyncio
async def test_hip_search_comic_object():
    """Test searching with Comic object."""
    scraper = HipScraper()

    comic = Comic(
        id="test-asm-300",
        title="Amazing Spider-Man",
        issue="300",
        year=1988,
        publisher="Marvel",
    )

    result = await scraper.search_comic(comic)

    assert result is not None
    assert result.comic.title == "Amazing Spider-Man"
    assert result.comic.issue == "300"

    await scraper.close()


@pytest.mark.asyncio
async def test_hip_scraper_finds_results():
    """Test that HIP scraper can find results for a popular comic."""
    scraper = HipScraper()

    comic = Comic(
        id="test-asm-300",
        title="Amazing Spider-Man",
        issue="300",
        year=1988,
        publisher="Marvel",
    )

    result = await scraper.search_comic(comic)

    assert result is not None
    assert result.comic.title == "Amazing Spider-Man"
    assert result.comic.issue == "300"

    print(f"\nListings found: {len(result.listings)}")
    print(f"Prices found: {len(result.prices)}")

    if result.listings:
        print(f"\nFirst listing:")
        print(f"  Store: {result.listings[0].store}")
        print(f"  Title: {result.listings[0].title}")
        print(f"  Price: {result.listings[0].price}")
        print(f"  URL: {result.listings[0].url}")

    await scraper.close()


@pytest.mark.asyncio
async def test_hip_parse_price():
    """Test price parsing."""
    scraper = HipScraper()

    assert scraper._parse_price("$10.00") == 10.0
    assert scraper._parse_price("10.00") == 10.0
    assert scraper._parse_price("$5.99") == 5.99
    assert scraper._parse_price("Free") == 0.0
    assert scraper._parse_price("") == 0.0

    await scraper.close()


@pytest.mark.asyncio
async def test_hip_find_years():
    """Test year extraction from listing data."""
    scraper = HipScraper()

    data = {
        "name": "Amazing Spider-Man #300 1988",
        "description": "Published in 1988",
    }

    years = scraper._find_years(data)
    assert 1988 in years

    await scraper.close()
