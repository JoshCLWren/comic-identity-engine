"""Test AA scraper with debug logging."""

import asyncio
import logging

logging.basicConfig(
    level=logging.DEBUG, format="%(name)s - %(levelname)s - %(message)s"
)

from comic_search_lib import AtomicAvenueScraper


async def main():
    scraper = AtomicAvenueScraper(timeout=30.0)

    result = await scraper.search_comic(
        title="X-Men",
        issue="1",
        year=1991,
        publisher="Marvel",
    )

    print(f"\n=== RESULTS ===")
    print(f"Has results: {result.has_results}")
    print(f"URL: {result.url}")
    print(f"Source issue ID: {result.source_issue_id}")


if __name__ == "__main__":
    asyncio.run(main())
