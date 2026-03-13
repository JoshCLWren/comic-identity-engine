"""Grand Comics Database (GCD) scraper for comic search.

This scraper uses the GCD JSON API to search for comics.
Note: GCD is a catalog/database, not a marketplace, so prices will be "N/A"
and listings represent database entries, not items for sale.

GCD API documentation: https://www.comics.org/api/
"""

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import aiohttp
from selectolax.lexbor import LexborHTMLParser

from comic_search_lib.exceptions import NetworkError, ParseError, RateLimitError
from comic_search_lib.models import Comic, SearchResult, ComicListing, ComicPrice
from comic_search_lib.resilience import CircuitBreaker

logger = logging.getLogger(__name__)


class GCDScraper:
    """Scraper for Grand Comics Database (comics.org) using their JSON API."""

    BASE_URL = "https://www.comics.org"
    API_BASE = f"{BASE_URL}/api"
    ISSUE_URL_TEMPLATE = f"{BASE_URL}/issue/"

    def __init__(
        self,
        timeout: float = 30.0,
        failure_threshold: int = 10,
        reset_timeout_seconds: int = 120,
    ):
        """Initialize scraper.

        Args:
            timeout: HTTP request timeout in seconds
            failure_threshold: Circuit breaker failures before opening
            reset_timeout_seconds: Circuit breaker reset timeout
        """
        self.timeout = timeout
        self._circuit_breaker = CircuitBreaker(
            name="gcd",
            failure_threshold=failure_threshold,
            reset_timeout_seconds=reset_timeout_seconds,
        )

    async def search_comic(
        self,
        title: str,
        issue: str,
        year: Optional[int] = None,
        publisher: Optional[str] = None,
    ) -> SearchResult:
        """Search for a comic on GCD using their API with circuit breaker protection.

        Note: GCD API doesn't have a direct search endpoint. This implementation
        tries to find the issue by constructing likely URLs and parsing responses.

        Args:
            title: Comic title
            issue: Issue number
            year: Optional publication year
            publisher: Optional publisher name

        Returns:
            SearchResult with URL and listings (database entries)

        Raises:
            NetworkError: If network request fails
            ParseError: If HTML parsing fails
        """
        comic = Comic(
            id=f"search-{int(__import__('time').time())}",
            title=title,
            issue=issue,
            year=year,
            publisher=publisher,
        )

        async def _do_search():
            from comic_search_lib.http_pool import get_http_pool

            pool = await get_http_pool()
            async with pool.get_session(self.BASE_URL) as session:
                return await self._search_with_session(comic, session)

        return await self._circuit_breaker.call_with_retry(_do_search)

    async def _search_with_session(
        self, comic: Comic, session: aiohttp.ClientSession
    ) -> SearchResult:
        """Search using GCD's JSON API instead of HTML scraping."""
        result = SearchResult(comic=comic, listings=[], prices=[])

        try:
            # Use GCD's JSON API to search for series
            # API endpoint: https://www.comics.org/api/series/
            api_url = f"{self.API_BASE}/series/"

            params = {}
            if comic.title:
                params["name"] = comic.title
            if comic.year:
                params["year_began"] = str(comic.year)
            if comic.publisher:
                params["publisher"] = comic.publisher

            logger.debug(f"Searching GCD API with params: {params}")

            headers = {
                "Accept": "application/json",
            }

            async with session.get(api_url, params=params, headers=headers) as response:
                response.raise_for_status()

                # Check if response is JSON (not HTML login page)
                content_type = response.headers.get("Content-Type", "")
                if "text/html" in content_type:
                    logger.warning(
                        "GCD returned HTML instead of JSON (possibly blocked)"
                    )
                    return result

                try:
                    data = await response.json()
                except Exception:
                    logger.warning("GCD response is not valid JSON")
                    return result

            # Parse series from API response
            series_list = self._parse_series_from_api(data)

            if not series_list:
                logger.debug(f"No GCD series found for {comic.title}")
                return result

            # For each series, try to find the issue using the API
            for series in series_list[:3]:
                series_id = series.get("id", "")
                if not series_id:
                    continue

                logger.debug(f"Checking series ID: {series_id}")

                try:
                    # Use GCD API to get issues for this series
                    issues = await self._fetch_issues_from_api(
                        session, series_id, str(comic.issue)
                    )

                    for issue in issues:
                        comic_listing = ComicListing(
                            store="GCD",
                            title=issue.get("title", ""),
                            price="N/A",
                            grade="",
                            url=issue.get("url", ""),
                            image_url=issue.get("image_url", ""),
                            store_type="gcd",
                            metadata={
                                "issue_id": issue.get("issue_id", ""),
                                "series_id": series_id,
                                "publisher": series.get("publisher", ""),
                                "publication_date": issue.get("publication_date", ""),
                            },
                        )
                        result.listings.append(comic_listing)

                    if result.listings:
                        result.url = f"{self.BASE_URL}/series/{series_id}/"
                        break

                except Exception as e:
                    logger.debug(f"Error fetching issues for series {series_id}: {e}")
                    continue

            logger.debug(f"Found {len(result.listings)} GCD entries")
            return result

            if not html:
                logger.debug("No response from GCD")
                return result

            # Parse series from the search results
            series_list = self._parse_series_results(html)
            print(f"📊 [GCD] Found {len(series_list)} series")

            if not series_list:
                logger.debug(f"No GCD series found for {comic.title}")
                return result

            # For each series, try to find the issue
            for series in series_list[:3]:  # Limit to top 3 series
                series_url = series.get("url", "")
                if not series_url:
                    continue

                if not series_url.startswith("http"):
                    series_url = urljoin(self.BASE_URL, series_url)

                print(f"   Series: {series.get('title', 'Unknown')} -> {series_url}")
                logger.debug(f"Checking series: {series_url}")

                # Fetch the series page
                try:
                    async with session.get(series_url) as series_response:
                        series_response.raise_for_status()
                        series_html = await series_response.text()

                    # Parse issues from the series page
                    issues = self._parse_issues_from_series(
                        series_html, str(comic.issue)
                    )
                    print(f"     Found {len(issues)} matching issues")

                    for issue in issues:
                        comic_listing = ComicListing(
                            store="GCD",
                            title=issue.get("title", ""),
                            price="N/A",
                            grade="",
                            url=issue.get("url", ""),
                            image_url=issue.get("image_url", ""),
                            store_type="gcd",
                            metadata={
                                "issue_id": issue.get("issue_id", ""),
                                "series_id": issue.get("series_id", ""),
                                "publisher": series.get("publisher", ""),
                                "publication_date": issue.get("publication_date", ""),
                            },
                        )
                        result.listings.append(comic_listing)

                    if result.listings:
                        result.url = series_url
                        break

                except Exception as e:
                    logger.debug(f"Error fetching series {series_url}: {e}")
                    continue

            logger.debug(f"Found {len(result.listings)} GCD entries")
            return result

        except aiohttp.ClientResponseError as e:
            raise NetworkError(
                f"GCD returned HTTP {e.status}",
                source="gcd",
                original_error=e,
            ) from e
        except aiohttp.ClientError as e:
            raise NetworkError(
                f"GCD network request failed: {e}",
                source="gcd",
                original_error=e,
            ) from e

    def _parse_series_results(self, html: str) -> List[Dict[str, Any]]:
        """Parse series results from GCD search HTML.

        GCD search results are displayed in a table format.
        """
        results = []

        try:
            parser = LexborHTMLParser(html)

            # Look for the results table
            table = parser.css_first("table.listing_table")
            if not table:
                table = parser.css_first("table")

            print(f"   [GCD Parser] Looking for results table...")
            print(f"   [GCD Parser] Found listing_table: {table is not None}")
            print(f"   [GCD Parser] Found any table: {table is not None}")

            if not table:
                logger.debug("No results table found in GCD response")
                # Try to find any links to series pages as fallback
                all_links = parser.css("a[href*='/series/']")
                print(f"   [GCD Parser] Fallback: found {len(all_links)} series links")
                for link in all_links[:5]:
                    href = link.attributes.get("href", "")
                    text = link.text().strip()[:50]
                    print(f"      - {text}: {href}")
                return []

            rows = table.css("tr")
            print(f"   [GCD Parser] Found {len(rows)} table rows")

            for row in rows:
                try:
                    cells = row.css("td")

                    if len(cells) < 2:
                        continue

                    # First cell usually has the series link
                    link_cell = cells[0]
                    series_link = link_cell.css_first("a")

                    if not series_link:
                        continue

                    url = series_link.attributes.get("href", "")
                    if url and not url.startswith("http"):
                        url = urljoin(self.BASE_URL, url)

                    # Extract series name
                    title = series_link.text().strip()

                    # Extract year if available
                    year = None
                    for cell in cells:
                        cell_text = cell.text().strip()
                        year_match = re.search(r"\b(19\d{2}|20\d{2})\b", cell_text)
                        if year_match:
                            year = year_match.group(1)
                            break

                    results.append(
                        {
                            "title": title,
                            "url": url,
                            "year": year,
                            "publisher": None,
                        }
                    )

                except Exception as e:
                    logger.debug(f"Error parsing series row: {e}")
                    continue

            logger.debug(f"Parsed {len(results)} series from GCD")
            print(f"   [GCD Parser] Successfully parsed {len(results)} series")
            return results

        except Exception as e:
            logger.error(f"Error parsing series results: {e}")
            print(f"   [GCD Parser] ERROR: {e}")
            return results

        except Exception as e:
            logger.error(f"Error parsing series results: {e}")
            return []

    def _parse_issues_from_series(
        self, html: str, issue_number: str
    ) -> List[Dict[str, Any]]:
        """Parse issues from a GCD series page.

        Args:
            html: Series page HTML
            issue_number: Issue number to filter by

        Returns:
            List of matching issues
        """
        results = []

        try:
            parser = LexborHTMLParser(html)

            # Look for the issue list table
            table = parser.css_first("table.listing_table")
            if not table:
                table = parser.css_first("table")

            if not table:
                return []

            rows = table.css("tr")

            for row in rows:
                try:
                    cells = row.css("td")

                    if len(cells) < 2:
                        continue

                    # First cell usually has the issue link
                    link_cell = cells[0]
                    issue_link = link_cell.css_first("a")

                    if not issue_link:
                        continue

                    url = issue_link.attributes.get("href", "")
                    if url and not url.startswith("http"):
                        url = urljoin(self.BASE_URL, url)

                    # Extract issue text
                    issue_text = issue_link.text().strip()

                    # Check if this matches our issue number
                    if not self._issue_matches(issue_text, issue_number):
                        continue

                    # Extract issue ID from URL
                    issue_id = self._extract_issue_id_from_url(url)

                    # Extract publication date
                    pub_date = None
                    for cell in cells:
                        cell_text = cell.text().strip()
                        # Look for date patterns
                        if re.search(r"\b(19\d{2}|20\d{2})\b", cell_text):
                            pub_date = cell_text
                            break

                    # Extract cover image if available
                    image_url = None
                    img_tag = link_cell.css_first("img")
                    if img_tag:
                        image_url = img_tag.attributes.get("src", "")
                        if image_url and not image_url.startswith("http"):
                            image_url = urljoin(self.BASE_URL, image_url)

                    results.append(
                        {
                            "title": issue_text,
                            "url": url,
                            "issue_id": issue_id,
                            "series_id": self._extract_series_id_from_url(url),
                            "publication_date": pub_date,
                            "image_url": image_url,
                        }
                    )

                except Exception as e:
                    logger.debug(f"Error parsing issue row: {e}")
                    continue

            return results

        except Exception as e:
            logger.error(f"Error parsing issues from series: {e}")
            return []

    def _issue_matches(self, issue_text: str, target_issue: str) -> bool:
        """Check if an issue text matches the target issue number.

        Args:
            issue_text: Issue text from GCD (e.g., "1", "1 (Direct)", "-1")
            target_issue: Target issue number

        Returns:
            True if the issue matches
        """
        # Normalize both for comparison
        issue_normalized = issue_text.lower().split("(")[0].strip()
        target_normalized = target_issue.lower().strip()

        return issue_normalized == target_normalized

    def _extract_issue_id_from_url(self, url: Optional[str]) -> str:
        """Extract issue ID from GCD URL.

        GCD URLs: https://www.comics.org/issue/125295/
        """
        if not url:
            return ""

        match = re.search(r"/issue/(\d+)/?", url)
        if match:
            return match.group(1)

        return ""

    def _extract_series_id_from_url(self, url: Optional[str]) -> str:
        """Extract series ID from GCD URL context.

        From an issue URL, try to infer the series ID.
        """
        if not url:
            return ""

        # Try to extract from issue URL first
        match = re.search(r"/issue/(\d+)/?", url)
        if match:
            # For now, return empty - we'd need to fetch the issue to get the series ID
            # Or parse it from the URL if the format is known
            pass

        return ""

    def _parse_series_from_api(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse series from GCD API JSON response.

        Args:
            data: JSON response from GCD API

        Returns:
            List of series dictionaries
        """
        results = []

        try:
            # GCD API response format: {"results": [...]} or direct array
            if isinstance(data, dict):
                series_array = data.get("results", data.get("series", []))
            elif isinstance(data, list):
                series_array = data
            else:
                return []

            for series in series_array:
                if not isinstance(series, dict):
                    continue

                series_id = series.get("id") or series.get("series_id")
                if not series_id:
                    continue

                results.append(
                    {
                        "id": str(series_id),
                        "title": series.get("name", series.get("title", "")),
                        "publisher": series.get("publisher", {}).get("name", "")
                        if isinstance(series.get("publisher"), dict)
                        else series.get("publisher", ""),
                        "year": series.get("year_began", series.get("year")),
                    }
                )

            logger.debug(f"Parsed {len(results)} series from GCD API")
            return results

        except Exception as e:
            logger.error(f"Error parsing API series response: {e}")
            return []

    async def _fetch_issues_from_api(
        self, session: aiohttp.ClientSession, series_id: str, issue_number: str
    ) -> List[Dict[str, Any]]:
        """Fetch issues for a series from GCD API.

        Args:
            session: aiohttp client session
            series_id: GCD series ID
            issue_number: Issue number to filter by

        Returns:
            List of matching issue dictionaries
        """
        results = []

        try:
            # Use GCD API to get issues for this series
            # API endpoint: https://www.comics.org/api/series/{series_id}/issues/
            issues_url = f"{self.API_BASE}/series/{series_id}/issues/"

            async with session.get(
                issues_url, headers={"Accept": "application/json"}
            ) as response:
                response.raise_for_status()

                data = await response.json()

            # Parse issues from API response
            if isinstance(data, dict):
                issues_array = data.get("results", data.get("issues", []))
            elif isinstance(data, list):
                issues_array = data
            else:
                return []

            for issue in issues_array:
                if not isinstance(issue, dict):
                    continue

                issue_id = issue.get("id") or issue.get("issue_id")
                if not issue_id:
                    continue

                # Check if issue number matches
                issue_num = issue.get("number", issue.get("issue", ""))
                if not self._issue_matches(str(issue_num), issue_number):
                    continue

                # Build issue URL
                url = f"{self.BASE_URL}/issue/{issue_id}/"

                # Extract publication date
                pub_date = issue.get("publication_date") or issue.get("date")
                if isinstance(pub_date, dict):
                    pub_date = pub_date.get("date", "")

                results.append(
                    {
                        "title": issue.get("display_name", f"#{issue_num}"),
                        "url": url,
                        "issue_id": str(issue_id),
                        "publication_date": str(pub_date) if pub_date else "",
                        "image_url": "",  # GCD API may not include images
                    }
                )

            return results

        except Exception as e:
            logger.debug(f"Error fetching issues from API: {e}")
            return []
