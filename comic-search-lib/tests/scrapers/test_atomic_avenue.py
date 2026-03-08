"""Test AA scraper with corrected parsing."""

import pytest
from comic_search_lib import AtomicAvenueScraper


@pytest.mark.asyncio
async def test_aa_scraper_finds_results():
    """Test that scraper actually finds results."""
    scraper = AtomicAvenueScraper(timeout=30.0)

    result = await scraper.search_comic(
        title="X-Men",
        issue="1",
        year=1991,
        publisher="Marvel",
    )

    print("\n=== RESULTS ===")
    print(f"Has results: {result.has_results}")
    print(f"URL: {result.url}")
    print(f"Source issue ID: {result.source_issue_id}")

    # The key assertion - we should get a URL
    assert result.url is not None, "Should have found at least one series URL"
    assert result.has_results, "Should have results"
