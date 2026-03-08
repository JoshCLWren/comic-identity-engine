#!/usr/bin/env python3
"""Simple demo of comic-search-lib."""

import asyncio
from comic_search_lib import ComicSearchClient
from comic_search_lib.models.comic import Comic


async def main():
    """Demo the comic search library."""
    print("=" * 60)
    print("Comic Search Library Demo")
    print("=" * 60)

    # Create a client
    async with ComicSearchClient() as client:
        # Search for a popular comic
        comic = Comic(
            id="demo-asm-300",
            title="Amazing Spider-Man",
            issue="300",
            year=1988,
            publisher="Marvel",
        )

        print(f"\n🔍 Searching for: {comic.title} #{comic.issue} ({comic.year})")
        print("-" * 60)

        # Search all platforms
        results = await client.search_all(comic)

        # Display results
        print("\n📊 RESULTS BY PLATFORM:")
        print("-" * 60)

        for platform, result in results.items():
            print(f"\n{platform.upper()}:")
            print(f"  Listings: {len(result.listings)}")
            print(f"  Prices: {len(result.prices)}")

            if result.listings:
                print(f"\n  Top 3 listings:")
                for i, listing in enumerate(result.listings[:3], 1):
                    print(f"    {i}. {listing.store}")
                    print(f"       Price: {listing.price}")
                    if listing.grade:
                        print(f"       Grade: {listing.grade}")
                    if listing.url:
                        print(f"       URL: {listing.url[:80]}...")
            elif result.url:
                print(f"  URL: {result.url}")

        # Show summary
        print("\n" + "=" * 60)
        print("📈 SUMMARY:")
        print("-" * 60)
        summary = client.get_summary(results)
        print(f"Platforms searched: {summary['platforms_searched']}")
        print(f"Platforms with results: {summary['platforms_with_results']}")
        print(f"Total listings: {summary['total_listings']}")
        print(f"Total prices: {summary['total_prices']}")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
