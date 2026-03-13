"""Series page extractor service for bulk cross-platform mapping.

This service implements the series page extraction strategy documented in
SERIES_PAGE_STRATEGY.md. It provides efficient bulk extraction of issue URLs
from series pages across all supported platforms.

This is 10-100x faster than individual issue searching because:
- One HTTP request per series instead of per issue
- Fetches 20-150 issues at once from series pages
- Reduces rate limiting and bandwidth usage
- Higher success rate (80-90% vs 20-30%)

USAGE:
    from comic_identity_engine.services.series_page_extractor import SeriesPageExtractor

    extractor = SeriesPageExtractor()

    # Extract series URL from issue URL
    series_url = await extractor.extract_series_url(
        "https://www.comics.org/issue/125295/",
        "gcd"
    )

    # Scrape all issue URLs from series page
    all_issues = await extractor.scrape_all_issues(
        "https://www.comics.org/series/4254/",
        "gcd"
    )
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup
import structlog

from comic_identity_engine.core.http_client import HttpClient
from comic_identity_engine.errors import NetworkError, ParseError


logger = structlog.get_logger(__name__)


DEFAULT_MAX_PAGES = 50


@dataclass
class SeriesExtractionResult:
    """Result from series page extraction.

    Attributes:
        series_url: The series page URL
        issue_urls: List of full issue URLs
        platform: Platform identifier
        issues_count: Number of issues found
    """

    series_url: str
    issue_urls: list[str]
    platform: str
    issues_count: int


class SeriesPageExtractor:
    """Service for extracting series pages and scraping all issue URLs.

    This service implements platform-specific handlers for:
    - GCD: JSON API (fastest)
    - AA: HTML parsing for series links
    - CPG: URL manipulation (no HTTP needed for extraction)
    - CCL: HTML parsing with pagination
    - LoCG: HTML parsing (may need API in future)

    All methods are async and use the HttpClient for proper rate limiting
    and error handling.
    """

    PLATFORM_DOMAINS = {
        "gcd": "www.comics.org",
        "aa": "atomicavenue.com",
        "cpg": "www.comicspriceguide.com",
        "ccl": "www.comiccollectorlive.com",
        "locg": "leagueofcomicgeeks.com",
    }

    def __init__(
        self,
        http_client: HttpClient | None = None,
        timeout: float = 30.0,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> None:
        """Initialize the series page extractor.

        Args:
            http_client: Optional HTTP client (one will be created if not provided)
            timeout: HTTP request timeout in seconds
            max_pages: Maximum pagination pages to fetch (prevents infinite loops)
        """
        self.timeout = timeout
        self.max_pages = max_pages
        self._http_client: HttpClient | None = http_client
        self._logger = logger
        self._html_cache: dict[str, str] = {}

    async def extract_series_url(
        self,
        issue_url: str,
        platform: str,
    ) -> str:
        """Extract series page URL from an issue URL.

        Args:
            issue_url: Full URL to an issue page
            platform: Platform identifier (gcd, aa, cpg, ccl, locg)

        Returns:
            Full URL to the series page

        Raises:
            ParseError: If URL cannot be parsed or series link not found
            NetworkError: If HTTP request fails
            ValueError: If platform is not supported

        Examples:
            >>> await extractor.extract_series_url(
            ...     "https://www.comics.org/issue/125295/",
            ...     "gcd"
            ... )
            "https://www.comics.org/series/4254/"
        """
        platform = platform.lower()

        if platform not in self.PLATFORM_DOMAINS:
            raise ValueError(
                f"Unsupported platform: {platform}. "
                f"Supported: {list(self.PLATFORM_DOMAINS.keys())}"
            )

        if not issue_url or not isinstance(issue_url, str):
            raise ValueError("issue_url must be a non-empty string")

        self._validate_url(issue_url, platform)

        self._logger.debug(
            "extract_series_url.starting",
            platform=platform,
            issue_url=issue_url,
        )

        handler = {
            "gcd": self._extract_gcd_series_url,
            "aa": self._extract_aa_series_url,
            "cpg": self._extract_cpg_series_url,
            "ccl": self._extract_ccl_series_url,
            "locg": self._extract_locg_series_url,
        }.get(platform)

        if handler is None:
            raise ValueError(f"No handler implemented for platform: {platform}")

        try:
            series_url = await handler(issue_url)
            self._logger.info(
                "extract_series_url.success",
                platform=platform,
                issue_url=issue_url,
                series_url=series_url,
            )
            return series_url
        except Exception as e:
            self._logger.error(
                "extract_series_url.failed",
                platform=platform,
                issue_url=issue_url,
                error=str(e),
            )
            raise

    async def scrape_all_issues(
        self,
        series_url: str,
        platform: str,
    ) -> list[str]:
        """Scrape all issue URLs from a series page.

        Args:
            series_url: Full URL to the series page
            platform: Platform identifier (gcd, aa, cpg, ccl, locg)

        Returns:
            List of full issue URLs

        Raises:
            ParseError: If page cannot be parsed
            NetworkError: If HTTP request fails
            ValueError: If platform is not supported

        Examples:
            >>> await extractor.scrape_all_issues(
            ...     "https://www.comics.org/series/4254/",
            ...     "gcd"
            ... )
            [
                "https://www.comics.org/issue/125295/",
                "https://www.comics.org/issue/125296/",
                ...
            ]
        """
        platform = platform.lower()

        if platform not in self.PLATFORM_DOMAINS:
            raise ValueError(
                f"Unsupported platform: {platform}. "
                f"Supported: {list(self.PLATFORM_DOMAINS.keys())}"
            )

        if not series_url or not isinstance(series_url, str):
            raise ValueError("series_url must be a non-empty string")

        self._validate_url(series_url, platform)

        self._logger.debug(
            "scrape_all_issues.starting",
            platform=platform,
            series_url=series_url,
        )

        handler = {
            "gcd": self._scrape_gcd_series_page,
            "aa": self._scrape_aa_series_page,
            "cpg": self._scrape_cpg_series_page,
            "ccl": self._scrape_ccl_series_page,
            "locg": self._scrape_locg_series_page,
        }.get(platform)

        if handler is None:
            raise ValueError(f"No handler implemented for platform: {platform}")

        try:
            issue_urls = await handler(series_url)
            self._logger.info(
                "scrape_all_issues.success",
                platform=platform,
                series_url=series_url,
                issues_count=len(issue_urls),
            )
            return issue_urls
        except Exception as e:
            self._logger.error(
                "scrape_all_issues.failed",
                platform=platform,
                series_url=series_url,
                error=str(e),
            )
            raise

    async def _get_http_client(self, platform: str) -> HttpClient:
        """Get or create an HTTP client for the platform.

        Args:
            platform: Platform identifier for rate limiting

        Returns:
            HttpClient instance
        """
        if self._http_client is None:
            self._http_client = HttpClient(platform=platform, timeout=self.timeout)
            await self._http_client._ensure_initialized()
        return self._http_client

    def _validate_url(self, url: str, platform: str) -> None:
        """Validate URL matches expected platform domain.

        Args:
            url: URL to validate
            platform: Platform identifier

        Raises:
            ValueError: If URL does not match platform domain
        """
        parsed = urlparse(url)
        expected_domain = self.PLATFORM_DOMAINS.get(platform)

        if not expected_domain:
            raise ValueError(f"Unknown platform: {platform}")

        if parsed.netloc != expected_domain:
            raise ValueError(
                f"URL domain '{parsed.netloc}' does not match "
                f"expected platform domain '{expected_domain}' for {platform}"
            )

    async def _fetch_html(self, url: str, platform: str, use_cache: bool = True) -> str:
        """Fetch HTML content from URL with optional caching.

        Args:
            url: URL to fetch
            platform: Platform identifier for rate limiting
            use_cache: Whether to use cached HTML if available

        Returns:
            HTML content as string

        Raises:
            NetworkError: If request fails
        """
        if use_cache and url in self._html_cache:
            self._logger.debug("_fetch_html.cache_hit", url=url)
            return self._html_cache[url]

        client = await self._get_http_client(platform)
        response = await client.get(url)
        html = response.text

        if use_cache:
            self._html_cache[url] = html

        return html

    async def _extract_gcd_series_url(self, issue_url: str) -> str:
        """Extract GCD series URL from issue URL using JSON API with HTML fallback.

        GCD JSON API: https://www.comics.org/issue/{id}/?format=json

        Args:
            issue_url: GCD issue URL

        Returns:
            GCD series URL

        Raises:
            ParseError: If JSON response is invalid and HTML fallback also fails
            NetworkError: If request fails
        """
        api_url = f"{issue_url.rstrip('/')}/?format=json"

        try:
            html = await self._fetch_html(api_url, "gcd", use_cache=False)

            data = json.loads(html)

            series_id = data["issue"]["series"]["id"]
            series_url = f"https://www.comics.org/series/{series_id}/"

            return series_url

        except (KeyError, json.JSONDecodeError) as e:
            self._logger.warning(
                "_extract_gcd_series_url.json_failed",
                issue_url=issue_url,
                error=str(e),
            )
            return await self._extract_gcd_series_url_html_fallback(issue_url)

    async def _extract_gcd_series_url_html_fallback(self, issue_url: str) -> str:
        """Extract GCD series URL from issue HTML page as fallback.

        Args:
            issue_url: GCD issue URL

        Returns:
            GCD series URL

        Raises:
            ParseError: If series link not found in HTML
            NetworkError: If request fails
        """
        html = await self._fetch_html(issue_url, "gcd")
        soup = BeautifulSoup(html, "html.parser")

        series_link = soup.select_one('a[href*="/series/"]')
        if not series_link or not series_link.get("href"):
            raise ParseError(
                "Series link not found in GCD issue page (HTML fallback)",
                source="gcd",
            )

        href = series_link["href"]

        if href.startswith("/"):
            parsed = urlparse(issue_url)
            href = f"{parsed.scheme}://{parsed.netloc}{href}"

        return href

    async def _scrape_gcd_series_page(self, series_url: str) -> list[str]:
        """Scrape all GCD issue URLs from series page using JSON API with HTML fallback.

        Args:
            series_url: GCD series URL

        Returns:
            List of GCD issue URLs

        Raises:
            ParseError: If JSON response is invalid and HTML fallback also fails
            NetworkError: If request fails
        """
        api_url = f"{series_url.rstrip('/')}/?format=json"

        try:
            html = await self._fetch_html(api_url, "gcd", use_cache=False)

            data = json.loads(html)

            issue_urls = []
            for issue in data.get("series", {}).get("issues", []):
                issue_id = issue.get("id")
                if issue_id:
                    issue_urls.append(f"https://www.comics.org/issue/{issue_id}/")

            if not issue_urls:
                self._logger.warning(
                    "_scrape_gcd_series_page.no_issues",
                    series_url=series_url,
                )

            return issue_urls

        except (KeyError, json.JSONDecodeError) as e:
            self._logger.warning(
                "_scrape_gcd_series_page.json_failed",
                series_url=series_url,
                error=str(e),
            )
            return await self._scrape_gcd_series_page_html_fallback(series_url)

    async def _scrape_gcd_series_page_html_fallback(self, series_url: str) -> list[str]:
        """Scrape all GCD issue URLs from series HTML page as fallback.

        Args:
            series_url: GCD series URL

        Returns:
            List of GCD issue URLs

        Raises:
            ParseError: If issue links not found in HTML
            NetworkError: If request fails
        """
        html = await self._fetch_html(series_url, "gcd")
        soup = BeautifulSoup(html, "html.parser")

        issue_links = soup.select('a[href*="/issue/"]')

        issue_urls = []
        for link in issue_links:
            href = link.get("href")
            if href:
                if href.startswith("/"):
                    parsed = urlparse(series_url)
                    href = f"{parsed.scheme}://{parsed.netloc}{href}"
                if "/issue/" in href:
                    issue_urls.append(href)

        if not issue_urls:
            self._logger.warning(
                "_scrape_gcd_series_page_html_fallback.no_issues",
                series_url=series_url,
            )

        return issue_urls

    async def _extract_aa_series_url(self, issue_url: str) -> str:
        """Extract AA series URL from issue URL by parsing HTML.

        AA issue pages link to series pages in the HTML.

        Args:
            issue_url: AA issue URL

        Returns:
            AA series URL

        Raises:
            ParseError: If series link not found in HTML
            NetworkError: If request fails
        """
        html = await self._fetch_html(issue_url, "aa")
        soup = BeautifulSoup(html, "html.parser")

        series_link = soup.select_one('a[href*="/atomic/series/"]')
        if not series_link or not series_link.get("href"):
            raise ParseError(
                "Series link not found in AA issue page",
                source="aa",
            )

        href = series_link["href"]

        if href.startswith("/"):
            parsed = urlparse(issue_url)
            href = f"{parsed.scheme}://{parsed.netloc}{href}"

        return href

    async def _scrape_aa_series_page(self, series_url: str) -> list[str]:
        """Scrape all AA issue URLs from series page.

        AA issue URLs have the format: /atomic/item/ITEM_ID/1/slug
        The slug is required for the URL to work (404s without it).
        We construct the slug from the link text if not present in href.

        Args:
            series_url: AA series URL

        Returns:
            List of AA issue URLs

        Raises:
            ParseError: If issue links not found
            NetworkError: If request fails
        """
        html = await self._fetch_html(series_url, "aa")
        soup = BeautifulSoup(html, "html.parser")

        issue_links = soup.select('a[href*="/atomic/item/"]')

        issue_urls = []
        for link in issue_links:
            href = link.get("href")
            if not href:
                continue

            # Convert to string if needed (BeautifulSoup returns AttributeValueList)
            if not isinstance(href, str):
                href = str(href)

            if href.startswith("/"):
                parsed = urlparse(series_url)
                href = f"{parsed.scheme}://{parsed.netloc}{href}"

            # AA URLs must have a slug
            # Full URL: https://atomicavenue.com/atomic/item/ITEM_ID/1/slug
            # Split: ['https:', '', 'atomicavenue.com', 'atomic', 'item', 'ITEM_ID', '1', 'slug']
            # Count: 8 parts
            # Without slug: ['https:', '', 'atomicavenue.com', 'atomic', 'item', 'ITEM_ID', '1']
            # Count: 7 parts
            path_parts = href.rstrip("/").split("/")

            if len(path_parts) >= 8:
                # URL already has slug, use as-is
                issue_urls.append(href)
            elif len(path_parts) == 7:
                # URL is missing slug, try to construct it from link text
                # Expected format: /atomic/item/ITEM_ID/1
                # We need to add a slug like "issue-1" or similar
                link_text = link.get_text(strip=True)

                # Try to extract issue number from link text
                # AA link text is usually like "#1" or "Issue #1"
                issue_match = re.search(r"#?(\d+)", link_text)

                if issue_match:
                    issue_num = issue_match.group(1)
                    # Construct URL with slug
                    # AA format: /atomic/item/ITEM_ID/1/issue-NUM
                    slug = f"issue-{issue_num}"
                    constructed_url = f"{href}/{slug}"
                    issue_urls.append(constructed_url)
                else:
                    # Can't construct slug, skip this URL
                    self._logger.debug(
                        "_scrape_aa_series_page.cannot_construct_slug",
                        url=href,
                        link_text=link_text,
                        reason="Cannot extract issue number from link text",
                    )
            else:
                # Malformed URL
                self._logger.debug(
                    "_scrape_aa_series_page.malformed_url",
                    url=href,
                    path_parts=len(path_parts),
                    reason="URL path has unexpected structure",
                )

        if not issue_urls:
            self._logger.warning(
                "_scrape_aa_series_page.no_issues",
                series_url=series_url,
            )

        return issue_urls

    async def _extract_cpg_series_url(self, issue_url: str) -> str:
        """Extract CPG series URL from issue URL by URL manipulation.

        CPG URL structure:
        - Issue: /titles/SERIES_SLUG/ISSUE_NUM/ISSUE_ID
        - Series: /titles/SERIES_SLUG

        Args:
            issue_url: CPG issue URL

        Returns:
            CPG series URL
        """
        parsed = urlparse(issue_url)
        path_parts = parsed.path.rstrip("/").split("/")

        if len(path_parts) < 4:
            raise ParseError(
                f"Invalid CPG issue URL structure: {issue_url}",
                source="cpg",
            )

        series_slug = path_parts[2]

        series_url = f"{parsed.scheme}://{parsed.netloc}/titles/{series_slug}"
        return series_url

    async def _scrape_cpg_series_page(self, series_url: str) -> list[str]:
        """Scrape all CPG issue URLs from series page.

        Args:
            series_url: CPG series URL

        Returns:
            List of CPG issue URLs

        Raises:
            ParseError: If issue links not found
            NetworkError: If request fails
        """
        html = await self._fetch_html(series_url, "cpg")
        soup = BeautifulSoup(html, "html.parser")

        issue_links = soup.select('a[href*="/titles/"]')

        issue_urls = []
        for link in issue_links:
            href = link.get("href")
            if href:
                if href.startswith("/"):
                    parsed = urlparse(series_url)
                    href = f"{parsed.scheme}://{parsed.netloc}{href}"

                path_parts = href.rstrip("/").split("/")
                if len(path_parts) > 4:
                    issue_urls.append(href)

        if not issue_urls:
            self._logger.warning(
                "_scrape_cpg_series_page.no_issues",
                series_url=series_url,
            )

        return issue_urls

    async def _extract_ccl_series_url(self, issue_url: str) -> str:
        """Extract CCL series URL from issue URL by URL manipulation.

        CCL URL structure:
        - Issue: /issue/comic-books/SERIES-SLUG/ISSUE_NUM/GUID
        - Series: /issue/comic-books/SERIES-SLUG

        Args:
            issue_url: CCL issue URL

        Returns:
            CCL series URL
        """
        parsed = urlparse(issue_url)
        path_parts = parsed.path.rstrip("/").split("/")

        if len(path_parts) < 3:
            raise ParseError(
                f"Invalid CCL issue URL structure: {issue_url}",
                source="ccl",
            )

        series_path = "/".join(path_parts[:3])
        series_url = f"{parsed.scheme}://{parsed.netloc}{series_path}"
        return series_url

    async def _scrape_ccl_series_page(self, series_url: str) -> list[str]:
        """Scrape all CCL issue URLs from series page with pagination.

        CCL may paginate large series.
        CCL issue URLs are in the format: /issue/comic-books/SERIES-SLUG/issue-NUM/GUID

        Args:
            series_url: CCL series URL

        Returns:
            List of CCL issue URLs

        Raises:
            ParseError: If issue links not found
            NetworkError: If request fails
        """
        all_issues_set = set()
        page = 1

        while page <= self.max_pages:
            paginated_url = f"{series_url}?page={page}"
            html = await self._fetch_html(paginated_url, "ccl")
            soup = BeautifulSoup(html, "html.parser")

            # Try multiple selectors for CCL issue links
            # CCL uses various link formats across different page layouts
            selectors = [
                'a[href*="/issue/comic-books/"]',
                'a[href*="/issue/"]',
                "a.issue-link",
                'a[href*="comic-books"]',
            ]

            issue_links = []
            for selector in selectors:
                found = soup.select(selector)
                if found:
                    issue_links.extend(found)
                    break  # Use first successful selector

            if not issue_links:
                # No links found on this page, might be end of pagination
                break

            page_had_issues = False
            for link in issue_links:
                href = link.get("href")
                if href and isinstance(href, str):
                    if href.startswith("/"):
                        parsed = urlparse(series_url)
                        href = f"{parsed.scheme}://{parsed.netloc}{href}"

                    # Only add URLs that look like issue URLs (contain GUID)
                    # CCL issue URLs have GUID at the end: /issue/comic-books/X-Men-1991/issue-1/UUID
                    if "/issue/" in href and len(href.rstrip("/").split("/")) >= 6:
                        all_issues_set.add(href)
                        page_had_issues = True

            if not page_had_issues:
                # No valid issue URLs found on this page
                break

            page += 1

        all_issues = list(all_issues_set)

        if not all_issues:
            self._logger.warning(
                "_scrape_ccl_series_page.no_issues",
                series_url=series_url,
            )

        return all_issues

    async def _extract_locg_series_url(self, issue_url: str) -> str:
        """Extract LoCG series URL from issue URL by parsing HTML.

        LoCG issue pages link to series pages in the HTML.

        Args:
            issue_url: LoCG issue URL

        Returns:
            LoCG series URL

        Raises:
            ParseError: If series link not found in HTML
            NetworkError: If request fails
        """
        html = await self._fetch_html(issue_url, "locg")
        soup = BeautifulSoup(html, "html.parser")

        series_link = soup.select_one('a[href*="/comics/series/"]')
        if not series_link or not series_link.get("href"):
            raise ParseError(
                "Series link not found in LoCG issue page",
                source="locg",
            )

        href = series_link["href"]

        if href.startswith("/"):
            parsed = urlparse(issue_url)
            href = f"{parsed.scheme}://{parsed.netloc}{href}"

        return href

    async def _scrape_locg_series_page(self, series_url: str) -> list[str]:
        """Scrape all LoCG issue URLs from series page.

        Args:
            series_url: LoCG series URL

        Returns:
            List of LoCG issue URLs

        Raises:
            ParseError: If issue links not found
            NetworkError: If request fails
        """
        html = await self._fetch_html(series_url, "locg")
        soup = BeautifulSoup(html, "html.parser")

        issue_links = soup.select('a[href*="/comic/"]')

        series_slug = series_url.rstrip("/").split("/")[-1]

        issue_urls = []
        for link in issue_links:
            href = link.get("href")
            if href:
                if href.startswith("/"):
                    parsed = urlparse(series_url)
                    href = f"{parsed.scheme}://{parsed.netloc}{href}"

                link_slug = href.rstrip("/").split("/")[-1]
                if link_slug != series_slug:
                    issue_urls.append(href)

        if not issue_urls:
            self._logger.warning(
                "_scrape_locg_series_page.no_issues",
                series_url=series_url,
            )

        return issue_urls
