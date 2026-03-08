"""
HipComics scraper implementation.

This module provides functionality to scrape comic data from HipComic.com,
focusing on finding the best prices for wishlist items.
"""

import asyncio
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Union

import httpx

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

    PLATFORM_URL = "https://www.hipcomic.com"
    CATALOG_API_URL = "https://catalog.hipcomic.com/api"

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
        self._catalog_token: Optional[str] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            headers = {
                "User-Agent": self._browser_user_agent(),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": self.PLATFORM_URL,
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

    def _browser_user_agent(self) -> str:
        """Return the browser user agent for HipComic requests."""
        return os.getenv(
            "HIPCOMIC_USER_AGENT",
            "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0",
        )

    def _catalog_headers(
        self, token: str, referer: str = "https://www.hipcomic.com/"
    ) -> dict[str, str]:
        """Build request headers for HipComic catalog API calls."""
        return {
            "User-Agent": self._browser_user_agent(),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": referer,
            "X-Requested-With": "XMLHttpRequest",
            "is-app": "0",
            "is-pwa": "0",
            "is-mobile": "0",
            "is-mobile-device": "0",
            "browser": os.getenv("HIPCOMIC_BROWSER", "Firefox"),
            "platform": os.getenv("HIPCOMIC_PLATFORM", "Linux"),
            "Origin": self.PLATFORM_URL,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Authorization": f"Bearer {token}",
        }

    def _login_headers(self) -> dict[str, str]:
        """Build request headers for HipComic authentication calls."""
        headers = self._catalog_headers(
            token=os.getenv("HIPCOMIC_GUEST_BEARER", ""),
            referer=f"{self.PLATFORM_URL}/",
        )
        headers["Sec-Fetch-Site"] = "same-origin"
        if token := headers.get("Authorization"):
            headers["Cookie"] = self._auth_cookie_header(token.removeprefix("Bearer "))
        headers.pop("Authorization", None)
        return headers

    def _auth_cookie_header(self, guest_token: str) -> str:
        """Build a cookie header for HipComic auth requests."""
        cookie_pairs = [
            ("i18n_redirected", "en"),
            ("JkKSMfEWUserToken", os.getenv("HIPCOMIC_USER_TOKEN", "")),
            ("JkKSMfEWCountryToken", os.getenv("HIPCOMIC_COUNTRY_TOKEN", "")),
            ("auth.strategy", "hybridJwt"),
            ("PHPSESSID", os.getenv("HIPCOMIC_PHPSESSID", "")),
            ("cf_clearance", os.getenv("HIPCOMIC_CF_CLEARANCE", "")),
            ("auth._token.hybridJwt", f"Bearer {guest_token}" if guest_token else ""),
            ("auth._refresh_token.hybridJwt", "false"),
        ]
        return "; ".join(f"{key}={value}" for key, value in cookie_pairs if value)

    async def _get_catalog_token(self, client: httpx.AsyncClient) -> Optional[str]:
        """Return an authenticated token for HipComic catalog API access."""
        if self._catalog_token:
            return self._catalog_token

        guest_token = os.getenv("HIPCOMIC_GUEST_BEARER")
        username = os.getenv("HIPCOMIC_AUTH_USERNAME")
        password = os.getenv("HIPCOMIC_AUTH_PASSWORD")

        if username and password and guest_token:
            try:
                response = await client.post(
                    f"{self.PLATFORM_URL}/api/authenticate",
                    files={
                        "username": (None, username),
                        "password": (None, password),
                        "remember_me": (None, "0"),
                    },
                    headers=self._login_headers(),
                )
                response.raise_for_status()
                token = response.json().get("token")
                if token:
                    self._catalog_token = token
                    return token
            except Exception:
                logger.debug("HipComic auth refresh failed; falling back to guest token")

        if guest_token:
            self._catalog_token = guest_token
            return guest_token

        return None

    async def _fetch_catalog_json(
        self,
        client: httpx.AsyncClient,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        token: Optional[str] = None,
        referer: str = "https://www.hipcomic.com/",
    ) -> Dict[str, Any]:
        """Fetch JSON from HipComic's catalog API."""
        auth_token = token or await self._get_catalog_token(client)
        if not auth_token:
            return {}

        response = await client.get(
            f"{self.CATALOG_API_URL}{path}",
            params=params,
            headers=self._catalog_headers(auth_token, referer=referer),
        )
        response.raise_for_status()
        return response.json()

    def _normalize_series_title(self, title: str) -> str:
        """Normalize a series title for Hip volume matching."""
        normalized = title.lower()
        normalized = re.sub(r"\(\d{4}\)", "", normalized)
        normalized = normalized.replace("-", " ")
        normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if normalized.startswith("the "):
            normalized = normalized[4:]
        return normalized

    def _score_volume_match(self, volume: Dict[str, Any], comic: Comic) -> float:
        """Score how well a HipComic volume matches the target comic."""
        target = self._normalize_series_title(comic.title)
        target_year = comic.series_start_year
        target_issue_year = comic.year
        target_publisher = (comic.publisher or "").strip().lower()
        name = volume.get("name") or ""
        candidate = self._normalize_series_title(name)
        if not candidate:
            return -1

        if candidate == target:
            score = 100.0
        elif candidate.startswith(target) or target in candidate:
            score = 70.0
        else:
            return -1

        start_year = volume.get("startYear")
        if target_year and str(start_year) == str(target_year):
            score += 20
        elif target_issue_year and str(start_year) == str(target_issue_year):
            score += 8

        publisher = ((volume.get("publisher") or {}).get("name") or "").lower()
        if target_publisher and publisher == target_publisher:
            score += 10

        issue_count = int(volume.get("issueCount") or 0)
        score += min(issue_count, 999) / 1000
        return score

    def _rank_candidate_volumes(
        self, volumes: List[Dict[str, Any]], comic: Comic
    ) -> List[Dict[str, Any]]:
        """Rank plausible HipComic volumes from best to worst match."""
        scored_volumes: list[tuple[float, Dict[str, Any]]] = []
        for volume in volumes:
            score = self._score_volume_match(volume, comic)
            if score >= 0:
                scored_volumes.append((score, volume))

        scored_volumes.sort(key=lambda item: item[0], reverse=True)
        return [volume for _, volume in scored_volumes]

    def _select_best_volume(
        self, volumes: List[Dict[str, Any]], comic: Comic
    ) -> Optional[Dict[str, Any]]:
        """Choose the best HipComic volume from catalog search results."""
        ranked = self._rank_candidate_volumes(volumes, comic)
        return ranked[0] if ranked else None

    async def _search_catalog_volumes(
        self, comic: Comic, client: httpx.AsyncClient, token: str
    ) -> List[Dict[str, Any]]:
        """Search HipComic catalog volumes for the target series."""
        queries = [comic.title]
        if comic.series_start_year:
            queries.insert(0, f"{comic.title} {comic.series_start_year}")

        volumes_by_uri: Dict[str, Dict[str, Any]] = {}
        for query in queries:
            data = await self._fetch_catalog_json(
                client,
                "/volumes",
                params={
                    "search": query,
                    "page": 1,
                    "itemsPerPage": 50,
                    "order[issueCount]": "DESC",
                },
                token=token,
            )
            for volume in data.get("hydra:member", []):
                uri = volume.get("uri")
                if uri:
                    volumes_by_uri[uri] = volume

        all_volumes = list(volumes_by_uri.values())
        us_volumes = [
            volume
            for volume in all_volumes
            if str(volume.get("uri") or "").startswith("/us/")
        ]
        return us_volumes or all_volumes

    async def _search_catalog_issues(
        self,
        comic: Comic,
        client: httpx.AsyncClient,
        token: str,
        volume: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Fetch HipComic catalog issues for a volume and exact issue number."""
        volume_uri = volume.get("uri")
        if not volume_uri:
            return []

        data = await self._fetch_catalog_json(
            client,
            "/issues",
            params={
                "volume.uri": volume_uri,
                "issueNumber": comic.issue,
                "page": 1,
                "itemsPerPage": 10,
            },
            token=token,
        )
        return data.get("hydra:member", [])

    def _build_catalog_listing(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        """Map a HipComic catalog issue to a listing-like dictionary."""
        volume = issue.get("volume") or {}
        volume_name = volume.get("name") or ""
        issue_number = issue.get("issueNumber") or ""
        story_name = issue.get("name") or ""
        suggested_price = issue.get("suggestedPrice") or 0.0
        uri = issue.get("uri") or ""

        if story_name:
            display_name = f"{volume_name} #{issue_number} {story_name}".strip()
        else:
            display_name = f"{volume_name} #{issue_number}".strip()

        return {
            "store": "HipComic Price Guide",
            "name": display_name,
            "item_title": volume_name,
            "raw_item_title": display_name,
            "price": f"${float(suggested_price):.2f}",
            "grade": "Guide",
            "url": f"{self.PLATFORM_URL}/price-guide{uri}" if uri else "",
            "image_url": issue.get("imageUrl", ""),
            "title": volume_name,
            "type": "hip",
            "issue_number": issue_number,
            "source_issue_id": str(issue.get("@id", "")).rsplit("/", 1)[-1],
            "key": f"{volume_name}|{issue_number}",
        }

    async def _search_catalog_api(
        self, comic: Comic, client: httpx.AsyncClient
    ) -> List[Dict[str, Any]]:
        """Search HipComic's authenticated catalog API for an exact issue."""
        token = await self._get_catalog_token(client)
        if not token:
            return []

        volumes = await self._search_catalog_volumes(comic, client, token)
        ranked_volumes = self._rank_candidate_volumes(volumes, comic)
        for volume in ranked_volumes[:10]:
            issues = await self._search_catalog_issues(comic, client, token, volume)
            if issues:
                return [
                    self._build_catalog_listing(issue)
                    for issue in issues
                    if issue.get("uri")
                ]

        return []

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
                if item.get("issue_number"):
                    setattr(listing, "issue_number", item["issue_number"])
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

            if search_result.listings:
                search_result.url = search_result.listings[0].url
                if results[0].get("source_issue_id"):
                    search_result.source_issue_id = results[0]["source_issue_id"]

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
        try:
            return await self._search_catalog_api(comic, client)

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
