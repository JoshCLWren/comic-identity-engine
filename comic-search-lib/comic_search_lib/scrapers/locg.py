"""
League of Comic Geeks (LoCG) scraper implementation.

This module provides functionality to scrape comic data from League of Comic Geeks,
focusing on finding comic information and marketplace listings.

Note: This scraper uses Playwright for browser automation as LoCG is a JavaScript-heavy site.
"""

import asyncio
import logging
import re
from typing import Any, Dict, List, Union

from playwright.async_api import Page, async_playwright

from comic_search_lib.exceptions import SearchError
from comic_search_lib.models.comic import Comic, SearchResult


logger = logging.getLogger(__name__)


class LoCGScraper:
    """
    Scraper for League of Comic Geeks website.

    This scraper uses Playwright for browser automation as LoCG is JavaScript-heavy.
    """

    BASE_URL = "https://leagueofcomicgeeks.com"
    SEARCH_URL = f"{BASE_URL}/search"

    def __init__(self, timeout: int = 30):
        """
        Initialize the LoCGScraper.

        Args:
            timeout (int): Default timeout in seconds for operations
        """
        self.timeout = timeout
        self._playwright = None
        self._browser = None
        self._context = None

    async def _get_browser_context(self):
        """Get or create browser context."""
        if self._context is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            )
        return self._context

    async def close(self) -> None:
        """Close the browser and cleanup resources."""
        logger.debug("Cleaning up LoCGScraper resources")

        if self._context:
            try:
                await asyncio.wait_for(self._context.close(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Timeout closing browser context")
            except Exception as e:
                logger.debug(f"Error closing context: {e}")
            self._context = None

        if self._browser:
            try:
                await asyncio.wait_for(self._browser.close(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Timeout closing browser")
            except Exception as e:
                logger.error(f"Error closing browser: {e}")
            self._browser = None

        if self._playwright:
            try:
                await asyncio.wait_for(self._playwright.stop(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Timeout stopping playwright")
            except Exception as e:
                logger.error(f"Error stopping playwright: {e}")
            self._playwright = None

    async def search_comic(self, comic: Union[Comic, Dict[str, Any]]) -> SearchResult:
        """
        Search for a single comic on League of Comic Geeks.

        Args:
            comic: The comic to search for, either as a Comic object or a dictionary

        Returns:
            SearchResult: The search result containing listings and prices

        Raises:
            SearchError: If the search fails
        """
        if isinstance(comic, dict):
            comic_id = f"{comic.get('title', '')}-{comic.get('issue', '')}-{comic.get('year', '')}"
            comic_obj = Comic(
                id=comic_id,
                title=comic.get("title", ""),
                issue=comic.get("issue", ""),
                year=comic.get("year"),
                publisher=comic.get("publisher", ""),
                series_start_year=comic.get("series_start_year"),
                series_end_year=comic.get("series_end_year"),
            )
        else:
            comic_obj = comic

        search_start = asyncio.get_event_loop().time()

        try:
            context = await self._get_browser_context()
            page = await context.new_page()
            page.set_default_timeout(self.timeout * 1000)

            try:
                search_results = await self._search_comic_workflow(page, comic_obj)

                search_result = SearchResult(
                    comic=comic_obj,
                    listings=[],
                    prices=[],
                    metadata={
                        "search_time": asyncio.get_event_loop().time() - search_start,
                    },
                )

                from comic_search_lib.models.comic import ComicListing, ComicPrice

                for item in search_results:
                    listing = ComicListing(
                        store=item.get("store", "League of Comic Geeks"),
                        title=item.get("title", ""),
                        price=item.get("price", "$0.00"),
                        grade=item.get("grade", ""),
                        url=item.get("url", ""),
                        image_url=item.get("image_url"),
                        store_type="locg",
                    )
                    search_result.listings.append(listing)

                    if item.get("price"):
                        price = ComicPrice(
                            store=item.get("store", "League of Comic Geeks"),
                            value=item.get("price", "$0.00"),
                            grade=item.get("grade", ""),
                            url=item.get("url", ""),
                            store_type="locg",
                        )
                        search_result.prices.append(price)

                return search_result

            finally:
                try:
                    await asyncio.wait_for(page.close(), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("Timeout closing page")

        except Exception as e:
            raise SearchError(
                f"Search failed: {e}", source="locg", original_error=e
            ) from e

    async def _search_comic_workflow(self, page: Page, comic: Comic) -> List[Dict]:
        """
        Search for a comic on League of Comic Geeks.

        Args:
            page: Playwright page
            comic: Comic to search for

        Returns:
            List of search results
        """
        logger.debug(f"Searching LoCG for {comic.title} #{comic.issue}")

        try:
            search_query = f"{comic.title} {comic.issue}".strip()
            if comic.year:
                search_query += f" {comic.year}"

            search_url = f"{self.SEARCH_URL}?keyword={search_query.replace(' ', '+')}"

            logger.debug(f"Navigating to search URL: {search_url}")
            await page.goto(
                search_url,
                timeout=self.timeout * 1000,
                wait_until="domcontentloaded",
            )
            await asyncio.wait_for(
                page.wait_for_load_state("domcontentloaded"), timeout=self.timeout
            )

            # Wait for dynamic content to load
            await asyncio.sleep(1.5)

            comic_links = await page.query_selector_all('a[href*="/comic/"]')
            logger.debug(f"Found {len(comic_links)} comic links")

            results = []

            for link in comic_links[:10]:
                try:
                    href = await link.get_attribute("href")
                    text = await link.text_content()

                    if not href or not text:
                        continue

                    if href.startswith("/"):
                        href = f"{self.BASE_URL}{href}"

                    # Try to find issue number in the text
                    issue_match = re.search(r"#?(\d+)", text)
                    if issue_match:
                        found_issue = issue_match.group(1)
                        # Only include if issue number matches
                        if found_issue != str(comic.issue):
                            continue

                    result = {
                        "title": text.strip(),
                        "url": href,
                        "store": "League of Comic Geeks",
                        "price": None,
                        "grade": "",
                    }

                    # Try to find image
                    img = await link.query_selector("img")
                    if img:
                        img_src = await img.get_attribute("src")
                        if img_src:
                            result["image_url"] = img_src

                    results.append(result)

                    if len(results) >= 5:
                        break

                except Exception as e:
                    logger.debug(f"Error parsing comic link: {e}")
                    continue

            logger.info(
                f"LoCG: Found {len(results)} results for {comic.title} #{comic.issue}"
            )
            return results

        except Exception as e:
            logger.error(f"Error in LoCG search workflow: {e}")
            return []

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
