"""Tests for unified ComicSearchClient."""

import pytest
from comic_search_lib.models.comic import Comic
from comic_search_lib.client import ComicSearchClient


@pytest.mark.asyncio
async def test_client_initialization():
    """Test that client initializes correctly."""
    client = ComicSearchClient(timeout=30)
    assert client.timeout == 30
    assert client._aa_scraper is None
    assert client._hip_scraper is None
    assert client._ccl_scraper is None
    await client.close()


@pytest.mark.asyncio
async def test_client_context_manager():
    """Test that client works as async context manager."""
    async with ComicSearchClient() as client:
        assert client is not None
        assert client.timeout == 30


@pytest.mark.asyncio
async def test_search_all_platforms():
    """Test searching across all platforms."""
    client = ComicSearchClient()

    comic = Comic(
        id="test-asm-300",
        title="Amazing Spider-Man",
        issue="300",
        year=1988,
        publisher="Marvel",
    )

    results = await client.search_all(comic)

    assert results is not None
    assert "atomic_avenue" in results
    assert "hip" in results
    assert "ccl" in results

    print("\n=== Search Results Summary ===")
    for platform, result in results.items():
        print(f"\n{platform.upper()}:")
        print(f"  Listings: {len(result.listings)}")
        print(f"  Prices: {len(result.prices)}")
        if result.listings:
            print(
                f"  First listing: {result.listings[0].store} - {result.listings[0].price}"
            )

    await client.close()


@pytest.mark.asyncio
async def test_get_summary():
    """Test getting summary of search results."""
    client = ComicSearchClient()

    comic = Comic(
        id="test-asm-300",
        title="Amazing Spider-Man",
        issue="300",
        year=1988,
        publisher="Marvel",
    )

    results = await client.search_all(comic)
    summary = client.get_summary(results)

    assert summary["platforms_searched"] == 3
    assert "total_listings" in summary
    assert "total_prices" in summary
    assert "platforms" in summary

    print("\n=== Summary ===")
    print(f"Platforms searched: {summary['platforms_searched']}")
    print(f"Platforms with results: {summary['platforms_with_results']}")
    print(f"Total listings: {summary['total_listings']}")
    print(f"Total prices: {summary['total_prices']}")

    await client.close()


@pytest.mark.asyncio
async def test_search_individual_platforms():
    """Test searching individual platforms."""
    client = ComicSearchClient()

    comic = Comic(
        id="test-asm-300",
        title="Amazing Spider-Man",
        issue="300",
        year=1988,
        publisher="Marvel",
    )

    aa_result = await client.search_atomic_avenue(comic)
    assert aa_result is not None
    assert aa_result.comic.title == "Amazing Spider-Man"

    hip_result = await client.search_hip(comic)
    assert hip_result is not None
    assert hip_result.comic.title == "Amazing Spider-Man"

    ccl_result = await client.search_ccl(comic)
    assert ccl_result is not None
    assert ccl_result.comic.title == "Amazing Spider-Man"

    print("\n=== Individual Platform Results ===")
    print(f"AA: {len(aa_result.listings)} listings")
    print(f"HIP: {len(hip_result.listings)} listings")
    print(f"CCL: {len(ccl_result.listings)} listings")

    await client.close()
