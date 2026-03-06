#!/usr/bin/env python
"""Quick test script for cross-platform comic search."""

import asyncio
import sys
from comic_search_lib.scrapers.cpg import CPGScraper


async def search_comic(title: str, issue: str, year: int = None):
    """Search for a comic across platforms."""
    scraper = CPGScraper(timeout=60)
    try:
        result = await scraper.search_comic(title=title, issue=issue, year=year)

        if result.listings:
            listing = result.listings[0]
            print(f"✓ Found on CPG:")
            print(f"  Title: {listing.title}")
            print(f"  URL: {listing.url}")
            if listing.image_url:
                print(f"  Image: {listing.image_url}")
            return listing.url
        else:
            print("✗ Not found on CPG")
            return None
    finally:
        await scraper.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_search.py <title> <issue> [year]")
        print("Example: python test_search.py 'X-Men' 81 1963")
        sys.exit(1)

    title = sys.argv[1]
    issue = sys.argv[2]
    year = int(sys.argv[3]) if len(sys.argv) > 3 else None

    asyncio.run(search_comic(title, issue, year))
