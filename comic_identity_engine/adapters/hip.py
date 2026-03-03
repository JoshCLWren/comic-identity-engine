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

from comic_identity_engine.adapters import (
    SourceAdapter,
    ValidationError,
)
from comic_identity_engine.models import IssueCandidate, SeriesCandidate
from comic_identity_engine.parsing import parse_issue_candidate


class HIPAdapter(SourceAdapter):
    """Adapter for HipComic.com price guide.

    This adapter works with pre-fetched HTML payloads from HipComic.com.
    It does not make any network calls - it accepts raw HTML content.
    """

    SOURCE = "hip"

    def __init__(self) -> None:
        """Initialize HIP adapter."""
        pass

    def fetch_series(self, source_series_id: str) -> SeriesCandidate:
        """Fetch series from HIP price guide.

        Args:
            source_series_id: HIP series slug (e.g., "x-men-1991")

        Returns:
            SeriesCandidate with validated metadata

        Raises:
            NotFoundError: Series not found in payload cache
            ValidationError: Required fields missing
        """
        raise NotImplementedError(
            "Use fetch_series_from_payload() instead - this adapter "
            "does not fetch data from remote sources"
        )

    def fetch_issue(self, source_issue_id: str) -> IssueCandidate:
        """Fetch issue from HIP price guide.

        Args:
            source_issue_id: HIP issue ID (encoded issue number, e.g., "1-1")

        Returns:
            IssueCandidate with validated metadata

        Raises:
            NotFoundError: Issue not found in payload cache
            ValidationError: Required fields missing or issue number invalid
        """
        raise NotImplementedError(
            "Use fetch_issue_from_payload() instead - this adapter "
            "does not fetch data from remote sources"
        )

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
        if title_elem:
            title_text = title_elem.text().strip()
            series_title, start_year = self._parse_hip_title(title_text)
            if series_title:
                result["series_title"] = series_title
            if start_year is not None:
                result["start_year"] = start_year

        issue_number_elem = parser.css_first(".issue-number, [class*='issue-number']")
        if issue_number_elem:
            issue_text = issue_number_elem.text().strip()
            result["issue_number"] = self._clean_issue_number(issue_text)
        else:
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
