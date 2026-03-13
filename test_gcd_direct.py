#!/usr/bin/env python3
"""Test what a real GCD search should look like."""

import aiohttp
import asyncio
from selectolax.lexbor import LexborHTMLParser


async def test_gcd_search():
    """Test GCD search directly."""
    print("\n" + "=" * 80)
    print("🔍 Testing GCD search URLs directly")
    print("=" * 80 + "\n")

    base_url = "https://www.comics.org"

    # Test different search URL formats
    test_urls = [
        # Format 1: Advanced search with series type
        f"{base_url}/search/advanced/?query_type=series&keywords=X-Force&method=icontains",
        # Format 2: With year
        f"{base_url}/search/advanced/?query_type=series&keywords=X-Force&method=icontains&year_begun=1991",
        # Format 3: Simple search
        f"{base_url}/search/?q=X-Force",
        # Format 4: Direct series URL (if we know the series ID)
        # X-Force vol. 1 has series ID 4215
        f"{base_url}/series/4215/",
    ]

    async with aiohttp.ClientSession() as session:
        for i, url in enumerate(test_urls, 1):
            print(f"\n--- Test {i}: {url} ---")
            try:
                async with session.get(url, timeout=30) as resp:
                    resp.raise_for_status()
                    actual_url = str(resp.url)
                    print(f"Actual URL: {actual_url}")

                    html = await resp.text()
                    print(f"Response length: {len(html)} chars")

                    # Try to parse for series links
                    parser = LexborHTMLParser(html)

                    # Look for series links
                    links = parser.css("a[href*='/series/']")
                    print(f"Found {len(links)} series links")
                    if links:
                        for j, link in enumerate(links[:5]):
                            href = link.attributes.get("href", "")
                            text = link.text().strip()[:50]
                            print(f"  {j + 1}. {text} -> {href}")

                    # Look for issue links
                    issue_links = parser.css("a[href*='/issue/']")
                    print(f"Found {len(issue_links)} issue links")
                    if issue_links:
                        for j, link in enumerate(issue_links[:5]):
                            href = link.attributes.get("href", "")
                            text = link.text().strip()[:50]
                            print(f"  {j + 1}. {text} -> {href}")

            except Exception as e:
                print(f"ERROR: {e}")

    print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(test_gcd_search())
