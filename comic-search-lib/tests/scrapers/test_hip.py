"""Tests for HipComics scraper."""

from unittest.mock import AsyncMock

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
        print("\nFirst listing:")
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


def test_select_best_volume_prefers_exact_series_match():
    """Catalog volume matching should pick the exact series over noisy results."""
    scraper = HipScraper()
    comic = Comic(
        id="xmen-minus-one",
        title="X-Men",
        issue="-1",
        year=1997,
        publisher="Marvel",
        series_start_year=1991,
    )
    volumes = [
        {
            "name": "X-Men: The End: Book 1: Dreamers & Demons (2004)",
            "issueCount": 6,
            "startYear": "2004",
            "publisher": {"name": "Marvel"},
            "uri": "/us/marvel/comic/x-men-the-end-2004/",
        },
        {
            "name": "X-Men (1991)",
            "issueCount": 115,
            "startYear": "1991",
            "publisher": {"name": "Marvel"},
            "uri": "/us/marvel/comic/x-men-1991/",
        },
    ]

    selected = scraper._select_best_volume(volumes, comic)

    assert selected is not None
    assert selected["uri"] == "/us/marvel/comic/x-men-1991/"


def test_build_catalog_listing_returns_price_guide_url():
    """Catalog issues should map to canonical Hip price-guide URLs."""
    scraper = HipScraper()
    listing = scraper._build_catalog_listing(
        {
            "@id": "/api/issues/42206",
            "uri": "/us/marvel/comic/x-men-1991/1-1/",
            "issueNumber": "-1",
            "name": "I Had A Dream",
            "suggestedPrice": 9.91,
            "imageUrl": "https://example.invalid/xmen.jpg",
            "volume": {"name": "X-Men (1991)"},
        }
    )

    assert listing["url"] == "https://www.hipcomic.com/price-guide/us/marvel/comic/x-men-1991/1-1/"
    assert listing["price"] == "$9.91"
    assert listing["issue_number"] == "-1"
    assert listing["source_issue_id"] == "42206"


@pytest.mark.asyncio
async def test_search_catalog_api_returns_exact_issue_result():
    """Hip catalog API search should return the exact issue page for #-1."""
    scraper = HipScraper()
    comic = Comic(
        id="xmen-minus-one",
        title="X-Men",
        issue="-1",
        year=1997,
        publisher="Marvel",
        series_start_year=1991,
    )
    fake_client = object()

    scraper._get_catalog_token = AsyncMock(return_value="token")
    scraper._search_catalog_volumes = AsyncMock(
        return_value=[
            {
                "name": "X-Men (1991)",
                "issueCount": 115,
                "startYear": "1991",
                "publisher": {"name": "Marvel"},
                "uri": "/us/marvel/comic/x-men-1991/",
            }
        ]
    )
    scraper._search_catalog_issues = AsyncMock(
        return_value=[
            {
                "@id": "/api/issues/42206",
                "uri": "/us/marvel/comic/x-men-1991/1-1/",
                "issueNumber": "-1",
                "name": "I Had A Dream",
                "suggestedPrice": 9.91,
                "volume": {"name": "X-Men (1991)"},
            }
        ]
    )

    results = await scraper._search_catalog_api(comic, fake_client)  # type: ignore[arg-type]

    assert len(results) == 1
    assert results[0]["url"].endswith("/price-guide/us/marvel/comic/x-men-1991/1-1/")


@pytest.mark.asyncio
async def test_search_catalog_api_checks_later_ranked_volume_candidates():
    """Hip catalog search should keep probing ranked volumes until an exact issue is found."""
    scraper = HipScraper()
    comic = Comic(
        id="xmen-minus-one",
        title="X-Men",
        issue="-1",
        year=1997,
        publisher="Marvel",
    )
    fake_client = object()

    uncanny = {
        "name": "The Uncanny X-Men (1981)",
        "issueCount": 405,
        "startYear": "1981",
        "publisher": {"name": "Marvel"},
        "uri": "/us/marvel/comic/the-uncanny-x-men-1981/",
    }
    xmen = {
        "name": "X-Men (1991)",
        "issueCount": 115,
        "startYear": "1991",
        "publisher": {"name": "Marvel"},
        "uri": "/us/marvel/comic/x-men-1991/",
    }

    scraper._get_catalog_token = AsyncMock(return_value="token")
    scraper._search_catalog_volumes = AsyncMock(return_value=[uncanny, xmen])
    scraper._search_catalog_issues = AsyncMock(
        side_effect=[
            [],
            [
                {
                    "@id": "/api/issues/42206",
                    "uri": "/us/marvel/comic/x-men-1991/1-1/",
                    "issueNumber": "-1",
                    "name": "I Had A Dream",
                    "suggestedPrice": 9.91,
                    "volume": {"name": "X-Men (1991)"},
                }
            ],
        ]
    )

    results = await scraper._search_catalog_api(comic, fake_client)  # type: ignore[arg-type]

    assert len(results) == 1
    assert results[0]["url"].endswith("/price-guide/us/marvel/comic/x-men-1991/1-1/")
