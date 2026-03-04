"""Comic Collector Live (CCL) adapter implementation.

This adapter fetches data from ComicCollectorLive and maps it to internal
candidate models. CCL is a marketplace and collection tracking platform.

CCL URL format:
- comiccollectorlive.com/Libraries/Issue/{issue_id}
- comiccollectorlive.com/Libraries/Series/{series_id}
"""

import re
from datetime import date
from typing import Any, Optional

import httpx
from selectolax.lexbor import LexborHTMLParser

from comic_identity_engine.adapters import (
    NotFoundError,
    SourceAdapter,
    SourceError,
    ValidationError,
)
from comic_identity_engine.models import IssueCandidate, SeriesCandidate
from comic_identity_engine.parsing import parse_issue_candidate


class CCLAdapter(SourceAdapter):
    """Adapter for Comic Collector Live (comiccollectorlive.com).

    This adapter fetches data from CCL and maps it to internal candidate models.
    It supports both direct fetching from CCL URLs and parsing pre-fetched HTML.
    """

    SOURCE = "ccl"
    BASE_URL = "https://www.comiccollectorlive.com"

    def __init__(self, timeout: float = 30.0) -> None:
        """Initialize CCL adapter.

        Args:
            timeout: HTTP request timeout in seconds
        """
        self.timeout = timeout
        # SSL verification disabled due to certificate issues on CCL
        self.client = httpx.Client(timeout=timeout, verify=False, follow_redirects=True)

    def fetch_series(self, source_series_id: str) -> SeriesCandidate:
        """Fetch series from CCL.

        Args:
            source_series_id: CCL series ID (e.g., "787")

        Returns:
            SeriesCandidate with validated metadata

        Raises:
            NotFoundError: Series not found on CCL
            ValidationError: Required fields missing
            SourceError: Network or scraping error
        """
        url = f"{self.BASE_URL}/Libraries/Series/{source_series_id}"

        try:
            # First visit main page to get ASP.NET session cookies
            self.client.get(self.BASE_URL)

            # Now fetch the series page
            response = self.client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise NotFoundError(f"Series not found: {source_series_id}") from e
            raise SourceError(f"HTTP error fetching series: {e}") from e
        except httpx.RequestError as e:
            raise SourceError(f"Network error fetching series: {e}") from e

        return self.fetch_series_from_payload(source_series_id, {"html": response.text})

    def fetch_issue(self, source_issue_id: str) -> IssueCandidate:
        """Fetch issue from CCL.

        Args:
            source_issue_id: CCL issue ID (e.g., "28636")

        Returns:
            IssueCandidate with validated metadata

        Raises:
            NotFoundError: Issue not found on CCL
            ValidationError: Required fields missing or issue number invalid
            SourceError: Network or scraping error
        """
        url = f"{self.BASE_URL}/Libraries/Issue/{source_issue_id}"

        try:
            # First visit main page to get ASP.NET session cookies
            self.client.get(self.BASE_URL)

            # Now fetch the issue page
            response = self.client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise NotFoundError(f"Issue not found: {source_issue_id}") from e
            raise SourceError(f"HTTP error fetching issue: {e}") from e
        except httpx.RequestError as e:
            raise SourceError(f"Network error fetching issue: {e}") from e

        return self.fetch_issue_from_payload(source_issue_id, {"html": response.text})

    def fetch_series_from_payload(
        self, source_series_id: str, payload: dict[str, Any]
    ) -> SeriesCandidate:
        """Parse series from pre-fetched CCL payload.

        Args:
            source_series_id: CCL series UUID (e.g., "84ac79ed-2a10-4a38-9b4c-6df3e0db37de")
            payload: Raw CCL series data as dict with 'html' field

        Returns:
            SeriesCandidate with validated metadata

        Raises:
            ValidationError: Required fields missing
        """
        if not payload:
            raise ValidationError("CCL series payload is empty")

        html = payload.get("html") or payload.get("content")
        if not html:
            raise ValidationError(
                "CCL series payload missing required field: html/content"
            )

        parser = LexborHTMLParser(html)

        title = self._extract_series_title(parser)
        if not title:
            raise ValidationError("CCL series missing required field: title")

        publisher = self._extract_publisher(parser)
        year_began = self._extract_series_year(parser)

        return SeriesCandidate(
            source=self.SOURCE,
            source_series_id=source_series_id,
            series_title=title,
            series_start_year=year_began,
            publisher=publisher,
            raw_payload=payload,
        )

    def fetch_issue_from_payload(
        self, source_issue_id: str, payload: dict[str, Any]
    ) -> IssueCandidate:
        """Parse issue from pre-fetched CCL HTML payload.

        Args:
            source_issue_id: CCL issue UUID
            payload: Raw CCL issue data as dict with 'html' field

        Returns:
            IssueCandidate with validated metadata

        Raises:
            ValidationError: Required fields missing or issue number invalid
        """
        if not payload:
            raise ValidationError("CCL issue payload is empty")

        html = payload.get("html") or payload.get("content")
        if not html:
            raise ValidationError(
                "CCL issue payload missing required field: html/content"
            )

        parser = LexborHTMLParser(html)

        page_title = self._extract_page_title(parser)
        if not page_title:
            raise ValidationError("CCL issue missing required field: page title")

        series_title, series_title_full, issue_number_raw = self._parse_page_title(
            page_title
        )
        if not series_title:
            raise ValidationError("CCL issue missing required field: series title")

        if not issue_number_raw:
            raise ValidationError("CCL issue missing required field: issue number")

        parse_result = parse_issue_candidate(issue_number_raw)
        if not parse_result.success:
            raise ValidationError(
                f"Invalid issue number '{issue_number_raw}': {parse_result.error_code}"
            )

        if parse_result.canonical_issue_number is None:
            raise ValidationError(
                f"Issue number '{issue_number_raw}' parsed successfully but produced no canonical form"
            )

        start_year = self._extract_start_year_from_title(series_title_full)
        publisher = self._extract_publisher(parser)

        variant_suffix = self._extract_variant_from_parser(parser)
        price = self._extract_price(parser)
        cover_date = self._extract_publish_date(parser)
        publication_date = self._extract_sale_date(parser)

        return IssueCandidate(
            source=self.SOURCE,
            source_series_id=self._extract_series_id_from_parser(parser),
            source_issue_id=source_issue_id,
            series_title=series_title,
            series_start_year=start_year,
            publisher=publisher,
            issue_number=parse_result.canonical_issue_number,
            variant_suffix=variant_suffix,
            cover_date=cover_date,
            publication_date=publication_date,
            price=price,
            raw_payload=payload,
        )

    def _extract_page_title(self, parser: LexborHTMLParser) -> Optional[str]:
        """Extract page title (h1) from CCL HTML.

        Args:
            parser: LexborHTMLParser instance

        Returns:
            Page title string or None
        """
        h1 = parser.css_first("h1")
        if h1:
            return h1.text(strip=True)
        return None

    def _parse_page_title(
        self, page_title: str
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Parse series title and issue number from CCL page title.

        CCL format: "X-Men (1991) issue -1-C DF Carlos Pacheco Cover (Signed by Lobdell) 1/500"

        Args:
            page_title: CCL page title string

        Returns:
            Tuple of (series_title, series_title_full, issue_number_raw)
        """
        match = re.match(
            r"^(.+?)\s+issue\s+(.+?)\s+(?:By\s+\w+)?", page_title, re.IGNORECASE
        )
        if match:
            series_part = match.group(1).strip()
            issue_part = match.group(2).strip()

            series_title = self._extract_series_title_from_part(series_part)
            issue_number = self._extract_issue_number_from_part(issue_part)

            return series_title, series_part, issue_number

        return None, None, None

    def _extract_series_title_from_part(self, series_part: str) -> Optional[str]:
        """Extract series title from series part of title.

        Args:
            series_part: Series part from title (e.g., "X-Men (1991)")

        Returns:
            Series title or None
        """
        match = re.match(r"^(.+?)\s*\((\d{4})\)", series_part)
        if match:
            return match.group(1).strip()
        return series_part.strip() if series_part else None

    def _extract_issue_number_from_part(self, issue_part: str) -> Optional[str]:
        """Extract issue number from issue part of title.

        Args:
            issue_part: Issue part from title (e.g., "-1-C DF Carlos Pacheco Cover")

        Returns:
            Raw issue number string or None

        Note:
            Returns None if the pattern looks like a multi-issue range (e.g., "1-3")
        """
        match = re.match(r"^(-?\d+(?:\.\d+)?(?:/\d+)?)(?=-\d)", issue_part)
        if match:
            return None

        match = re.match(r"^(-?\d+(?:\.\d+)?(?:/\d+)?)", issue_part)
        if match:
            return match.group(1)
        return None

    def _extract_start_year_from_title(
        self, series_title: Optional[str]
    ) -> Optional[int]:
        """Extract start year from series title.

        Args:
            series_title: Series title string (e.g., "X-Men (1991)")

        Returns:
            Start year as int or None
        """
        if not series_title:
            return None
        match = re.search(r"\((\d{4})\)", series_title)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
        return None

    def _extract_series_title(self, parser: LexborHTMLParser) -> Optional[str]:
        """Extract series title from CCL series HTML.

        Args:
            parser: LexborHTMLParser instance

        Returns:
            Series title or None
        """
        title_elem = parser.css_first("h1")
        if title_elem:
            title_text = title_elem.text(strip=True)
            match = re.match(r"^(.+?)\s*\(", title_text)
            if match:
                return match.group(1).strip()
            return title_text
        return None

    def _extract_publisher(self, parser: LexborHTMLParser) -> Optional[str]:
        """Extract publisher from CCL HTML.

        Args:
            parser: LexborHTMLParser instance

        Returns:
            Publisher name or None
        """
        publisher_link = parser.css_first("a[href*='/LiveData/Publisher.aspx']")
        if publisher_link:
            return publisher_link.text(strip=True)
        return None

    def _extract_series_year(self, parser: LexborHTMLParser) -> Optional[int]:
        """Extract series start year from CCL series HTML.

        Args:
            parser: LexborHTMLParser instance

        Returns:
            Start year as int or None
        """
        title_elem = parser.css_first("h1")
        if title_elem:
            title_text = title_elem.text(strip=True)
            return self._extract_start_year_from_title(title_text)
        return None

    def _extract_variant_from_parser(self, parser: LexborHTMLParser) -> Optional[str]:
        """Extract variant suffix from CCL HTML.

        Args:
            parser: LexborHTMLParser instance

        Returns:
            Variant suffix (e.g., "A", "B", "C") or None
        """
        rows = parser.css("table tr")
        for row in rows:
            cells = row.css("td")
            if len(cells) >= 2:
                label = cells[0].text(strip=True)
                value = cells[1].text(strip=True)
                if label.lower() == "variant:":
                    variant = value.strip()
                    if variant and variant.isalpha() and len(variant) == 1:
                        return variant.upper()
        return None

    def _extract_price(self, parser: LexborHTMLParser) -> Optional[float]:
        """Extract cover price from CCL HTML.

        Args:
            parser: LexborHTMLParser instance

        Returns:
            Price as float or None
        """
        rows = parser.css("table tr")
        for row in rows:
            cells = row.css("td")
            if len(cells) >= 2:
                label = cells[0].text(strip=True)
                value = cells[1].text(strip=True)
                if label.lower() == "cover price:":
                    return self._parse_price_string(value)
        return None

    def _parse_price_string(self, price_str: Optional[str]) -> Optional[float]:
        """Parse price string from CCL.

        Args:
            price_str: Price string (e.g., "$1.95", "2.50")

        Returns:
            Price as float or None
        """
        if not price_str:
            return None
        match = re.search(r"\$?([\d\.]+)", price_str)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return None

    def _extract_publish_date(self, parser: LexborHTMLParser) -> Optional[date]:
        """Extract publish date from CCL HTML.

        Args:
            parser: LexborHTMLParser instance

        Returns:
            Date object or None
        """
        return self._extract_date_by_label(parser, "publish date:")

    def _extract_sale_date(self, parser: LexborHTMLParser) -> Optional[date]:
        """Extract sale date from CCL HTML.

        Args:
            parser: LexborHTMLParser instance

        Returns:
            Date object or None
        """
        return self._extract_date_by_label(parser, "sale date:")

    def _extract_date_by_label(
        self, parser: LexborHTMLParser, label: str
    ) -> Optional[date]:
        """Extract date from CCL HTML by table row label.

        Args:
            parser: LexborHTMLParser instance
            label: Row label to search for (e.g., "publish date:")

        Returns:
            Date object or None
        """
        rows = parser.css("table tr")
        for row in rows:
            cells = row.css("td")
            if len(cells) >= 2:
                row_label = cells[0].text(strip=True).lower()
                value = cells[1].text(strip=True)
                if row_label == label.lower():
                    return self._parse_date_string(value)
        return None

    def _parse_date_string(self, date_str: Optional[str]) -> Optional[date]:
        """Parse date string from CCL format.

        CCL format: "JUL 01 1997" or "Jul 01, 1997"

        Args:
            date_str: Date string from CCL

        Returns:
            Date object or None
        """
        if not date_str:
            return None

        month_map = {
            "jan": "01",
            "feb": "02",
            "mar": "03",
            "apr": "04",
            "may": "05",
            "jun": "06",
            "jul": "07",
            "aug": "08",
            "sep": "09",
            "oct": "10",
            "nov": "11",
            "dec": "12",
        }

        match = re.match(r"(\w{3})\s+(\d{1,2})\s*,?\s*(\d{4})", date_str, re.IGNORECASE)
        if match:
            month_str = match.group(1).lower()[:3]
            day = match.group(2).zfill(2)
            year = match.group(3)

            if month_str in month_map:
                month = month_map[month_str]
                try:
                    return date.fromisoformat(f"{year}-{month}-{day}")
                except ValueError:
                    pass
        return None

    def _extract_series_id_from_parser(self, parser: LexborHTMLParser) -> str:
        """Extract series UUID from CCL HTML.

        Args:
            parser: LexborHTMLParser instance

        Returns:
            Series UUID string or empty string
        """
        issues_link = parser.css_first("a[href*='/issues/comic-books/']")
        if issues_link:
            href = issues_link.attributes.get("href", "")
            if href:
                match = re.search(
                    r"/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})",
                    href,
                )
                if match:
                    return match.group(1)
        return ""
