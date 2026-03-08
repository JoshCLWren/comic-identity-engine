"""Comic Collector Live (CCL) scraper.

This implementation follows the documented parent-directory HTTP scraper
approach instead of the older Playwright workflow. CCL is accessible via
plain HTTP requests, but in local practice its TLS chain is flaky enough
that the working implementation must disable certificate verification.
"""

import asyncio
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Union

import httpx
from bs4 import BeautifulSoup

from comic_search_lib.exceptions import NetworkError, SearchError
from comic_search_lib.models.comic import Comic, ComicListing, ComicPrice, SearchResult


logger = logging.getLogger(__name__)


class CCLScraper:
    """HTTP-based scraper for Comic Collector Live."""

    BASE_URL = "https://www.comiccollectorlive.com"
    SEARCH_URL = f"{BASE_URL}/titles/comic-books/page-1"
    UUID_PATTERN = re.compile(
        r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"
    )
    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) "
            "Gecko/20100101 Firefox/120.0"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Referer": BASE_URL,
        "X-UserVersion-Developer": "true",
        "Priority": "u=0, i",
    }

    def __init__(
        self,
        timeout: int = 30,
        cookies: Optional[Dict[str, str]] = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.timeout = timeout
        self.cookies = cookies or {}
        self._external_client = client
        self._client: Optional[httpx.AsyncClient] = client

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the shared HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=self.DEFAULT_HEADERS,
                cookies=self.cookies,
                follow_redirects=True,
                timeout=self.timeout,
                verify=False,
            )
        return self._client

    async def close(self) -> None:
        """Close owned HTTP resources."""
        if self._client is not None and self._client is not self._external_client:
            await self._client.aclose()
        self._client = self._external_client

    async def search_comic(self, comic: Union[Comic, Dict[str, Any]]) -> SearchResult:
        """Search for a comic issue on Comic Collector Live."""
        comic_obj = self._coerce_comic(comic)

        try:
            if comic_obj.metadata.get("series_id"):
                result = await self._direct_series_http(
                    comic_obj, str(comic_obj.metadata["series_id"])
                )
                if result.has_results:
                    return result

            title_result = await self._search_by_title_http(comic_obj)

            series_id = title_result.metadata.get("selected_series_id")
            if series_id:
                comic_obj.metadata["series_id"] = series_id
                direct_result = await self._direct_series_http(comic_obj, str(series_id))
                if direct_result.has_results:
                    return direct_result

                if direct_result.metadata.get("auth_failed"):
                    return direct_result

            return title_result
        except httpx.HTTPError as exc:
            raise NetworkError(
                f"CCL request failed: {exc}",
                source="ccl",
                original_error=exc,
            ) from exc
        except SearchError:
            raise
        except Exception as exc:
            raise SearchError(
                f"Search failed: {exc}",
                source="ccl",
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

    async def _search_by_title_http(self, comic: Comic) -> SearchResult:
        """Search CCL series pages by title."""
        client = await self._get_client()
        last_result: Optional[SearchResult] = None

        for query in self._build_search_queries(comic):
            response = await client.get(self.SEARCH_URL, params={"find": query})

            if response.status_code in (401, 403):
                return SearchResult(
                    comic=comic,
                    metadata={
                        "auth_failed": True,
                        "detail": f"HTTP {response.status_code} from title search",
                    },
                )

            response.raise_for_status()
            result = self._parse_search_results_html(response.text, comic)
            result.metadata.setdefault("query", query)
            if result.metadata.get("selected_series_id"):
                return result
            last_result = result

        if last_result is not None:
            return last_result

        return SearchResult(
            comic=comic,
            metadata={"source": "title_search", "detail": "no title queries executed"},
        )

    async def _direct_series_http(self, comic: Comic, series_id: str) -> SearchResult:
        """Navigate straight to a CCL series issue list."""
        client = await self._get_client()
        series_slug = self._build_series_slug(comic.title, comic.year)
        target_issue = self._issue_jump_token(comic.issue)
        filtered_url = (
            f"{self.BASE_URL}/issues/comic-books/{series_slug}/page-1/"
            f"{series_id}?find={urllib.parse.quote(target_issue)}"
        )

        response = await client.get(filtered_url)
        if response.status_code in (401, 403):
            return SearchResult(
                comic=comic,
                metadata={
                    "auth_failed": True,
                    "detail": f"HTTP {response.status_code} from direct series lookup",
                    "series_id": series_id,
                },
            )

        response.raise_for_status()
        result = await self._parse_series_html(response.text, comic, series_id)
        if result.has_results:
            return result

        if self._should_scan_unfiltered_series(comic.issue):
            fallback_result = await self._scan_unfiltered_series_pages(
                comic=comic,
                series_id=series_id,
                series_slug=series_slug,
            )
            if fallback_result.has_results:
                return fallback_result

        return result

    async def _parse_series_html(
        self,
        html: str,
        comic: Comic,
        series_id: str,
    ) -> SearchResult:
        """Parse a series issue grid and follow the matching issue page."""
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.find_all("div", class_="card-issue")
        target_issue = self._normalize_issue(comic.issue)

        for card in cards:
            issue_text = self._extract_issue_text(card)
            if issue_text is None or self._normalize_issue(issue_text) != target_issue:
                continue

            link = card.select_one('a[id*="imgLink"]')
            if link is None:
                continue

            href = str(link.get("href", "")).strip()
            detail_url = urllib.parse.urljoin(self.BASE_URL, href)
            image = card.find("img", class_="img-responsive")
            image_url = str(image.get("src", "")).strip() if image else None

            return await self._fetch_issue_detail_page(
                detail_url=detail_url,
                comic=comic,
                series_id=series_id,
                image_url=image_url,
            )

        return SearchResult(
            comic=comic,
            metadata={
                "source": "direct_series",
                "no_match": True,
                "series_id": series_id,
                "detail": f"no issue card matched issue {comic.issue}",
            },
        )

    async def _fetch_issue_detail_page(
        self,
        detail_url: str,
        comic: Comic,
        series_id: str,
        image_url: Optional[str],
    ) -> SearchResult:
        """Fetch the issue detail page and parse vendor listings."""
        client = await self._get_client()
        response = await client.get(detail_url)

        if response.status_code in (401, 403):
            return SearchResult(
                comic=comic,
                url=detail_url,
                metadata={
                    "auth_failed": True,
                    "series_id": series_id,
                    "detail": f"HTTP {response.status_code} from issue detail lookup",
                },
            )

        response.raise_for_status()

        listings = self._parse_issue_detail_page(
            html=response.text,
            comic=comic,
            detail_url=detail_url,
            image_url=image_url,
        )
        prices = [
            ComicPrice(
                store=listing.store,
                value=listing.price,
                grade=listing.grade,
                url=listing.url,
                store_type="ccl",
                metadata=dict(listing.metadata),
            )
            for listing in listings
        ]

        source_issue_id = self._extract_issue_uuid(detail_url)
        metadata: Dict[str, Any] = {
            "source": "direct_series",
            "series_id": series_id,
        }
        if not listings:
            metadata["detail"] = "issue page loaded but no vendor boxes were present"

        return SearchResult(
            comic=comic,
            listings=listings,
            prices=prices,
            metadata=metadata,
            url=detail_url,
            source_issue_id=source_issue_id,
        )

    def _parse_search_results_html(self, html: str, comic: Comic) -> SearchResult:
        """Parse the title search results page and choose the best series UUID."""
        soup = BeautifulSoup(html, "html.parser")
        series_candidates: list[dict[str, Any]] = []

        for element in soup.find_all(id=True):
            element_id = str(element.get("id", "")).strip()
            if not self.UUID_PATTERN.fullmatch(element_id):
                continue

            title_text = element.get_text(" ", strip=True)
            if not title_text:
                continue

            series_candidates.append(
                {
                    "series_id": element_id,
                    "title_text": title_text,
                    "year": self._extract_year_from_series_text(title_text),
                }
            )

        selected_series_id = self._select_best_series_id(series_candidates, comic)
        metadata: Dict[str, Any] = {
            "source": "title_search",
            "series_ids": [item["series_id"] for item in series_candidates],
            "selected_series_id": selected_series_id,
        }

        if not series_candidates:
            metadata["no_results"] = True
            metadata["detail"] = f"no CCL series results for {comic.title}"
        elif selected_series_id is None:
            metadata["detail"] = "series results found but no candidate survived scoring"

        return SearchResult(
            comic=comic,
            metadata=metadata,
        )

    def _select_best_series_id(
        self,
        series_candidates: list[dict[str, Any]],
        comic: Comic,
    ) -> Optional[str]:
        """Choose the best-matching CCL series UUID."""
        if not series_candidates:
            return None

        normalized_target = self._normalize_title(comic.title)
        scored: list[tuple[int, str]] = []

        for candidate in series_candidates:
            title_text = str(candidate["title_text"])
            display_title = self._extract_display_title(title_text)
            normalized_candidate = self._normalize_title(display_title)
            score = 0

            if normalized_target and normalized_candidate == normalized_target:
                score += 200
            elif normalized_target and normalized_candidate.startswith(
                f"{normalized_target} "
            ):
                score += 150
            elif normalized_target and normalized_target in normalized_candidate:
                score += 100

            candidate_year = candidate.get("year")
            if comic.year is not None and candidate_year is not None:
                year_delta = abs(candidate_year - comic.year)
                if year_delta == 0:
                    score += 25
                elif year_delta <= 2:
                    score += 10
                elif year_delta <= 5:
                    score += 3

            if comic.publisher:
                if comic.publisher.lower() in title_text.lower():
                    score += 10

            scored.append((score, str(candidate["series_id"])))

        scored.sort(reverse=True)
        return scored[0][1]

    def _extract_display_title(self, title_text: str) -> str:
        """Extract the series title portion from a CCL search result line."""
        match = re.match(r"^(.*?)\s+Comic Book\b", title_text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return title_text.strip()

    def _parse_issue_detail_page(
        self,
        html: str,
        comic: Comic,
        detail_url: str,
        image_url: Optional[str],
    ) -> List[ComicListing]:
        """Parse vendor listings from an issue detail page."""
        soup = BeautifulSoup(html, "html.parser")
        listings: List[ComicListing] = []

        for vendor_box in soup.find_all("div", class_="profile-box-contact"):
            listing = self._parse_vendor_box(
                vendor_box=vendor_box,
                comic=comic,
                detail_url=detail_url,
                image_url=image_url,
            )
            if listing is not None:
                listings.append(listing)

        return listings

    def _parse_vendor_box(
        self,
        vendor_box,
        comic: Comic,
        detail_url: str,
        image_url: Optional[str],
    ) -> Optional[ComicListing]:
        """Parse one vendor box from an issue detail page."""
        store_link = vendor_box.select_one(".profile-box-header a.txt-white")
        if store_link is None:
            return None

        store_name = store_link.get_text(" ", strip=True)
        username_element = vendor_box.select_one(".job-position")
        username = (
            username_element.get_text(" ", strip=True) if username_element else None
        )

        option = vendor_box.select_one("select option")
        if option is None:
            return None

        option_text = option.get_text(" ", strip=True)
        price, grade = self._parse_price_grade(option_text)
        if price is None:
            return None

        return ComicListing(
            store=store_name,
            title=f"{comic.title} #{comic.issue}",
            price=price,
            grade=grade,
            url=detail_url,
            image_url=image_url,
            store_type="ccl",
            metadata={
                "username": username,
                "price_float": float(price.replace("$", "")),
                "series_id": self._extract_series_uuid(detail_url),
            },
        )

    def _parse_price_grade(self, option_text: str) -> tuple[Optional[str], Optional[str]]:
        """Parse the first vendor price/grade option."""
        match = re.match(
            r"\$(?P<price>[0-9.]+)\s*-\s*(?P<grade>[A-Z0-9/+\-.]+)",
            option_text,
            flags=re.IGNORECASE,
        )
        if match:
            return f"${match.group('price')}", match.group("grade").strip()

        price_match = re.search(r"\$([0-9.]+)", option_text)
        if price_match:
            return f"${price_match.group(1)}", None

        return None, None

    def _extract_issue_text(self, card) -> Optional[str]:
        """Extract the issue token from a series issue card."""
        issue_element = card.select_one("div.text-center.small b:nth-of-type(2)")
        if issue_element is None:
            return None
        return issue_element.get_text(strip=True)

    def _extract_year_from_series_text(self, text: str) -> Optional[int]:
        """Extract a plausible series year from CCL search result text."""
        match = re.search(r"\b(19|20)\d{2}\b", text)
        if not match:
            return None
        return int(match.group(0))

    def _build_series_slug(self, title: str, year: Optional[int]) -> str:
        """Build the CCL series slug used by the issues endpoint."""
        clean = re.sub(r"[^\w\s-]", "", title).strip()
        clean = re.sub(r"\s+", "-", clean)
        if year is not None:
            return f"{clean}-{year}"
        return clean

    async def _scan_unfiltered_series_pages(
        self,
        comic: Comic,
        series_id: str,
        series_slug: str,
        max_pages: int = 12,
    ) -> SearchResult:
        """Scan raw series pages when CCL's issue jump fails for special issues."""
        client = await self._get_client()

        for page in range(1, max_pages + 1):
            url = (
                f"{self.BASE_URL}/issues/comic-books/{series_slug}/page-{page}/"
                f"{series_id}"
            )
            response = await client.get(url)
            response.raise_for_status()

            result = await self._parse_series_html(response.text, comic, series_id)
            if result.has_results:
                result.metadata.setdefault("detail", f"found via unfiltered page {page}")
                return result

            soup = BeautifulSoup(response.text, "html.parser")
            if not soup.find("div", class_="card-issue"):
                break

        return SearchResult(
            comic=comic,
            metadata={
                "source": "direct_series_scan",
                "series_id": series_id,
                "detail": f"unfiltered series scan exhausted {max_pages} pages",
            },
        )

    def _should_scan_unfiltered_series(self, issue: str) -> bool:
        """Return True when the filtered CCL issue jump is likely unreliable."""
        normalized = self._normalize_issue(issue)
        if normalized.startswith("-"):
            return True
        if not re.fullmatch(r"\d+(?:\.\d+)?", normalized):
            return True
        return False

    def _build_search_queries(self, comic: Comic) -> list[str]:
        """Build CCL search queries in the order that works on the live site."""
        normalized = re.sub(r"[^a-z0-9]+", "", comic.title.lower())
        spaced = self._normalize_title(comic.title)
        queries: list[str] = []

        if comic.year is not None and normalized:
            queries.append(f"{normalized} {comic.year}")
        if normalized:
            queries.append(normalized)
        if comic.year is not None and spaced:
            queries.append(f"{spaced} {comic.year}")
        if spaced:
            queries.append(spaced)

        deduped: list[str] = []
        for query in queries:
            if query and query not in deduped:
                deduped.append(query)
        return deduped

    def _issue_jump_token(self, issue: str) -> str:
        """Choose the token CCL expects in the issue jump query."""
        normalized = self._normalize_issue(issue)
        if normalized == "":
            return ""
        return normalized

    def _normalize_title(self, text: str) -> str:
        """Normalize title text for loose matching."""
        normalized = text.lower()
        normalized = re.sub(r"\s*\(.*?\)", "", normalized)
        normalized = re.sub(r"[^a-z0-9\s-]", " ", normalized)
        normalized = normalized.replace("-", " ")
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _normalize_issue(self, issue: str) -> str:
        """Normalize issue numbers without changing special values like -1."""
        return issue.strip().lower()

    def _extract_issue_uuid(self, url: str) -> Optional[str]:
        """Extract issue UUID from a CCL issue URL."""
        match = self.UUID_PATTERN.search(url)
        return match.group(0) if match else None

    def _extract_series_uuid(self, url: str) -> Optional[str]:
        """Extract series UUID from a CCL series URL."""
        match = re.search(
            r"/page-\d+/(" + self.UUID_PATTERN.pattern + r")(?:\?|$)",
            url,
        )
        if match:
            return match.group(1)
        return None

    async def search_comics(
        self, comics: List[Union[Comic, Dict[str, Any]]]
    ) -> List[SearchResult]:
        """Search multiple comics in parallel."""
        return await asyncio.gather(*(self.search_comic(comic) for comic in comics))

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
