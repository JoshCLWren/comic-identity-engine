"""Demo script for GCD scraper."""

import asyncio
from comic_search_lib import GCDScraper


async def main():
    """Demonstrate GCD scraper functionality."""
    scraper = GCDScraper(timeout=30)

    print("=== GCD Scraper Demo ===\n")

    # Example 1: Search for X-Men #1 (1963)
    print("Example 1: Searching for X-Men #1 (1963)")
    result = await scraper.search_comic(
        title="X-Men",
        issue="1",
        year=1963,
        publisher="Marvel",
    )

    print(f"  Has results: {result.has_results}")
    print(f"  URL: {result.url}")
    print(f"  Listings found: {len(result.listings)}")

    for i, listing in enumerate(result.listings[:3], 1):
        print(f"    {i}. {listing.title}")
        print(f"       URL: {listing.url}")
        print(f"       Price: {listing.price}")
        if listing.metadata:
            print(f"       Issue ID: {listing.metadata.get('issue_id', 'N/A')}")
            print(f"       Series ID: {listing.metadata.get('series_id', 'N/A')}")

    # Example 2: Search for Amazing Spider-Man #1 (1963)
    print("\nExample 2: Searching for Amazing Spider-Man #1 (1963)")
    result = await scraper.search_comic(
        title="Amazing Spider-Man",
        issue="1",
        year=1963,
    )

    print(f"  Has results: {result.has_results}")
    print(f"  Listings found: {len(result.listings)}")

    # Example 3: Search with special issue number
    print("\nExample 3: Searching for X-Men #-1 (1997)")
    result = await scraper.search_comic(
        title="X-Men",
        issue="-1",
        year=1997,
    )

    print(f"  Has results: {result.has_results}")
    print(f"  Listings found: {len(result.listings)}")


if __name__ == "__main__":
    asyncio.run(main())
