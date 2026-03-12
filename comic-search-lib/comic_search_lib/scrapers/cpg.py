"""
Comics Price Guide (CPG) scraper implementation.

This module provides a scraper for Comics Price Guide that uses the public API
to search for comics and construct direct URLs to issue pages.
"""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from comic_search_lib.browser_pool import browser_page
from comic_search_lib.exceptions import SearchError
from comic_search_lib.models.comic import Comic, SearchResult

logger = logging.getLogger(__name__)


class CPGScraper:
    """
    Scraper for Comics Price Guide (comicspriceguide.com).

    Uses CPG's public API for search and Playwright for fetching issue details.
    """

    BASE_URL = "https://www.comicspriceguide.com"
    SEARCH_API = f"{BASE_URL}/api/Search"

    def __init__(self, timeout: int = 30, profile_dir: Optional[str] = None):
        """
        Initialize the CPGScraper.

        Args:
            timeout (int): Default timeout in seconds for operations
            profile_dir (Optional[str]): Directory for persistent browser profile (deprecated, using browser pool)
        """
        self.timeout = timeout
        self.profile_dir = profile_dir

    async def search_comic(
        self,
        title: str,
        issue: str,
        year: Optional[int] = None,
        publisher: Optional[str] = None,
        url: Optional[str] = None,
    ) -> SearchResult:
        """
        Search for a comic on Comics Price Guide.

        Args:
            title: Comic title
            issue: Issue number
            year: Optional publication year
            publisher: Optional publisher name
            url: Optional direct URL to the issue page

        Returns:
            SearchResult with URL and basic metadata
        """
        comic_id = f"cpg-{title}-{issue}-{year or ''}"
        comic = Comic(
            id=comic_id,
            title=title,
            issue=issue,
            year=year,
            publisher=publisher,
        )

        search_start = asyncio.get_event_loop().time()

        try:
            # If URL is provided, get details directly
            if url:
                details = await self._get_issue_details_from_url(url)
                if details:
                    search_results = [details]
                else:
                    search_results = []
            else:
                # Search using API
                search_results = await self._search_with_api(comic)

            search_result = SearchResult(
                comic=comic,
                listings=[],
                prices=[],
                metadata={
                    "search_time": asyncio.get_event_loop().time() - search_start,
                },
            )

            from comic_search_lib.models.comic import ComicListing

            for item in search_results:
                listing = ComicListing(
                    store="Comics Price Guide",
                    title=item.get("title", f"{title} #{issue}"),
                    price=item.get("price", "Login required"),
                    grade=item.get("grade", ""),
                    url=item.get("url", ""),
                    image_url=item.get("cover_image"),
                    store_type="cpg",
                )
                search_result.listings.append(listing)

            return search_result

        except Exception as e:
            raise SearchError(
                f"Search failed: {e}", source="cpg", original_error=e
            ) from e

    async def _search_with_api(self, comic: Comic) -> List[Dict]:
        """
        Search for a comic using CPG's API.

        Args:
            comic: Comic to search for

        Returns:
            List of search results
        """
        logger.debug(f"Searching CPG API for {comic.title} #{comic.issue}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Don't send year parameter - API filters too aggressively
                params = {
                    "title": comic.title,
                    "issue": str(comic.issue),
                }

                response = await client.get(self.SEARCH_API, params=params)

                if response.status_code != 200:
                    logger.error(f"CPG API returned status {response.status_code}")
                    return []

                data = response.json()

                if not data.get("items"):
                    logger.debug("CPG API returned no items")
                    return []

                results = []

                # Sort results by title similarity to get best match first
                def title_similarity(item_title: str, search_title: str) -> float:
                    """Simple similarity score based on word overlap."""
                    item_words = set(item_title.lower().split())
                    search_words = set(search_title.lower().split())
                    if not search_words:
                        return 0.0
                    overlap = len(item_words & search_words)
                    return overlap / len(search_words)

                # Sort items by title similarity
                sorted_items = sorted(
                    data["items"][:50],
                    key=lambda item: title_similarity(
                        item.get("title", {}).get("name", ""), comic.title
                    ),
                    reverse=True,
                )

                for item in sorted_items[:10]:
                    # Check if issue number matches
                    item_issue = str(item.get("number", ""))
                    comic_issue = str(comic.issue)

                    # Normalize issue numbers for comparison
                    item_issue_norm = item_issue.lstrip("0")
                    comic_issue_norm = comic_issue.lstrip("0")

                    if item_issue_norm != comic_issue_norm:
                        continue

                    # Extract data from API response
                    title_data = item.get("title", {})
                    title_name = title_data.get("name", "")
                    title_seo = title_data.get("nameSEO", "")
                    publisher_name = item.get("publisher", {}).get("name", "")
                    years_str = title_data.get("years", "")

                    # If year provided, check if it falls within the series years
                    if comic.year and years_str:
                        # Parse years range (e.g., "1963-2014")
                        years_match = re.match(r"(\d{4})-(\d{4}|\d{4}s)", years_str)
                        if years_match:
                            start_year = int(years_match.group(1))
                            # If year is outside range, skip this result
                            if comic.year < start_year:
                                continue

                    # Extract resource ID from image URL
                    img_url = item.get("full_img", "")
                    resource_id = self._extract_resource_id(img_url)

                    if not resource_id:
                        logger.debug(f"Could not extract resource ID from {img_url}")
                        continue

                    # Construct direct URL
                    url = (
                        f"{self.BASE_URL}/titles/{title_seo}/{item_issue}/{resource_id}"
                    )

                    result = {
                        "title": f"{title_name} #{item_issue}",
                        "url": url,
                        "price": "Login required",
                        "grade": "",
                        "cover_image": img_url,
                        "publisher": publisher_name,
                        "cover_price": item.get("cover_price", ""),
                        "age": item.get("age", ""),
                    }

                    # Check if key issue
                    if item.get("key"):
                        result["key_issue"] = True

                    results.append(result)

                    # Only return first match
                    if len(results) >= 1:
                        break

                logger.info(
                    f"CPG: Found {len(results)} results for {comic.title} #{comic.issue}"
                )
                return results

        except Exception as e:
            logger.error(f"CPG API search failed: {e}")
            return []

    def _extract_resource_id(self, img_url: str) -> Optional[str]:
        """
        Extract resource ID from CPG image URL.

        Args:
            img_url: Image URL from API

        Returns:
            Resource ID or None
        """
        if not img_url:
            return None

        # Image URLs are like: https://comicspriceguide.com/image/siww/siwxm
        match = re.search(r"/image/([^/]+)/([^/]+?)(?:/thm)?$", img_url)
        if match:
            return match.group(2)

        return None

    async def _get_issue_details_from_url(self, url: str) -> Optional[Dict]:
        """
        Get detailed information from an issue page URL.

        Args:
            url: URL of the issue page

        Returns:
            Dict with issue details or None
        """
        try:
            async with browser_page() as page:
                await page.goto(url, timeout=self.timeout * 1000)
                await asyncio.sleep(2)

            details: Dict[str, Any] = {
                "url": url,
                "price": "Login required",
                "grade": "",
            }

            # Extract data from page text
            page_text = await page.evaluate("() => document.body.innerText")

            # Extract published date
            pub_match = re.search(r"Published\s+(\w+\s+\d{4})", page_text)
            if pub_match:
                details["published"] = pub_match.group(1)

            # Extract comic age
            age_match = re.search(r"Comic Age\s+(\w+)", page_text)
            if age_match:
                details["age"] = age_match.group(1)

            # Extract cover price
            price_match = re.search(r"Cover Price\s+\.?([\d.]+)", page_text)
            if price_match:
                details["cover_price"] = f"${price_match.group(1)}"

            # Check for key issue
            details["key_issue"] = "Key Issue" in page_text

            # Extract cover image
            try:
                cover_img = await page.query_selector('a[href*="/image/"] img')
                if cover_img:
                    cover_link = await cover_img.evaluate("el => el.closest('a')?.href")
                    if cover_link:
                        details["cover_image"] = cover_link
            except Exception:
                pass

            # Extract title from page
            title_match = re.search(r"^(.+)\s+#\d+", page_text, re.MULTILINE)
            if title_match:
                details["title"] = title_match.group(1).strip()

            return details

        except Exception as e:
            logger.debug(f"Error getting issue details from URL: {e}")
            return None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        pass
