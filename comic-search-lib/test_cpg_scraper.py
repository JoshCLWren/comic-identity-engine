#!/usr/bin/env python3
"""Test script for CPG scraper."""

import asyncio
import sys

# Add parent directory to path for imports
sys.path.insert(0, "/mnt/extra/josh/code/comic-search-lib")

from comic_search_lib.scrapers.cpg import CPGScraper


async def test_cpg_scraper():
    """Test the CPG scraper with a simple search."""
    print("Testing CPG Scraper...")

    scraper = CPGScraper(timeout=30)

    try:
        # Test with X-Men #1 (1963)
        print("\nTest 1: Searching for X-Men #1 (1963)")
        result = await scraper.search_comic(title="X-Men", issue="1", year=1963)

        print(f"  Has results: {result.has_results}")
        print(f"  Number of listings: {len(result.listings)}")
        print(f"  Number of prices: {len(result.prices)}")

        if result.has_results:
            print("\n  First 3 listings:")
            for i, listing in enumerate(result.listings[:3], 1):
                print(f"    {i}. {listing.store}: {listing.price} ({listing.grade})")
                if listing.url:
                    print(f"       URL: {listing.url}")
        else:
            print("  No results found (this may be expected if CPG is down)")

        # Test with Amazing Spider-Man #1
        print("\nTest 2: Searching for Amazing Spider-Man #1")
        result2 = await scraper.search_comic(
            title="Amazing Spider-Man", issue="1", year=1963
        )

        print(f"  Has results: {result2.has_results}")
        print(f"  Number of listings: {len(result2.listings)}")

        if result2.has_results:
            print("\n  First 3 listings:")
            for i, listing in enumerate(result2.listings[:3], 1):
                print(f"    {i}. {listing.store}: {listing.price} ({listing.grade})")
        else:
            print("  No results found (this may be expected if CPG is down)")

        print("\n✓ CPG Scraper test completed successfully")
        return True

    except Exception as e:
        print(f"\n✗ Error testing CPG scraper: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_cpg_scraper())
    sys.exit(0 if success else 1)
