"""Atomic Avenue (AA) adapter implementation.

This adapter ingests data from Atomic Avenue HTML pages and maps it to
internal candidate models. Atomic Avenue is a comic marketplace that
displays series and issue information in HTML format.

AA URL patterns:
- atomicavenue.com/atomic/item/ITEM_ID/1/slug (issue page)
- atomicavenue.com/atomic/series/SERIES_ID (series page)
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from selectolax.lexbor import LexborHTMLParser
from urllib.parse import quote

from comic_identity_engine.adapters import (
    NotFoundError,
    SourceAdapter,
    SourceError,
    ValidationError,
)
from comic_identity_engine.core.http_client import HttpClient
from comic_identity_engine.models import IssueCandidate, SeriesCandidate
from comic_identity_engine.parsing import parse_issue_candidate

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Simple search result for cross-platform matching."""

    url: str
    has_results: bool
    source_issue_id: Optional[str] = None


class AAAdapter(SourceAdapter):
    """Adapter for Atomic Avenue (atomicavenue.com).

    This adapter fetches data from Atomic Avenue HTML pages and maps
    it to internal candidate models.
    """

    SOURCE = "aa"
    BASE_URL = "https://atomicavenue.com"

    def __init__(
        self,
        http_client: HttpClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize AA adapter.

        Args:
            http_client: Optional HTTP client for making requests
            timeout: HTTP request timeout in seconds (used if http_client not provided)
        """
        super().__init__(http_client)
        self.timeout = timeout

    async def fetch_series(self, source_series_id: str) -> SeriesCandidate:
        """Fetch series from Atomic Avenue.

        Args:
            source_series_id: AA series ID (e.g., "20384")

        Returns:
            SeriesCandidate with validated metadata

        Raises:
            NotFoundError: Series not found (404)
            SourceError: Network or HTTP error
            ValidationError: Required fields missing
        """
        url = f"{self.BASE_URL}/atomic/series/{source_series_id}"

        if self.http_client is None:
            raise SourceError("HTTP client not initialized")

        try:
            response = await self.http_client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise NotFoundError(f"Series not found: {source_series_id}") from e
            raise SourceError(f"HTTP error fetching series: {e}") from e
        except httpx.RequestError as e:
            raise SourceError(f"Network error fetching series: {e}") from e

        return self.fetch_series_from_html(source_series_id, response.text)

    async def fetch_issue(
        self, source_issue_id: str, full_url: Optional[str] = None
    ) -> IssueCandidate:
        """Fetch issue from Atomic Avenue.

        Args:
            source_issue_id: AA item ID (e.g., "209583")
            full_url: Optional full URL with slug (required for AA issues)

        Returns:
            IssueCandidate with validated metadata

        Raises:
            NotFoundError: Issue not found (404)
            SourceError: Network or HTTP error
            ValidationError: Required fields missing or issue number invalid
        """
        if full_url:
            url = full_url
        else:
            url = f"{self.BASE_URL}/atomic/item/{source_issue_id}/1"

        if self.http_client is None:
            raise SourceError("HTTP client not initialized")

        try:
            response = await self.http_client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise NotFoundError(f"Issue not found: {source_issue_id}") from e
            raise SourceError(f"HTTP error fetching issue: {e}") from e
        except httpx.RequestError as e:
            raise SourceError(f"Network error fetching issue: {e}") from e

        return self.fetch_issue_from_html(source_issue_id, response.text)

    def fetch_series_from_html(
        self, source_series_id: str, html: Optional[str]
    ) -> SeriesCandidate:
        """Parse series from pre-fetched AA HTML payload.

        Args:
            source_series_id: AA series ID (e.g., "20384")
            html: Raw AA HTML page as string

        Returns:
            SeriesCandidate with validated metadata

        Raises:
            ValidationError: Required fields missing
        """
        if not html:
            raise ValidationError("AA series HTML is empty")

        parser = LexborHTMLParser(html)

        series_title = self._extract_series_title(parser)
        if not series_title:
            raise ValidationError("AA series missing required field: series_title")

        publisher, start_year, end_year = self._extract_series_metadata(parser)

        return SeriesCandidate(
            source=self.SOURCE,
            source_series_id=source_series_id,
            series_title=series_title,
            series_start_year=start_year,
            publisher=publisher,
            series_end_year=end_year,
            raw_payload={"html": html},
        )

    def fetch_issue_from_html(
        self, source_issue_id: str, html: Optional[str]
    ) -> IssueCandidate:
        """Parse issue from pre-fetched AA HTML payload.

        Args:
            source_issue_id: AA item ID (e.g., "209583")
            html: Raw AA HTML page as string

        Returns:
            IssueCandidate with validated metadata

        Raises:
            ValidationError: Required fields missing or issue number invalid
        """
        if not html:
            raise ValidationError("AA issue HTML is empty")

        parser = LexborHTMLParser(html)

        series_title = self._extract_series_title(parser)
        if not series_title:
            raise ValidationError("AA issue missing required field: series_title")

        issue_number = self._extract_issue_number(parser)
        if not issue_number:
            raise ValidationError("AA issue missing required field: issue_number")

        parse_result = parse_issue_candidate(issue_number)
        if not parse_result.success:
            raise ValidationError(
                f"Invalid issue number '{issue_number}': {parse_result.error_code}"
            )

        if parse_result.canonical_issue_number is None:
            raise ValidationError(
                f"Issue number '{issue_number}' parsed successfully but produced no canonical form"
            )

        publisher, start_year, _ = self._extract_series_metadata(parser)

        return IssueCandidate(
            source=self.SOURCE,
            source_series_id=self._extract_series_id_from_html(parser),
            source_issue_id=source_issue_id,
            series_title=series_title,
            series_start_year=start_year,
            publisher=publisher,
            issue_number=parse_result.canonical_issue_number,
            variant_suffix=parse_result.variant_suffix,
            raw_payload={"html": html},
        )

    def _extract_series_title(self, parser: LexborHTMLParser) -> Optional[str]:
        """Extract series title from AA HTML.

        Args:
            parser: Selectolax HTML parser

        Returns:
            Series title or None
        """
        # Try multiple selectors for different AA page formats
        title_elem = parser.css_first("#ctl00_ContentPlaceHolder1_lblIssueName a")
        if not title_elem:
            title_elem = parser.css_first("h2.dropLeftMargin a")
        if not title_elem:
            title_elem = parser.css_first("h2.dropLeftMargin")
        if title_elem:
            title_text = title_elem.text().strip()
            # Remove issue number if present (e.g., "Leave it to Chance #1" -> "Leave it to Chance")
            issue_match = re.search(r"\s*#\d+", title_text)
            if issue_match:
                title_text = title_text[: issue_match.start()].strip()
            return self._normalize_series_title(title_text)
        return None

    def _normalize_series_title(self, title_text: str) -> str:
        """Normalize Atomic Avenue series titles with common duplication glitches."""
        cleaned = re.sub(r"\s+", " ", title_text).strip()
        words = cleaned.split()
        if len(words) % 2 == 0:
            midpoint = len(words) // 2
            if words[:midpoint] == words[midpoint:]:
                return " ".join(words[:midpoint])
        return cleaned

    def _extract_series_metadata(
        self, parser: LexborHTMLParser
    ) -> tuple[Optional[str], Optional[int], Optional[int]]:
        """Extract publisher and years from AA HTML.

        Args:
            parser: Selectolax HTML parser

        Returns:
            Tuple of (publisher, start_year, end_year)
        """
        publisher = None
        start_year = None
        end_year = None

        # Find all div elements with dropLeftMargin class (skip h2)
        metadata_divs = parser.css("div.dropLeftMargin")
        for metadata_div in metadata_divs:
            text = metadata_div.text()

            # Try to match publisher name (including Unicode characters)
            # Pattern: Capital letter followed by letters/spaces, then comma
            publisher_match = re.search(
                r"([A-Z\u00C0-\u017F][A-Za-z\u00C0-\u017F\s]+),\s*\d{4}", text
            )
            if publisher_match:
                publisher = publisher_match.group(1).strip()
            else:
                publisher_match = re.search(
                    r"^([A-Z\u00C0-\u017F][A-Za-z\u00C0-\u017F\s]+),", text
                )
                if publisher_match:
                    publisher = publisher_match.group(1).strip()

            year_match = re.search(r"(\d{4})(?:-(\d{4}))?", text)
            if year_match:
                start_year = int(year_match.group(1))
                if year_match.group(2):
                    end_year = int(year_match.group(2))

        return publisher, start_year, end_year

    def _extract_issue_number(self, parser: LexborHTMLParser) -> Optional[str]:
        """Extract issue number from AA HTML.

        Args:
            parser: Selectolax HTML parser

        Returns:
            Issue number or None
        """
        # Try multiple selectors for different AA page formats
        issue_elem = parser.css_first("#ctl00_ContentPlaceHolder1_lblIssueName")
        if not issue_elem:
            issue_elem = parser.css_first(".issueSearchIssueNum")

        if issue_elem:
            text = issue_elem.text().strip()
            # Extract issue number from format like "Leave it to Chance #1"
            issue_match = re.search(r"#(\S+)", text)
            if issue_match:
                return issue_match.group(1)
            # First check if it looks like a range (should not extract ranges)
            if re.search(r"\d+\s*-\s*\d+", text):
                return None
            # Extract issue number (including negative, decimal, and variant letter)
            # Pattern matches: -1, 0.5, 37, 37A, 37.B, 37DE, etc.
            issue_match = re.search(r"(-?\d+(?:\.\d+)?(?:\.?[A-Za-z]+)?)", text)
            if issue_match:
                return issue_match.group(1)
        return None

    def _extract_series_id_from_html(self, parser: LexborHTMLParser) -> str:
        """Extract series ID from AA HTML.

        Args:
            parser: Selectolax HTML parser

        Returns:
            Series ID as string
        """
        series_link = parser.css_first("h2.dropLeftMargin a")
        if series_link:
            href = series_link.attributes.get("href") or ""
            match = re.search(r"/series/(\d+)", href)
            if match:
                return match.group(1)
        return ""
