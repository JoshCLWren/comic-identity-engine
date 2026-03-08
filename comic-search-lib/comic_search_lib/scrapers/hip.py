"""
HipComics scraper implementation.

This module provides functionality to scrape comic data from HipComic.com,
focusing on finding the best prices for wishlist items.
"""

import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional, Union

import httpx
from selectolax.lexbor import LexborHTMLParser

from comic_search_lib.exceptions import (
    NetworkError,
    ParseError,
    RateLimitError,
    SearchError,
)
from comic_search_lib.models.comic import Comic, SearchResult


logger = logging.getLogger(__name__)


class HipScraper:
    """
    Scraper for Hip Comics website with optimized search and parsing capabilities.

    This class handles searching, parsing, and validating comic listings from
    HipComic.com, with special handling for year matching and price extraction.
    """

    BASE_URL = (
        "https://www.hipcomic.com/category/comic-books/100/?category_slug=comic-books"
    )

    def __init__(self, timeout: int = 30, max_retries: int = 3):
        """
        Initialize the HipScraper.

        Args:
            timeout (int): Default timeout in seconds for operations
            max_retries (int): Maximum number of retries for failed requests
        """
        self.timeout = timeout
        self._max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": self.BASE_URL,
            }
            self._client = httpx.AsyncClient(
                headers=headers,
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _fetch_html(self, url: str, client: httpx.AsyncClient) -> str:
        """Fetch HTML from URL."""
        try:
            response = await client.get(url)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "60")
                raise RateLimitError(
                    "Rate limited by HipComics (HTTP 429)",
                    source="hip",
                    retry_after=int(retry_after) if retry_after.isdigit() else 60,
                )
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitError(
                    "Rate limited by HipComics (HTTP 429)",
                    source="hip",
                    retry_after=60,
                ) from e
            raise NetworkError(
                f"HTTP error: {e}", source="hip", original_error=e
            ) from e
        except httpx.RequestError as e:
            raise NetworkError(
                f"Network error: {e}", source="hip", original_error=e
            ) from e

    async def search_comic(self, comic: Union[Comic, Dict[str, Any]]) -> SearchResult:
        """
        Search for a single comic on Heritage Auctions (HIP).

        Args:
            comic: The comic to search for, either as a Comic object or a dictionary

        Returns:
            SearchResult: The search result containing listings and prices

        Raises:
            SearchError: If the search fails
        """
        # Convert dict to Comic if needed
        if isinstance(comic, dict):
            comic_id = f"{comic.get('title', '')}-{comic.get('issue', '')}-{comic.get('year', '')}"
            comic_obj = Comic(
                id=comic_id,
                title=comic.get("title", ""),
                issue=comic.get("issue", ""),
                year=comic.get("year") or comic.get("row_year_int"),
                publisher=comic.get("publisher", ""),
                series_start_year=comic.get("series_start_year"),
                series_end_year=comic.get("series_end_year"),
            )
        else:
            comic_obj = comic

        logger.debug(f"Starting search for comic: {comic_obj.title} #{comic_obj.issue}")
        search_start = time.time()

        try:
            client = await self._get_client()

            search_result = SearchResult(
                comic=comic_obj,
                listings=[],
                prices=[],
                metadata={"search_time": time.time() - search_start},
            )

            results = await self._search_comic_with_session(comic_obj, client)

            if not results:
                return search_result

            for item in results:
                # Create listing
                from comic_search_lib.models.comic import ComicListing, ComicPrice

                listing = ComicListing(
                    store=item.get("store", "HipComics"),
                    title=item.get("name", item.get("item_title", "")),
                    price=item.get("price", "$0.00"),
                    grade=item.get("grade", "Unknown"),
                    url=item.get("url", ""),
                    image_url=item.get("image_url", ""),
                    store_type="hip",
                )
                search_result.listings.append(listing)

                # Create price
                price = ComicPrice(
                    store=item.get("store", "HipComics"),
                    value=item.get("price", "$0.00"),
                    grade=item.get("grade", "Unknown"),
                    url=item.get("url", ""),
                    store_type="hip",
                )
                search_result.prices.append(price)

            return search_result

        except Exception as e:
            if isinstance(e, (NetworkError, ParseError, RateLimitError)):
                raise
            raise SearchError(
                f"Search failed: {e}", source="hip", original_error=e
            ) from e

    async def _search_comic_with_session(
        self, comic: Comic, client: httpx.AsyncClient
    ) -> List[Dict]:
        """
        Search for a comic using the provided client.

        Args:
            comic: The comic to search for
            client: The HTTP client to use

        Returns:
            List[Dict]: List of found listings
        """
        results = []
        comic_title = comic.title
        comic_issue = comic.issue

        try:
            page = 1
            page_size = 96
            max_pages = 5

            while page <= max_pages and len(results) < 50:
                logger.debug(f"Processing page {page} for {comic_title} #{comic_issue}")

                year_suffix = f" {comic.year}" if comic.year else ""
                keywords = f"{comic_title} {comic_issue}{year_suffix}".replace(
                    " ", "%20"
                )
                search_url = (
                    f"{self.BASE_URL}&keywords={keywords}&listing_type=product&"
                    f"limit={page_size}&sort=default"
                )

                if page > 1:
                    search_url += f"&page={page}"

                logger.debug(f"Search URL: {search_url}")

                html = await self._fetch_html(search_url, client)

                if not html:
                    break

                parser = LexborHTMLParser(html)
                comic_listings = parser.css(".r-listing")

                if not comic_listings:
                    logger.debug(f"No listings found on page {page}")
                    break

                logger.debug(f"Found {len(comic_listings)} listings on page {page}")

                for listing_div in comic_listings:
                    listing = {}

                    link_tag = listing_div.css_first("a[href*='/listing/']")
                    if not link_tag:
                        continue

                    listing["url"] = link_tag.attributes.get("href", "")
                    if not listing["url"]:
                        continue
                    listing["url"] = f"https://www.hipcomic.com{listing['url']}"

                    name_elem = listing_div.css_first(".r-listing__title h5")
                    if name_elem:
                        listing["name"] = name_elem.text().strip()
                    else:
                        title_elem = listing_div.css_first(".r-listing__title")
                        if title_elem:
                            listing["name"] = title_elem.text().strip()

                    if not listing.get("name"):
                        continue

                    listing["raw_item_title"] = listing["name"]
                    listing["item_title"] = (
                        listing["name"].lower().split("#")[0].strip()
                    )

                    skip_keywords = ["cgc", "lot", "set"]
                    if any(
                        keyword in listing["item_title"].lower()
                        for keyword in skip_keywords
                    ):
                        continue

                    img_tag = listing_div.css_first("img")
                    if img_tag:
                        listing["image_url"] = img_tag.attributes.get("src", "")

                    price_tag = listing_div.css_first(".r-listing__price")
                    if not price_tag:
                        price_tag = listing_div.css_first("[class*='price']")

                    if price_tag:
                        price_text = price_tag.text().strip()
                    else:
                        continue

                    if price_text.startswith("C"):
                        continue

                    price_value = self._parse_price(price_text)
                    if price_value <= 0:
                        continue
                    listing["price"] = f"${price_value:.2f}"

                    seller_elem = listing_div.css_first("#details-seller-username")
                    if seller_elem:
                        seller_text = seller_elem.text()
                        seller_name = re.sub(r"\s*\(\d+\)", "", seller_text).strip()
                        listing["store"] = seller_name if seller_name else "HIP"
                    else:
                        listing["store"] = "HIP"

                    implied_years = self._find_years(listing)

                    if "#" in listing["name"]:
                        implied_issue = listing["name"].split("#")[1].split(" ")[0]
                        if comic_issue != implied_issue:
                            for divider in ("--", "-"):
                                if divider in implied_issue:
                                    implied_issue = implied_issue.split(divider)[0]

                            cleaned_issue = "".join(filter(str.isdigit, implied_issue))
                            if cleaned_issue == implied_issue:
                                continue
                            if comic_issue != cleaned_issue:
                                continue

                    valid_listing = True

                    if comic.year:
                        comic_year_int = int(comic.year)
                        year_matches = any(
                            int(imp_year) in (comic_year_int, comic_year_int + 1)
                            for imp_year in implied_years
                            if isinstance(imp_year, int) or str(imp_year).isdigit()
                        )
                        if not year_matches:
                            valid_listing = False
                            logger.debug(
                                f"[HIP] Filtered listing with years {implied_years}, "
                                f"looking for {comic_year_int}"
                            )

                    elif (
                        hasattr(comic, "series_start_year")
                        and comic.series_start_year
                        and hasattr(comic, "series_end_year")
                        and comic.series_end_year
                    ):
                        for imp_year in implied_years:
                            try:
                                start_year = int(comic.series_start_year)
                                end_year = int(comic.series_end_year)
                                imp_year = int(imp_year)

                                if imp_year < start_year or imp_year > end_year:
                                    valid_listing = False
                                    break
                            except (ValueError, TypeError):
                                pass

                    if not valid_listing:
                        continue

                    listing["title"] = comic.title
                    listing["type"] = "hip"
                    listing["key"] = f"{comic.title}|{listing['item_title']}"
                    results.append(listing)

                page += 1

            return results

        except Exception as e:
            if isinstance(e, (NetworkError, ParseError, RateLimitError)):
                raise
            raise ParseError(
                f"Error parsing search results: {e}",
                source="hip",
                original_error=e,
            ) from e

    def _find_years(self, data: Dict) -> List[int]:
        """
        Find years mentioned in the listing data.

        Args:
            data: Listing data dictionary

        Returns:
            List[int]: List of years found in the data
        """
        try:
            years = set()

            text = " ".join(str(val) for val in data.values())

            year_matches = re.finditer(r"\b(19\d{2}|20\d{2})\b", text)
            for match in year_matches:
                years.add(int(match.group(1)))

            partial_years = re.findall(r"'(\d{2})", text)
            for year in partial_years:
                try:
                    year_int = int(year)
                    full_year = 1900 + year_int if year_int > 50 else 2000 + year_int
                    years.add(full_year)
                except (ValueError, TypeError):
                    continue

            year_ints = list(years)
            if year_ints:
                min_year, max_year = min(year_ints), max(year_ints)
                for y in range(min_year - 1, max_year + 2):
                    years.add(y)

            return list(years)

        except Exception as e:
            logger.error(f"Error finding years: {e}")
            return []

    def _parse_price(self, price_text: str) -> float:
        """
        Parse price from text.

        Args:
            price_text: Price text to parse

        Returns:
            float: Parsed price value
        """
        try:
            cleaned = re.sub(r"[^\d.]", "", price_text)
            if not cleaned:
                return 0.0
            return float(cleaned)
        except (ValueError, AttributeError):
            return 0.0

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
