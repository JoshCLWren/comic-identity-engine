"""League of Comic Geeks (LoCG) scraper implementation.

LoCG search returns series results, not issue results. The working flow is:
1. Search for the series by title/year.
2. Pick the best matching series result.
3. Open the series page.
4. Extract the exact issue link from the series issue list.

This scraper uses a persistent Playwright context because LoCG is guarded by
Cloudflare and is unreliable with plain HTTP requests.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from playwright.async_api import Page, async_playwright

from comic_search_lib.exceptions import SearchError
from comic_search_lib.models.comic import Comic, ComicListing, ComicPrice, SearchResult


logger = logging.getLogger(__name__)


class LoCGScraper:
    """Scraper for League of Comic Geeks."""

    BASE_URL = "https://leagueofcomicgeeks.com"
    SEARCH_URL = f"{BASE_URL}/search"
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    SERIES_LINK_SELECTOR = 'a.link-collection-series[href*="/comics/series/"]'
    ISSUE_LINK_SELECTOR = 'a[href*="/comic/"]'
    ISSUE_ID_PATTERN = re.compile(r"/comic/(\d+)")
    YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")
    ISSUE_COUNT_PATTERN = re.compile(r"^\s*(\d+)")
    MAX_SCROLL_ATTEMPTS = 20
    SCROLL_WAIT_MS = 1200

    def __init__(self, timeout: int = 30):
        """Initialize the LoCG scraper."""
        self.timeout = timeout
        self._playwright = None
        self._context = None

    async def _get_browser_context(self):
        """Get or create a persistent browser context."""
        if self._context is not None:
            return self._context

        user_data_dir = (
            Path(__file__).resolve().parents[3] / ".cache" / "playwright" / "locg"
        )
        user_data_dir.mkdir(parents=True, exist_ok=True)

        self._playwright = await async_playwright().start()
        self._context = await self._playwright.chromium.launch_persistent_context(
            str(user_data_dir),
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--no-first-run",
                "--no-default-browser-check",
                "--force-color-profile=srgb",
            ],
            user_agent=self.DEFAULT_USER_AGENT,
            ignore_https_errors=True,
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            timezone_id="America/Chicago",
        )
        return self._context

    async def close(self) -> None:
        """Close the browser context and Playwright resources."""
        if self._context:
            try:
                await asyncio.wait_for(self._context.close(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Timeout closing LoCG browser context")
            except Exception as exc:
                logger.debug("Error closing LoCG browser context: %s", exc)
            self._context = None

        if self._playwright:
            try:
                await asyncio.wait_for(self._playwright.stop(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Timeout stopping LoCG Playwright instance")
            except Exception as exc:
                logger.debug("Error stopping LoCG Playwright instance: %s", exc)
            self._playwright = None

    async def search_comic(self, comic: Union[Comic, Dict[str, Any]]) -> SearchResult:
        """Search for a comic issue on LoCG."""
        comic_obj = self._coerce_comic(comic)
        search_start = asyncio.get_event_loop().time()

        try:
            context = await self._get_browser_context()
            page = await context.new_page()
            page.set_default_timeout(self.timeout * 1000)

            try:
                await self._apply_stealth(page)

                issue_match = await self._search_issue_workflow(page, comic_obj)
                result = SearchResult(
                    comic=comic_obj,
                    listings=[],
                    prices=[],
                    metadata={
                        "search_time": asyncio.get_event_loop().time() - search_start,
                    },
                )

                if issue_match is None:
                    return result

                result.url = issue_match["url"]
                result.source_issue_id = issue_match["source_issue_id"]
                result.metadata.update(
                    {
                        "series_id": issue_match["series_id"],
                        "series_url": issue_match["series_url"],
                        "series_title": issue_match["series_title"],
                        "series_year": issue_match["series_year"],
                        "query": issue_match["query"],
                    }
                )

                listing = ComicListing(
                    store="League of Comic Geeks",
                    title=issue_match["title"],
                    price="",
                    grade="",
                    url=issue_match["url"],
                    store_type="locg",
                )
                price = ComicPrice(
                    store="League of Comic Geeks",
                    value="",
                    grade="",
                    url=issue_match["url"],
                    store_type="locg",
                )
                result.listings.append(listing)
                result.prices.append(price)
                return result
            finally:
                try:
                    await asyncio.wait_for(page.close(), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("Timeout closing LoCG page")
        except Exception as exc:
            raise SearchError(
                f"Search failed: {exc}",
                source="locg",
                original_error=exc,
            ) from exc

    def _coerce_comic(self, comic: Union[Comic, Dict[str, Any]]) -> Comic:
        """Normalize dict input into a Comic model."""
        if isinstance(comic, Comic):
            return comic

        return Comic(
            id=f"{comic.get('title', '')}-{comic.get('issue', '')}-{comic.get('year', '')}",
            title=comic.get("title", ""),
            issue=comic.get("issue", ""),
            year=comic.get("year"),
            publisher=comic.get("publisher"),
            series_start_year=comic.get("series_start_year"),
            series_end_year=comic.get("series_end_year"),
            metadata=dict(comic.get("metadata", {})),
        )

    async def _apply_stealth(self, page: Page) -> None:
        """Apply the minimal browser patches needed for LoCG."""
        await page.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8
            });
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8
            });
            """
        )

    async def _search_issue_workflow(
        self,
        page: Page,
        comic: Comic,
    ) -> Optional[Dict[str, str]]:
        """Find an issue by searching for its series and scanning the series page."""
        for query in self._build_series_queries(comic):
            series_results = await self._fetch_series_results(page, query)
            if not series_results:
                continue

            series_match = self._select_best_series_match(series_results, comic)
            if not series_match:
                continue

            issue_match = await self._fetch_issue_from_series(page, series_match, comic)
            if issue_match:
                issue_match["query"] = query
                return issue_match

        return None

    def _build_series_queries(self, comic: Comic) -> List[str]:
        """Build LoCG series-search queries in priority order."""
        years: List[int] = []
        for value in (comic.series_start_year, comic.year):
            if value and value not in years:
                years.append(value)

        queries = []
        for year in years:
            queries.append(f"{comic.title} {year}")
        queries.append(comic.title)
        return queries

    async def _fetch_series_results(
        self,
        page: Page,
        query: str,
    ) -> List[Dict[str, Any]]:
        """Search LoCG and extract series results from the page."""
        search_url = f"{self.SEARCH_URL}?keyword={query.replace(' ', '+')}"
        logger.debug("Searching LoCG series results", query=query, url=search_url)

        await page.goto(
            search_url,
            timeout=self.timeout * 1000,
            wait_until="domcontentloaded",
        )
        await page.wait_for_timeout(1500)

        title = await page.title()
        if title.lower().startswith("just a moment"):
            raise SearchError("LoCG Cloudflare challenge blocked search", source="locg")

        return await page.eval_on_selector_all(
            self.SERIES_LINK_SELECTOR,
            """
            (elements) => {
                const deduped = new Map();
                for (const element of elements) {
                    const card = element.closest('li') || element.closest('.card') || element.parentElement;
                    const image = element.querySelector('img');
                    const title = (
                        element.textContent ||
                        image?.getAttribute('alt') ||
                        element.getAttribute('title') ||
                        ''
                    ).trim();
                    const entry = {
                        url: element.href,
                        title,
                        card_text: (card?.innerText || '').trim(),
                        data_id: element.getAttribute('data-id') || '',
                    };

                    const existing = deduped.get(entry.url);
                    if (!existing) {
                        deduped.set(entry.url, entry);
                        continue;
                    }

                    if (!existing.title && entry.title) {
                        deduped.set(entry.url, entry);
                        continue;
                    }

                    if (existing.card_text.length < entry.card_text.length) {
                        deduped.set(entry.url, entry);
                    }
                }

                return Array.from(deduped.values());
            }
            """,
        )

    def _select_best_series_match(
        self,
        series_results: Sequence[Dict[str, Any]],
        comic: Comic,
    ) -> Optional[Dict[str, Any]]:
        """Choose the best LoCG series result for the target comic."""
        target_title = self._normalize_title(comic.title)
        target_tokens = set(target_title.split())
        target_year = comic.series_start_year or comic.year
        target_publisher = self._normalize_publisher(comic.publisher or "")
        target_issue_value = self._parse_numeric_issue(comic.issue)

        best_match: Optional[Dict[str, Any]] = None
        best_score = -1

        for result in series_results:
            title = result.get("title", "")
            if not title:
                continue

            normalized_title = self._normalize_title(title)
            title_tokens = set(normalized_title.split())
            if not target_tokens.issubset(title_tokens):
                continue

            if normalized_title == target_title:
                score = 100
            else:
                extra_tokens = len(title_tokens - target_tokens)
                score = max(10, 70 - (extra_tokens * 10))

            card_text = result.get("card_text", "")
            series_year = self._extract_primary_year(card_text)
            issue_count = self._extract_issue_count(card_text)
            publisher = self._extract_publisher(card_text)
            result["series_year"] = series_year
            result["issue_count"] = issue_count
            result["publisher"] = publisher

            if target_year is not None and series_year is not None:
                score -= min(abs(target_year - series_year), 5)
            elif target_year is not None:
                score -= 3

            normalized_publisher = self._normalize_publisher(publisher or "")
            if target_publisher and normalized_publisher:
                if normalized_publisher == target_publisher:
                    score += 40
                elif (
                    target_publisher in normalized_publisher
                    or normalized_publisher in target_publisher
                ):
                    score += 25

            if target_issue_value is not None and issue_count is not None:
                if issue_count >= target_issue_value:
                    score += 15
                else:
                    score -= 50

            if score > best_score:
                best_score = score
                best_match = result

        return best_match

    async def _fetch_issue_from_series(
        self,
        page: Page,
        series_match: Dict[str, Any],
        comic: Comic,
    ) -> Optional[Dict[str, str]]:
        """Open a series page and extract the exact issue URL."""
        await page.goto(
            series_match["url"],
            timeout=self.timeout * 1000,
            wait_until="domcontentloaded",
        )
        await page.wait_for_timeout(1500)

        previous_count = -1
        stalled_attempts = 0

        for _ in range(self.MAX_SCROLL_ATTEMPTS):
            issue_links = await self._extract_issue_links(page)
            issue_match = self._select_issue_match(issue_links, comic.issue)
            if issue_match is not None:
                source_issue_id = self._extract_source_issue_id(issue_match["url"])
                if source_issue_id is None:
                    return None

                return {
                    "url": issue_match["url"],
                    "title": issue_match["title"],
                    "source_issue_id": source_issue_id,
                    "series_id": self._extract_series_id(series_match["url"]),
                    "series_url": series_match["url"],
                    "series_title": series_match["title"],
                    "series_year": str(series_match.get("series_year") or ""),
                }

            current_count = len(issue_links)
            if current_count <= previous_count:
                stalled_attempts += 1
            else:
                stalled_attempts = 0
                previous_count = current_count

            if stalled_attempts >= 2:
                break

            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(self.SCROLL_WAIT_MS)

        return None

    async def _extract_issue_links(self, page: Page) -> List[Dict[str, str]]:
        """Extract issue links from the current series page state."""
        return await page.eval_on_selector_all(
            self.ISSUE_LINK_SELECTOR,
            """
            (elements) => elements
                .map((element) => ({
                    url: element.href,
                    title: (element.textContent || '').trim(),
                }))
                .filter((item) => item.url.includes('/comic/'))
            """,
        )

    def _select_issue_match(
        self,
        issue_links: Sequence[Dict[str, str]],
        target_issue: str,
    ) -> Optional[Dict[str, str]]:
        """Pick the exact base issue from a series page."""
        normalized_target = self._normalize_issue(target_issue)

        for link in issue_links:
            url = link.get("url", "")
            title = link.get("title", "")
            if not url or not title:
                continue
            if "?variant=" in url:
                continue
            if self._extract_issue_from_title(title) != normalized_target:
                continue
            return link

        return None

    def _normalize_title(self, title: str) -> str:
        """Normalize a series title for matching."""
        normalized = title.lower().strip()
        normalized = re.sub(r"\(.*?\)", "", normalized)
        normalized = normalized.replace("the ", "")
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    def _extract_primary_year(self, text: str) -> Optional[int]:
        """Extract the first year shown in a LoCG series result card."""
        match = self.YEAR_PATTERN.search(text or "")
        if not match:
            return None
        return int(match.group(0))

    def _extract_issue_count(self, text: str) -> Optional[int]:
        """Extract the issue count displayed at the start of a result card."""
        match = self.ISSUE_COUNT_PATTERN.search(text or "")
        if not match:
            return None
        return int(match.group(1))

    def _extract_publisher(self, text: str) -> str:
        """Extract the publisher segment from a LoCG result card."""
        lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
        if len(lines) < 2:
            return ""
        publisher_segment = lines[1].split("·", 1)[0].strip()
        return publisher_segment

    def _extract_issue_from_title(self, title: str) -> Optional[str]:
        """Extract and normalize the issue number from a LoCG issue title."""
        match = re.search(r"#\s*(-?\d+(?:/\d+)?(?:\.\d+)?)", title)
        if not match:
            return None
        return self._normalize_issue(match.group(1))

    def _normalize_issue(self, issue: str) -> str:
        """Normalize issue text for matching."""
        value = (issue or "").strip().lower()
        value = value.lstrip("#")
        return value

    def _normalize_publisher(self, publisher: str) -> str:
        """Normalize publisher text for matching."""
        normalized = (publisher or "").lower().strip()
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        normalized = re.sub(r"\bcomics\b", "", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    def _parse_numeric_issue(self, issue: str) -> Optional[int]:
        """Parse whole-number issue strings used to evaluate issue-count fit."""
        normalized_issue = self._normalize_issue(issue)
        if not normalized_issue.isdigit():
            return None
        return int(normalized_issue)

    def _extract_source_issue_id(self, url: str) -> Optional[str]:
        """Extract the LoCG issue ID from a LoCG issue URL."""
        match = self.ISSUE_ID_PATTERN.search(url)
        if not match:
            return None
        return match.group(1)

    def _extract_series_id(self, url: str) -> str:
        """Extract the LoCG series ID from a series URL."""
        match = re.search(r"/series/(\d+)/", url)
        return match.group(1) if match else ""

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
