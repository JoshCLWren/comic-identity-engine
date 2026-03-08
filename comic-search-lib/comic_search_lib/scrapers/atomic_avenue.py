"""
Atomic Avenue scraper for comic search.

Extracted and simplified from comic-web-scrapers.
Uses httpx instead of aiohttp, no Redis dependency.
"""

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from selectolax.lexbor import LexborHTMLParser

from comic_search_lib.exceptions import NetworkError, RateLimitError
from comic_search_lib.models import Comic, SearchResult, ComicListing, ComicPrice

logger = logging.getLogger(__name__)


class AtomicAvenueScraper:
    """Scraper for Atomic Avenue (atomicavenue.com)."""

    BASE_URL = "https://atomicavenue.com"
    SEARCH_URL = f"{BASE_URL}/atomic/SearchIssues.aspx"

    def __init__(self, timeout: float = 30.0):
        """Initialize scraper.

        Args:
            timeout: HTTP request timeout in seconds
        """
        self.timeout = timeout

    async def search_comic(
        self,
        title: str,
        issue: str,
        year: Optional[int] = None,
        publisher: Optional[str] = None,
    ) -> SearchResult:
        """Search for a comic on Atomic Avenue.

        Args:
            title: Comic title
            issue: Issue number
            year: Optional publication year
            publisher: Optional publisher name

        Returns:
            SearchResult with URL and listings

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

        async with httpx.AsyncClient(follow_redirects=True) as client:
            return await self._search_with_client(comic, client)

    async def _search_with_client(
        self, comic: Comic, client: httpx.AsyncClient
    ) -> SearchResult:
        """Search using an httpx client."""
        result = SearchResult(comic=comic, listings=[], prices=[])

        title_encoded = quote(comic.title, safe="")
        issue_encoded = quote(str(comic.issue), safe="")
        search_url = (
            f"{self.SEARCH_URL}?XT=1&M=1&T={title_encoded}&I={issue_encoded}&PN=1"
        )

        logger.debug(f"Searching AA: {search_url}")

        try:
            response = await client.get(search_url, timeout=self.timeout)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitError(
                    "Rate limited by Atomic Avenue",
                    source="atomic_avenue",
                    original_error=e,
                )
            raise NetworkError(
                f"HTTP error: {e}",
                source="atomic_avenue",
                original_error=e,
                status_code=e.response.status_code,
            )
        except httpx.RequestError as e:
            raise NetworkError(
                f"Network error: {e}",
                source="atomic_avenue",
                original_error=e,
            )

        html = response.text
        logger.debug(f"AA response length: {len(html)}")

        final_url = str(response.url)
        logger.debug(f"Final URL: {final_url}")

        if not html:
            return result

        parser = LexborHTMLParser(html)

        # Check if we were redirected directly to an item/series page
        if "/item/" in final_url:
            logger.debug("Redirected to item page, parsing inventory grid")
            result.url = final_url
            result.source_issue_id = self._extract_issue_id_from_url(final_url)

            listings = self._parse_series_listings(parser, str(comic.issue))

            for listing in listings:
                comic_listing = ComicListing(
                    store=listing.get("seller", "Unknown"),
                    title=f"{comic.title} #{comic.issue}",
                    price=f"${listing.get('price', 0):.2f}"
                    if listing.get("price")
                    else "N/A",
                    grade=listing.get("condition", ""),
                    url=final_url,
                )
                result.listings.append(comic_listing)

                if listing.get("price"):
                    comic_price = ComicPrice(
                        store=listing.get("seller", "Unknown"),
                        value=f"${listing.get('price', 0):.2f}",
                        grade=listing.get("condition", ""),
                        url=final_url,
                    )
                    result.prices.append(comic_price)

            logger.debug(f"Found {len(result.listings)} listings")
            return result

        # Otherwise, parse search results for direct issue listings and series links.
        logger.debug(f"Parsing AA HTML for {comic.title} #{comic.issue}")

        series_list = self._parse_series_results(parser)
        search_result_listings = self._parse_search_results_listings(
            parser, str(comic.issue)
        )

        if search_result_listings:
            best_listing = self._select_best_issue_listing(search_result_listings, comic)
            result.url = best_listing["item_url"] or None
            result.source_issue_id = self._extract_issue_id_from_url(result.url or "")

            for listing in search_result_listings:
                comic_listing = ComicListing(
                    store="Atomic Avenue",
                    title=f"{comic.title} #{comic.issue}",
                    price=f"${listing.get('min_price', 0):.2f}",
                    grade="",
                    url=listing["item_url"],
                )
                result.listings.append(comic_listing)
                result.prices.append(
                    ComicPrice(
                        store="Atomic Avenue",
                        value=f"${listing.get('min_price', 0):.2f}",
                        grade="",
                        url=listing["item_url"],
                    )
                )

            logger.debug(
                "Found %d direct search-result listings for issue #%s",
                len(search_result_listings),
                comic.issue,
            )
            return result

        if not series_list:
            logger.debug("No series found")
            return result

        best_series = self._select_best_series(series_list, comic)
        if not best_series:
            logger.debug("No suitable series match found")
            return result
        series_url = best_series["url"]

        if not series_url.startswith("http"):
            series_url = f"{self.BASE_URL}{series_url}"

        result.url = series_url

        if series_url:
            result.source_issue_id = self._extract_issue_id_from_url(series_url)

        logger.debug(f"Fetching series page: {series_url}")

        try:
            series_response = await client.get(series_url, timeout=self.timeout)
            series_response.raise_for_status()
            series_html = series_response.text

            if series_html:
                series_parser = LexborHTMLParser(series_html)
                listings = self._parse_series_listings(series_parser, str(comic.issue))

                for listing in listings:
                    comic_listing = ComicListing(
                        store=listing.get("seller", "Unknown"),
                        title=f"{comic.title} #{comic.issue}",
                        price=f"${listing.get('price', 0):.2f}"
                        if listing.get("price")
                        else "N/A",
                        grade=listing.get("condition", ""),
                        url=series_url,
                    )
                    result.listings.append(comic_listing)

                    if listing.get("price"):
                        comic_price = ComicPrice(
                            store=listing.get("seller", "Unknown"),
                            value=f"${listing.get('price', 0):.2f}",
                            grade=listing.get("condition", ""),
                            url=series_url,
                        )
                        result.prices.append(comic_price)

                logger.debug(f"Found {len(result.listings)} listings")

        except httpx.HTTPStatusError as e:
            logger.debug(f"Error fetching series page: {e}")
        except httpx.RequestError as e:
            logger.debug(f"Network error fetching series page: {e}")

        return result

    def _parse_series_results(self, parser: LexborHTMLParser) -> List[Dict[str, Any]]:
        """Parse series results from search page."""
        series_list = []

        try:
            title_groups = parser.css("div.title-group")
            for group in title_groups:
                try:
                    link = group.css_first("div.title-group-header h2 a")
                    if not link:
                        continue

                    name = link.text().strip()
                    url = link.attributes.get("href", "")
                    if not name or not url:
                        continue

                    publisher = None
                    year_start = None
                    year_end = None

                    publisher_span = group.css_first("span.title-group-publisher")
                    if publisher_span:
                        publisher_text = publisher_span.text().strip()
                        if "," in publisher_text:
                            parts = publisher_text.split(",", 1)
                            publisher = parts[0].strip()
                            year_start, year_end = self._parse_year_range(parts[1].strip())
                        elif publisher_text:
                            publisher = publisher_text

                    series_list.append(
                        {
                            "name": name,
                            "url": url,
                            "publisher": publisher,
                            "year_start": year_start,
                            "year_end": year_end,
                        }
                    )
                except Exception as e:
                    logger.debug(f"Error parsing title-group series header: {e}")
                    continue

            if series_list:
                return series_list

            title_issues = parser.css_first("ul.titleIssues")
            title_links = []
            if title_issues:
                title_links = title_issues.css("h2.dropLeftMargin a")
                if not title_links:
                    title_links = title_issues.css("li.issueGridRow div.issueTitle a")

            if not title_links:
                title_links = parser.css('a[id*="RepeaterTitleGroups"][id*="lnkTitle"]')

            for link in title_links:
                try:
                    name = link.text().strip()
                    url = link.attributes.get("href", "")

                    if not name or not url:
                        continue

                    publisher = None
                    year_start = None
                    year_end = None

                    parent = link.parent
                    if parent:
                        grandparent = parent.parent
                        if (
                            grandparent
                            and grandparent.tag == "li"
                            and "issueGridRow" in grandparent.attributes.get("class", "")
                        ):
                            info_divs = grandparent.css("div.issueInfo")
                            if info_divs:
                                info_text = info_divs[0].text().strip()
                                parts = info_text.split("•")
                                if len(parts) >= 1:
                                    publisher = parts[0].strip()
                                if len(parts) >= 2:
                                    year_start, year_end = self._parse_year_range(
                                        parts[1].strip()
                                    )
                        elif grandparent:
                            divs = grandparent.css("div.dropLeftMargin")
                            if divs:
                                info_text = divs[0].text().strip()
                                parts = info_text.split(",")
                                if len(parts) >= 1:
                                    publisher = parts[0].strip()
                                if len(parts) >= 2:
                                    year_start, year_end = self._parse_year_range(
                                        parts[1].strip()
                                    )

                    if publisher is None or year_start is None:
                        container = parent.parent if parent and parent.parent else None
                        if container:
                            fallback_divs = container.css("div.dropLeftMargin")
                            for div in fallback_divs:
                                info_text = div.text().strip()
                                if "," not in info_text:
                                    continue
                                parts = info_text.split(",", 1)
                                if publisher is None:
                                    publisher = parts[0].strip()
                                if len(parts) > 1 and year_start is None:
                                    year_start, year_end = self._parse_year_range(
                                        parts[1].strip()
                                    )

                    series_list.append(
                        {
                            "name": name,
                            "url": url,
                            "publisher": publisher,
                            "year_start": year_start,
                            "year_end": year_end,
                        }
                    )

                except Exception as e:
                    logger.debug(f"Error parsing series header: {e}")
                    continue

            return series_list

        except Exception as e:
            logger.error(f"Error parsing series results: {e}")
            return series_list

    def _parse_search_results_listings(
        self, parser: LexborHTMLParser, issue_number: str
    ) -> List[Dict[str, Any]]:
        """Parse direct issue listings from an AA search results page."""
        listings: List[Dict[str, Any]] = []

        try:
            title_groups = parser.css("div.title-group")
            for group in title_groups:
                try:
                    series_link = group.css_first("div.title-group-header h2 a")
                    series_name = series_link.text().strip() if series_link else None
                    publisher = None
                    year_start = None
                    publisher_span = group.css_first("span.title-group-publisher")
                    if publisher_span:
                        publisher_text = publisher_span.text().strip()
                        if "," in publisher_text:
                            parts = publisher_text.split(",", 1)
                            publisher = parts[0].strip()
                            year_start, _ = self._parse_year_range(parts[1].strip())
                        elif publisher_text:
                            publisher = publisher_text

                    issue_cards = group.css("li.issue-card")
                except Exception as exc:
                    logger.debug("Error parsing title-group metadata: %s", exc)
                    issue_cards = []
                    series_name = None
                    publisher = None
                    year_start = None

                for card in issue_cards:
                    try:
                        issue_link = card.css_first("a.issue-label-link")
                        copies_container = card.css_first(".issue-card-copies")
                        if not issue_link or not copies_container:
                            continue

                        issue_text = issue_link.attributes.get("data-issue", "") or issue_link.text().strip()
                        if self._normalize_issue(issue_text) != self._normalize_issue(
                            issue_number
                        ):
                            continue

                        href = issue_link.attributes.get("href", "")
                        if href and not href.startswith("http"):
                            href = f"{self.BASE_URL}{href}"

                        copies_text = copies_container.text().strip()
                        copies_match = re.search(r"(\d+)\s+copies", copies_text, re.IGNORECASE)
                        price_match = re.search(
                            r"from\s+\$([\d.]+)", copies_text, re.IGNORECASE
                        )
                        if not href or not price_match:
                            continue

                        listings.append(
                            {
                                "copies_available": int(copies_match.group(1))
                                if copies_match
                                else 0,
                                "min_price": float(price_match.group(1)),
                                "item_url": href,
                                "series_name": series_name,
                                "publisher": publisher,
                                "year_start": year_start,
                            }
                        )
                    except Exception as exc:
                        logger.debug("Error parsing issue-card listing: %s", exc)
                        continue

            if listings:
                return listings

            issue_cards = parser.css("li.issue-card")
            for card in issue_cards:
                try:
                    issue_link = card.css_first("a.issue-label-link")
                    copies_container = card.css_first(".issue-card-copies")
                    if not issue_link or not copies_container:
                        continue

                    issue_text = issue_link.attributes.get("data-issue", "") or issue_link.text().strip()
                    if self._normalize_issue(issue_text) != self._normalize_issue(
                        issue_number
                    ):
                        continue

                    href = issue_link.attributes.get("href", "")
                    if href and not href.startswith("http"):
                        href = f"{self.BASE_URL}{href}"

                    copies_text = copies_container.text().strip()
                    copies_match = re.search(r"(\d+)\s+copies", copies_text, re.IGNORECASE)
                    price_match = re.search(
                        r"from\s+\$([\d.]+)", copies_text, re.IGNORECASE
                    )
                    if not href or not price_match:
                        continue

                    listings.append(
                        {
                            "copies_available": int(copies_match.group(1))
                            if copies_match
                            else 0,
                            "min_price": float(price_match.group(1)),
                            "item_url": href,
                        }
                    )
                except Exception as exc:
                    logger.debug("Error parsing issue-card listing: %s", exc)
                    continue

            issue_items = parser.css("li.issue.aligntop")
            for item in issue_items:
                try:
                    issue_num_elem = item.css_first(".issueSearchIssueNum")
                    if not issue_num_elem:
                        continue

                    issue_text = issue_num_elem.text().strip()
                    if self._normalize_issue(issue_text) != self._normalize_issue(
                        issue_number
                    ):
                        continue

                    copies_elem = item.css_first(".issueSearchCopies")
                    if not copies_elem:
                        continue

                    copies_text = copies_elem.text().strip()
                    if "no copies" in copies_text.lower():
                        continue

                    copies_match = re.search(r"(\d+)\s+copies", copies_text, re.IGNORECASE)
                    price_match = re.search(
                        r"from\s+\$([\d.]+)", copies_text, re.IGNORECASE
                    )
                    item_link = item.css_first("a[href*='/atomic/item/']")
                    if not item_link or not price_match:
                        continue

                    item_url = item_link.attributes.get("href", "")
                    if item_url and not item_url.startswith("http"):
                        item_url = f"{self.BASE_URL}{item_url}"

                    listings.append(
                        {
                            "copies_available": int(copies_match.group(1))
                            if copies_match
                            else 0,
                            "min_price": float(price_match.group(1)),
                            "item_url": item_url,
                        }
                    )
                except Exception as exc:
                    logger.debug("Error parsing search results listing: %s", exc)
                    continue
        except Exception as exc:
            logger.error("Error parsing AA search results listings: %s", exc)

        return listings

    def _select_best_series(
        self, series_list: List[Dict[str, Any]], comic: Comic
    ) -> Optional[Dict[str, Any]]:
        """Select the best matching series using publisher and year."""
        if not series_list:
            return None

        scored_series = []
        for series in series_list:
            score = 0
            publisher = series.get("publisher")
            year_start = series.get("year_start")
            year_end = series.get("year_end")

            if comic.publisher and publisher:
                if comic.publisher.lower() in publisher.lower():
                    score += 100

            if comic.year and year_start:
                year_diff = abs(comic.year - year_start)
                if year_diff <= 1:
                    score += 50
                elif year_diff <= 3:
                    score += 30
                elif year_diff <= 10:
                    score += 10

            if year_start and year_end:
                score += 5

            scored_series.append((score, series))

        scored_series.sort(key=lambda item: item[0], reverse=True)
        if scored_series and scored_series[0][0] > 0:
            return scored_series[0][1]
        return series_list[0]

    def _select_best_issue_listing(
        self, listings: List[Dict[str, Any]], comic: Comic
    ) -> Dict[str, Any]:
        """Select the best direct issue listing using series metadata."""
        scored = []
        for listing in listings:
            score = 0
            publisher = listing.get("publisher")
            year_start = listing.get("year_start")
            series_name = listing.get("series_name") or ""

            if comic.publisher and publisher:
                if comic.publisher.lower() in publisher.lower():
                    score += 100

            if comic.year and year_start:
                year_diff = abs(comic.year - year_start)
                if year_diff <= 1:
                    score += 50
                elif year_diff <= 3:
                    score += 30
                elif year_diff <= 10:
                    score += 10

            if series_name and self._normalize_title(comic.title) in self._normalize_title(series_name):
                score += 25

            score -= listing.get("min_price", 0.0) / 100.0
            scored.append((score, listing))

        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]

    def _parse_year_range(self, text: str) -> tuple[Optional[int], Optional[int]]:
        """Parse Atomic Avenue year range text."""
        if "-" in text:
            years = text.split("-")
            try:
                start = int(years[0].strip())
            except ValueError:
                return None, None
            try:
                end = int(years[1].strip()) if len(years) > 1 and years[1].strip() else None
            except ValueError:
                end = None
            return start, end

        try:
            return int(text.strip()), None
        except ValueError:
            return None, None

    def _normalize_issue(self, text: str) -> str:
        """Normalize an issue-like string for comparison."""
        match = re.search(r"#\s*(-?\d+(?:\.\d+)?(?:/\d+)?)", text)
        if match:
            return match.group(1)
        match = re.search(r"(-?\d+(?:\.\d+)?(?:/\d+)?)\s*$", text)
        return match.group(0) if match else text.strip()

    def _normalize_title(self, text: str) -> str:
        """Normalize a title for lightweight comparison."""
        normalized = text.lower()
        normalized = re.sub(r"\(.*?\)", "", normalized)
        normalized = normalized.replace("-", " ")
        normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _parse_series_listings(
        self, parser: LexborHTMLParser, issue_number: str
    ) -> List[Dict[str, Any]]:
        """Parse seller listings from series page HTML.

        Args:
            parser: The HTML parser instance
            issue_number: The issue number to filter by

        Returns:
            List of listing dicts with keys: condition, price, seller, rating, notes
        """
        listings = []

        try:
            inventory_grid = parser.css_first(
                "#ctl00_ContentPlaceHolder1_InventoryGrid"
            )

            if not inventory_grid:
                logger.debug("No inventory grid found on series page")
                return listings

            rows = inventory_grid.css("tr.issueGridRow")

            for row in rows:
                try:
                    cells = row.css("td")

                    if len(cells) < 6:
                        continue

                    condition = cells[0].text().strip() if len(cells) > 0 else None

                    price_text = cells[1].text().strip() if len(cells) > 1 else None
                    price = None
                    if price_text:
                        try:
                            price = float(
                                price_text.replace("$", "").replace(",", "").strip()
                            )
                        except (ValueError, AttributeError):
                            pass

                    seller = None
                    if len(cells) > 2:
                        seller_link = cells[2].css_first("a")
                        if seller_link:
                            seller = seller_link.text().strip()

                    rating = None
                    if len(cells) > 3:
                        rating_img = cells[3].css_first("img")
                        if rating_img:
                            rating = rating_img.attributes.get("alt", "")

                    notes = None
                    if len(cells) > 5:
                        col5_text = cells[5].text().strip()
                        if col5_text and col5_text != "&nbsp;":
                            notes = col5_text

                    if seller and price is not None:
                        listings.append(
                            {
                                "condition": condition,
                                "price": price,
                                "seller": seller,
                                "rating": rating,
                                "notes": notes,
                            }
                        )

                except Exception as e:
                    logger.debug(f"Error parsing listing row: {e}")
                    continue

            logger.debug(f"Found {len(listings)} seller listings on series page")
            return listings

        except Exception as e:
            logger.error(f"Error parsing series listings: {e}")
            return listings

    def _extract_issue_id_from_url(self, url: str) -> Optional[str]:
        """Extract issue ID from Atomic Avenue URL."""
        if not url:
            return None
        match = re.search(r"/item/(\d+)", url)
        if match:
            return match.group(1)
        return None
