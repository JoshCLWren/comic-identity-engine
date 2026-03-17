"""HipComic (HIP) adapter implementation.

This adapter ingests data from HipComic.com price guide pages and maps it
to internal candidate models. HIP uses a web interface with HTML parsing.

HIP URL patterns:
- hipcomic.com/price-guide/us/marvel/comic/SERIES_SLUG/ISSUE_ENCODED/
- hipcomic.com/price-guide/us/marvel/comic/SERIES_SLUG/ISSUE_ENCODED/VARIANT_SLUG/

Note: HIP uses special encoding for negative issue numbers:
- "-1" is encoded as "1-1"
- This encoding is handled in the issue number parsing
"""

import re
from datetime import date
from typing import Any

import httpx

from comic_identity_engine.adapters import (
    NotFoundError,
    SourceAdapter,
    SourceError,
    ValidationError,
)
from longbox_commons import parse_issue_candidate
from longbox_commons.models import IssueCandidate, SeriesCandidate
from scrapekit import HttpClient


class HIPAdapter(SourceAdapter):
    """Adapter for HipComic.com price guide.

    This adapter fetches data from HipComic.com and maps it to internal
    candidate models.
    """

    SOURCE = "hip"
    BASE_URL = "https://www.hipcomic.com"

    def __init__(
        self,
        http_client: HttpClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize HIP adapter.

        Args:
            http_client: Optional HTTP client for making requests
            timeout: HTTP request timeout in seconds (used if http_client not provided)
        """
        super().__init__(http_client)
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/133.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "max-age=0",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "document",
            "sec-ch-ua": (
                '"Chromium";v="133", "Not(A:Brand";v="99", "Google Chrome";v="133"'
            ),
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }

    async def fetch_series(self, source_series_id: str) -> SeriesCandidate:
        """Fetch series from HIP price guide.

        Args:
            source_series_id: HIP series slug (e.g., "x-men-1991")

        Returns:
            SeriesCandidate with validated metadata

        Raises:
            NotImplementedError: HIP does not have traditional series pages
            ValidationError: Required fields missing
        """
        raise NotImplementedError(
            "HIP does not have traditional series pages like other platforms. "
            "Use fetch_series_from_payload() with pre-fetched HTML instead."
        )

    async def fetch_issue(
        self, source_issue_id: str, full_url: str | None = None
    ) -> IssueCandidate:
        """Fetch issue from HIP price guide.

        Args:
            source_issue_id: HIP listing ID or encoded issue identifier
            full_url: Optional canonical HipComic price-guide URL

        Returns:
            IssueCandidate with validated metadata

        Raises:
            NotFoundError: Issue not found on HIP (404)
            ValidationError: Required fields missing or issue number invalid
            SourceError: Network or HTTP error
        """
        if self.http_client is None:
            raise SourceError("HTTP client not initialized")

        if full_url:
            try:
                response = await self.http_client.get(full_url, headers=self.headers)
                response.raise_for_status()
                return self.fetch_issue_from_payload(
                    source_issue_id, {"html": response.text}
                )
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 404:
                    raise SourceError(f"HTTP error fetching issue: {e}") from e
            except httpx.RequestError as e:
                raise SourceError(f"Network error fetching issue: {e}") from e

        # Try the listing URL pattern first
        urls = [
            f"{self.BASE_URL}/listing/{source_issue_id}",
            f"{self.BASE_URL}/new-comic-listings/{source_issue_id}",
        ]

        last_error = None
        for url in urls:
            try:
                response = await self.http_client.get(url, headers=self.headers)
                response.raise_for_status()
                # Success - parse the HTML
                return self.fetch_issue_from_payload(
                    source_issue_id, {"html": response.text}
                )
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    # Try next URL pattern
                    last_error = e
                    continue
                raise SourceError(f"HTTP error fetching issue: {e}") from e
            except httpx.RequestError as e:
                raise SourceError(f"Network error fetching issue: {e}") from e

        # All URLs returned 404
        raise NotFoundError(f"Issue not found: {source_issue_id}") from last_error

    def fetch_series_from_payload(
        self, source_series_id: str, payload: dict[str, Any]
    ) -> SeriesCandidate:
        """Parse series from pre-fetched HIP HTML payload.

        Args:
            source_series_id: HIP series slug (e.g., "x-men-1991")
            payload: Dict containing 'html' key with raw HIP page HTML

        Returns:
            SeriesCandidate with validated metadata

        Raises:
            ValidationError: Required fields missing or HTML invalid
        """
        if not payload:
            raise ValidationError("HIP series payload is empty")

        html = payload.get("html", "")
        if not html:
            raise ValidationError("HIP series payload missing 'html' field")

        series_data = self._extract_series_from_html(html)
        if not series_data:
            raise ValidationError(
                "Could not extract series data from HIP HTML - "
                "page may be malformed or use unexpected format"
            )

        series_title = series_data.get("title")
        if not series_title:
            raise ValidationError("HIP series missing required field: title")

        start_year = series_data.get("start_year")
        if start_year is None:
            raise ValidationError("HIP series missing required field: start_year")

        publisher = series_data.get("publisher")

        return SeriesCandidate(
            source=self.SOURCE,
            source_series_id=source_series_id,
            series_title=series_title,
            series_start_year=start_year,
            publisher=publisher,
            series_end_year=series_data.get("end_year"),
            raw_payload=payload,
        )

    def fetch_issue_from_payload(
        self, source_issue_id: str, payload: dict[str, Any]
    ) -> IssueCandidate:
        """Parse issue from pre-fetched HIP HTML payload.

        Args:
            source_issue_id: HIP issue ID (encoded issue number, e.g., "1-1")
            payload: Dict containing 'html' key with raw HIP page HTML

        Returns:
            IssueCandidate with validated metadata

        Raises:
            ValidationError: Required fields missing or issue number invalid
        """
        if not payload:
            raise ValidationError("HIP issue payload is empty")

        html = payload.get("html", "")
        if not html:
            raise ValidationError("HIP issue payload missing 'html' field")

        issue_data = self._extract_issue_from_html(html)
        if not issue_data:
            raise ValidationError(
                "Could not extract issue data from HIP HTML - "
                "page may be malformed or use unexpected format"
            )

        raw_number = issue_data.get("issue_number", "")
        if not raw_number:
            raise ValidationError("HIP issue missing required field: issue_number")

        series_title = issue_data.get("series_title")
        if not series_title:
            raise ValidationError("HIP issue missing required field: series_title")

        parse_result = parse_issue_candidate(raw_number)
        if not parse_result.success:
            raise ValidationError(
                f"Invalid issue number '{raw_number}': {parse_result.error_code}"
            )

        if parse_result.canonical_issue_number is None:
            raise ValidationError(
                f"Issue number '{raw_number}' parsed successfully but produced no canonical form"
            )

        start_year = issue_data.get("start_year")
        publisher = issue_data.get("publisher")

        variant_suffix = issue_data.get("variant_suffix") or parse_result.variant_suffix
        variant_name = issue_data.get("variant_name")
        cover_date = issue_data.get("cover_date")
        publication_date = issue_data.get("publication_date")

        price = self._parse_price(issue_data.get("price"))
        page_count = issue_data.get("page_count")
        upc = issue_data.get("upc")

        return IssueCandidate(
            source=self.SOURCE,
            source_series_id=issue_data.get("series_slug", ""),
            source_issue_id=source_issue_id,
            series_title=series_title,
            series_start_year=start_year,
            publisher=publisher,
            issue_number=parse_result.canonical_issue_number,
            variant_suffix=variant_suffix,
            cover_date=cover_date,
            publication_date=publication_date,
            price=price,
            page_count=page_count,
            upc=upc,
            variant_name=variant_name,
            raw_payload=payload,
        )

    def _extract_series_from_html(self, html: str) -> dict[str, Any] | None:
        """Extract series metadata from HIP HTML.

        Args:
            html: Raw HIP page HTML

        Returns:
            Dict with series metadata or None if extraction fails
        """
        from selectolax.lexbor import LexborHTMLParser

        parser = LexborHTMLParser(html)

        result: dict[str, Any] = {}

        title_elem = parser.css_first("h1")
        if title_elem:
            title_text = title_elem.text().strip()
            series_title, start_year = self._parse_hip_title(title_text)
            if series_title:
                result["title"] = series_title
            if start_year is not None:
                result["start_year"] = start_year

        publisher_elem = parser.css_first(".publisher, [class*='publisher']")
        if publisher_elem:
            result["publisher"] = publisher_elem.text().strip()

        year_match = re.search(r"\((\d{4})\)", html)
        if year_match and "start_year" not in result:
            result["start_year"] = int(year_match.group(1))

        return result if result else None

    def _extract_issue_from_html(self, html: str) -> dict[str, Any] | None:
        """Extract issue metadata from HIP HTML.

        Args:
            html: Raw HIP issue page HTML

        Returns:
            Dict with issue metadata or None if extraction fails
        """
        from selectolax.lexbor import LexborHTMLParser

        parser = LexborHTMLParser(html)

        result: dict[str, Any] = {}

        title_elem = parser.css_first("h1")
        if title_elem and title_elem.text().strip():
            title_text = title_elem.text().strip()
            series_title, start_year = self._parse_hip_title(title_text)
            if series_title:
                result["series_title"] = series_title
            if start_year is not None:
                result["start_year"] = start_year

        detail_attributes = self._extract_detail_attributes(parser)
        series_text = detail_attributes.get("series")
        if series_text and "series_title" not in result:
            series_title, start_year = self._parse_hip_title(series_text)
            if series_title:
                result["series_title"] = series_title
            if start_year is not None:
                result["start_year"] = start_year

        issue_text = detail_attributes.get("issue")
        if issue_text:
            result["issue_number"] = self._clean_issue_number(issue_text)

        publisher_text = detail_attributes.get("publisher")
        if publisher_text:
            result["publisher"] = publisher_text

        issue_number_elem = parser.css_first(".issue-number, [class*='issue-number']")
        if issue_number_elem:
            issue_text = issue_number_elem.text().strip()
            result["issue_number"] = self._clean_issue_number(issue_text)
        elif "issue_number" not in result:
            return None

        publisher_elem = parser.css_first(
            ".publisher, [class*='publisher-name'], [class*='publisher-info']"
        )
        if publisher_elem:
            result["publisher"] = publisher_elem.text().strip()

        series_slug_match = re.search(r"/comic/([^/]+)/", html)
        if series_slug_match:
            result["series_slug"] = series_slug_match.group(1)

        date_elem = parser.css_first(
            ".cover-date, [class*='cover-date'], [class*='publication-date']"
        )
        if date_elem:
            result["cover_date"] = self._parse_date(date_elem.text().strip())

        variant_elem = parser.css_first(".variant, [class*='variant-']")
        if variant_elem:
            variant_text = variant_elem.text().strip()
            result["variant_name"] = variant_text
            result["variant_suffix"] = self._extract_variant_suffix(variant_text)

        price_elem = parser.css_first(".price, [class*='price-'], [class*='pricing']")
        if price_elem:
            result["price"] = price_elem.text().strip()

        page_count_elem = parser.css_first(".page-count, [class*='page-count-']")
        if page_count_elem:
            result["page_count"] = self._parse_page_count(
                page_count_elem.text().strip()
            )

        upc_elem = parser.css_first(
            ".upc, .barcode, [class*='upc-'], [class*='barcode-']"
        )
        if upc_elem:
            upc_text = upc_elem.text().strip()
            if upc_text and len(upc_text) > 8:
                result["upc"] = upc_text

        return result if result else None

    def _extract_detail_attributes(self, parser: object) -> dict[str, str]:
        """Extract key/value metadata from HipComic detail rows."""
        details: dict[str, str] = {}

        for attr in parser.css(".r-detail-attribute"):
            label_elem = attr.css_first(".r-detail-attribute__label")
            if label_elem is None:
                continue

            label = label_elem.text().strip().lower()
            value_parts: list[str] = []
            for child in attr.iter():
                text = child.text().strip()
                if not text or text.lower() == label:
                    continue
                if text not in value_parts:
                    value_parts.append(text)

            if value_parts:
                details[label] = " ".join(value_parts)

        return details

    def _parse_hip_title(self, title: str) -> tuple[str, int | None]:
        """Extract series title and start year from HIP title.

        HIP format: "X-Men (1991)" or "Amazing Spider-Man (1963)" or "X-Men (1991-2001)"

        Args:
            title: HIP page title string

        Returns:
            Tuple of (series_title, start_year)
        """
        match = re.search(r"\((\d{4})(?:-\d{4})?\)", title)
        if match:
            year = int(match.group(1))
            title_only = title[: match.start()].strip()
            return title_only, year
        return title, None

    def _clean_issue_number(self, issue_str: str) -> str:
        """Clean and normalize issue number from HIP.

        HIP may encode negative numbers specially (e.g., "1-1" for "-1").

        Args:
            issue_str: Raw issue number string from HIP

        Returns:
            Cleaned issue number string
        """
        cleaned = issue_str.strip()

        if cleaned == "1-1":
            return "-1"

        match = re.match(r"#?\s*(.+)", cleaned)
        if match:
            return match.group(1).strip()

        return cleaned

    def _extract_variant_suffix(self, variant_text: str) -> str | None:
        """Extract variant suffix from variant text.

        Args:
            variant_text: Variant description text

        Returns:
            Variant suffix code or None
        """
        if not variant_text:
            return None

        normalized = (
            variant_text.lower().replace("-", "").replace("_", "").replace(" ", "")
        )

        single_letter_match = re.match(r"^([a-z])$", normalized)
        if single_letter_match:
            return single_letter_match.group(1).upper()

        return normalized.upper() if normalized else None

    def _parse_date(self, date_str: str) -> date | None:
        """Parse date from HIP date string.

        Args:
            date_str: HIP date string

        Returns:
            Date object or None
        """
        if not date_str:
            return None

        iso_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", date_str)
        if iso_match:
            try:
                return date(
                    int(iso_match.group(1)),
                    int(iso_match.group(2)),
                    int(iso_match.group(3)),
                )
            except ValueError:
                pass

        month_match = re.search(
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})",
            date_str,
            re.IGNORECASE,
        )
        if month_match:
            try:
                month_str = month_match.group(1)
                year = int(month_match.group(2))
                month_map = {
                    "jan": 1,
                    "feb": 2,
                    "mar": 3,
                    "apr": 4,
                    "may": 5,
                    "jun": 6,
                    "jul": 7,
                    "aug": 8,
                    "sep": 9,
                    "oct": 10,
                    "nov": 11,
                    "dec": 12,
                }
                month = month_map.get(month_str[:3].lower())
                if month:
                    return date(year, month, 1)
            except (ValueError, KeyError):
                pass

        year_match = re.search(r"\b(19|20)\d{2}\b", date_str)
        if year_match:
            try:
                year = int(year_match.group(0))
                return date(year, 1, 1)
            except ValueError:
                pass

        return None

    def _parse_price(self, price_str: str | None) -> float | None:
        """Parse price from HIP price string.

        Args:
            price_str: HIP price string

        Returns:
            Price as float or None
        """
        if not price_str:
            return None

        match = re.search(r"\$?([\d,]+\.?\d*)", price_str)
        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except ValueError:
                pass
        return None

    def _parse_page_count(self, page_str: str) -> int | None:
        """Parse page count from HIP page count string.

        Args:
            page_str: HIP page count string

        Returns:
            Page count as int or None
        """
        if not page_str:
            return None

        match = re.search(r"(\d+)", page_str)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
        return None
