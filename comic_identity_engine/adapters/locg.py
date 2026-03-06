"""League of Comic Geeks (LoCG) adapter implementation.

This adapter ingests data from the League of Comic Geeks platform
and maps it to internal candidate models.

LoCG is a community-driven comic database with good coverage of
modern comics and variant information.

URL patterns:
- leagueofcomicgeeks.com/comic/SERIES_ID/slug-ISSUE_NUM?variant=VARIANT_ID
- leagueofcomicgeeks.com/comic/SERIES_ID/ISSUE_ID
- leagueofcomicgeeks.com/comics/series/SERIES_ID/
"""

import re
from datetime import date

import httpx

from comic_identity_engine.adapters import (
    SourceAdapter,
    SourceError,
    ValidationError,
)
from comic_identity_engine.core.http_client import HttpClient
from comic_identity_engine.models import IssueCandidate, SeriesCandidate
from comic_identity_engine.parsing import parse_issue_candidate


class LoCGAdapter(SourceAdapter):
    """Adapter for League of Comic Geeks (leagueofcomicgeeks.com).

    This adapter fetches data from the LoCG website and maps it to
    internal candidate models.
    """

    SOURCE = "locg"
    BASE_URL = "https://leagueofcomicgeeks.com"

    def __init__(
        self,
        http_client: HttpClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize LoCG adapter.

        Args:
            http_client: Optional HTTP client for making requests
            timeout: HTTP request timeout in seconds (used if http_client not provided)
        """
        super().__init__(http_client)
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

    async def fetch_series(self, source_series_id: str) -> SeriesCandidate:
        """Fetch series from LoCG.

        Args:
            source_series_id: LoCG series ID (e.g., "111275")

        Returns:
            SeriesCandidate with validated metadata

        Raises:
            NotFoundError: Series not found on LoCG
            ValidationError: Required fields missing
            SourceError: Network or API error
        """
        url = f"{self.BASE_URL}/comic/{source_series_id}"

        if self.http_client is None:
            raise SourceError("HTTP client not initialized")

        try:
            response = await self.http_client.get(url, headers=self.headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                from comic_identity_engine.adapters import NotFoundError

                raise NotFoundError(f"Series not found: {source_series_id}") from e
            raise SourceError(f"HTTP error fetching series: {e}") from e
        except httpx.RequestError as e:
            raise SourceError(f"Network error fetching series: {e}") from e

        return self._parse_series_from_html(source_series_id, response.text)

    async def fetch_issue(
        self, source_issue_id: str, full_url: str | None = None
    ) -> IssueCandidate:
        """Fetch issue from LoCG.

        Args:
            source_issue_id: LoCG issue ID or variant ID (e.g., "1169529")

        Returns:
            IssueCandidate with validated metadata

        Raises:
            NotFoundError: Issue not found on LoCG
            ValidationError: Required fields missing or issue number invalid
            SourceError: Network or API error
        """
        url = f"{self.BASE_URL}/comic/{source_issue_id}"

        if self.http_client is None:
            raise SourceError("HTTP client not initialized")

        try:
            response = await self.http_client.get(url, headers=self.headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                from comic_identity_engine.adapters import NotFoundError

                raise NotFoundError(f"Issue not found: {source_issue_id}") from e
            raise SourceError(f"HTTP error fetching issue: {e}") from e
        except httpx.RequestError as e:
            raise SourceError(f"Network error fetching issue: {e}") from e

        return self._parse_issue_from_html(source_issue_id, response.text)

    def fetch_series_from_html(
        self, source_series_id: str, html: str
    ) -> SeriesCandidate:
        """Parse series from pre-fetched LoCG HTML.

        Args:
            source_series_id: LoCG series ID
            html: Raw HTML response from LoCG

        Returns:
            SeriesCandidate with validated metadata

        Raises:
            ValidationError: Required fields missing
        """
        return self._parse_series_from_html(source_series_id, html)

    def fetch_issue_from_html(self, source_issue_id: str, html: str) -> IssueCandidate:
        """Parse issue from pre-fetched LoCG HTML.

        Args:
            source_issue_id: LoCG issue ID
            html: Raw HTML response from LoCG

        Returns:
            IssueCandidate with validated metadata

        Raises:
            ValidationError: Required fields missing or issue number invalid
        """
        return self._parse_issue_from_html(source_issue_id, html)

    def _parse_series_from_html(
        self, source_series_id: str, html: str
    ) -> SeriesCandidate:
        """Parse series metadata from LoCG HTML.

        Args:
            source_series_id: LoCG series ID
            html: Raw HTML from series page

        Returns:
            SeriesCandidate with validated metadata

        Raises:
            ValidationError: Required fields missing
        """
        if not html:
            raise ValidationError("LoCG series HTML is empty")

        series_title = self._extract_series_title_from_html(html)
        if not series_title:
            raise ValidationError("LoCG series missing required field: title")

        publisher = self._extract_publisher_from_html(html)
        start_year = self._extract_series_start_year_from_html(html)

        return SeriesCandidate(
            source=self.SOURCE,
            source_series_id=source_series_id,
            series_title=series_title,
            series_start_year=start_year,
            publisher=publisher,
            raw_payload={"html": html},
        )

    def _parse_issue_from_html(self, source_issue_id: str, html: str) -> IssueCandidate:
        """Parse issue metadata from LoCG HTML.

        Args:
            source_issue_id: LoCG issue ID
            html: Raw HTML from issue page

        Returns:
            IssueCandidate with validated metadata

        Raises:
            ValidationError: Required fields missing or issue number invalid
        """
        if not html:
            raise ValidationError("LoCG issue HTML is empty")

        series_title = self._extract_series_title_from_html(html)
        if not series_title:
            raise ValidationError("LoCG issue missing required field: series title")

        issue_number = self._extract_issue_number_from_html(html)
        if not issue_number:
            raise ValidationError("LoCG issue missing required field: issue number")

        parse_result = parse_issue_candidate(issue_number)
        if not parse_result.success:
            raise ValidationError(
                f"Invalid issue number '{issue_number}': {parse_result.error_code}"
            )

        if parse_result.canonical_issue_number is None:
            raise ValidationError(
                f"Issue number '{issue_number}' parsed successfully but produced no canonical form"
            )

        source_series_id = self._extract_series_id_from_html(html)
        publisher = self._extract_publisher_from_html(html)
        start_year = self._extract_series_start_year_from_html(html)

        variant_suffix = self._extract_variant_suffix_from_html(html)
        variant_name = self._extract_variant_name_from_html(html)

        cover_date = self._extract_cover_date_from_html(html)
        price = self._extract_price_from_html(html)
        upc = self._extract_upc_from_html(html)

        return IssueCandidate(
            source=self.SOURCE,
            source_series_id=source_series_id,
            source_issue_id=source_issue_id,
            series_title=series_title,
            series_start_year=start_year,
            publisher=publisher,
            issue_number=parse_result.canonical_issue_number,
            variant_suffix=variant_suffix,
            cover_date=cover_date,
            price=price,
            upc=upc,
            variant_name=variant_name,
            raw_payload={"html": html},
        )

    def _extract_series_title_from_html(self, html: str) -> str | None:
        """Extract series title from LoCG HTML.

        Args:
            html: Raw HTML from LoCG

        Returns:
            Series title or None
        """
        title_tag_value = None
        h1_title_value = None

        # Extract from title tag
        title_match = re.search(
            r"<title>([^<]+?)\s*\|\s*League of Comic Geeks</title>", html, re.I
        )
        if title_match:
            title_tag_value = title_match.group(1).strip()
        else:
            title_match = re.search(r"<title>([^<]+?)\s*Reviews</title>", html, re.I)
            if title_match:
                title_tag_value = title_match.group(1).strip()

        # Extract from h1 with title class
        h1_match = re.search(
            r'<h1[^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)</h1>', html, re.I
        )
        if h1_match:
            h1_title_value = h1_match.group(1).strip()

        # Choose the best title based on content
        # Prefer title tag if it contains year in parentheses or issue number
        # Prefer h1 if title tag is too generic
        if title_tag_value and h1_title_value:
            # If title tag has year (like "X-Men (1991)") or issue (like "X-Men #1"), use it
            if re.search(r"\(\d{4}\)|#\d+", title_tag_value):
                return title_tag_value
            # If h1 is more descriptive (longer), use it
            if len(h1_title_value) > len(title_tag_value):
                return h1_title_value
            # Default to title tag
            return title_tag_value

        # Return whichever we found
        if h1_title_value:
            return h1_title_value
        if title_tag_value:
            return title_tag_value

        # Try any h1 tag as fallback
        h1_any_match = re.search(r"<h1[^>]*>([^<]+)</h1>", html, re.I)
        if h1_any_match:
            title = h1_any_match.group(1).strip()
            if title:
                return title

        return None

    def _extract_issue_number_from_html(self, html: str) -> str | None:
        """Extract issue number from LoCG HTML.

        Args:
            html: Raw HTML from LoCG

        Returns:
            Issue number string or None
        """
        # Try h1 tag with "SeriesName #Issue" format
        match = re.search(r"<h1[^>]*>([^<]+?)\s+#(\d+)", html, re.I)
        if match:
            return match.group(2)

        # Try title tag with "SeriesName #Issue Reviews" format
        match = re.search(r"<title>[^<]+?\s+#(\d+)\s+Reviews", html, re.I)
        if match:
            return match.group(1)

        # Try generic title tag pattern
        match = re.search(r"<title>[^<]+?#([\d\./-]+)(?:\s*\||\s*$)", html)
        if match:
            return match.group(1)

        # Try h2 tag as fallback
        match = re.search(
            r'<h2[^>]*class="[^"]*issue[^"]*"[^>]*>([^<]+)</h2>', html, re.I
        )
        if match:
            issue_text = match.group(1).strip()
            number_match = re.search(r"#?([\d\./-]+)", issue_text)
            if number_match:
                return number_match.group(1)

        return None

    def _extract_series_id_from_html(self, html: str) -> str:
        """Extract series ID from LoCG HTML.

        Args:
            html: Raw HTML from LoCG

        Returns:
            Series ID as string
        """
        match = re.search(r"/comic/(\d+)", html)
        if match:
            return match.group(1)

        return ""

    def _extract_publisher_from_html(self, html: str) -> str | None:
        """Extract publisher from LoCG HTML.

        Args:
            html: Raw HTML from LoCG

        Returns:
            Publisher name or None
        """
        # Try publisher element with class
        patterns = [
            r'<p[^>]*class="[^"]*publisher[^"]*"[^>]*>([^<]+)</p>',
            r'<span[^>]*class="[^"]*publisher[^"]*"[^>]*>([^<]+)</span>',
            r'<div[^>]*class="[^"]*publisher[^"]*"[^>]*>([^<]+)</div>',
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.I)
            if match:
                publisher = match.group(1).strip()
                if publisher:
                    return publisher

        # Try publisher page link
        patterns = [
            r'<a[^>]*href="/publishers/[^"]*"[^>]*>([^<]+)</a>',
            r'<a[^>]*href="/comics/(?:dc|marvel|image|dark-horse|idw)[^"]*"[^>]*>([^<]+)</a>',
            r'<a[^>]*href="/comics/([a-z]+)"[^>]*>',
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.I)
            if match:
                publisher = match.group(1).strip()
                # Capitalize publisher name
                if publisher:
                    return publisher.title()

        # Look for common publisher names in text
        # Check longer names first to avoid partial matches
        publishers = [
            "DC Comics",
            "Image Comics",
            "Dark Horse Comics",
            "Marvel Comics",
            "Marvel",
            "IDW Publishing",
            "IDW",
        ]
        for publisher in publishers:
            if publisher in html:
                return publisher

        return None

    def _extract_series_start_year_from_html(self, html: str) -> int | None:
        """Extract series start year from LoCG HTML.

        Args:
            html: Raw HTML from LoCG

        Returns:
            Start year as int or None
        """
        patterns = [
            r"\((\d{4})[–-]",
            r"(\d{4})\s*Series",
            r"Published\s+(\d{4})",
        ]

        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                try:
                    return int(match.group(1))
                except (ValueError, IndexError):  # pragma: no cover
                    continue

        return None

    def _extract_variant_suffix_from_html(self, html: str) -> str | None:
        """Extract variant suffix from LoCG HTML.

        Args:
            html: Raw HTML from LoCG

        Returns:
            Variant suffix code or None
        """
        patterns = [
            r"variant[^:]*:\s*([A-Z]{1,2})(?:\s|<|$)",
            r"cover\s+([A-Z])(?:\s|<)",
            r"edition\s*:\s*([A-Z])",
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.I)
            if match:
                suffix = match.group(1).strip().upper()
                if suffix:
                    return suffix

        return None

    def _extract_variant_name_from_html(self, html: str) -> str | None:
        """Extract variant name from LoCG HTML.

        Args:
            html: Raw HTML from LoCG

        Returns:
            Variant description or None
        """
        patterns = [
            r'<span[^>]*class="[^"]*variant[^"]*"[^>]*>([^<]+)</span>',
            r"variant[^:]*:\s*([^<\n]+?)(?:<|\\\n)",
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.I)
            if match:
                variant_name = match.group(1).strip()
                if variant_name and variant_name not in ["Standard", "None"]:
                    return variant_name

        return None

    def _extract_cover_date_from_html(self, html: str) -> date | None:
        """Extract cover date from LoCG HTML.

        Args:
            html: Raw HTML from LoCG

        Returns:
            Cover date or None
        """
        patterns = [
            r"(\d{4})-(\d{1,2})-(\d{1,2})",
            r"(\w+)\s+(\d{1,2}),?\s+(\d{4})",
        ]

        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                try:
                    if "-" in match.group(0):
                        year = int(match.group(1))
                        month = int(match.group(2))
                        day = int(match.group(3))
                        return date(year, month, day)
                    else:
                        month_str = match.group(1)
                        day = int(match.group(2))
                        year = int(match.group(3))

                        months = {
                            "January": 1,
                            "February": 2,
                            "March": 3,
                            "April": 4,
                            "May": 5,
                            "June": 6,
                            "July": 7,
                            "August": 8,
                            "September": 9,
                            "October": 10,
                            "November": 11,
                            "December": 12,
                            "Jan": 1,
                            "Feb": 2,
                            "Mar": 3,
                            "Apr": 4,
                            "May": 5,
                            "Jun": 6,
                            "Jul": 7,
                            "Aug": 8,
                            "Sep": 9,
                            "Oct": 10,
                            "Nov": 11,
                            "Dec": 12,
                        }

                        month = months.get(month_str)
                        if month and 1 <= day <= 31:
                            return date(year, month, day)
                except (ValueError, IndexError):  # pragma: no cover
                    continue

        return None

    def _extract_price_from_html(self, html: str) -> float | None:
        """Extract price from LoCG HTML.

        Args:
            html: Raw HTML from LoCG

        Returns:
            Price as float or None
        """
        patterns = [
            r"\$(\d+\.\d{2})",
            r"price[^:]*:\s*\$(\d+\.\d{2})",
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.I)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:  # pragma: no cover
                    continue

        return None

    def _extract_upc_from_html(self, html: str) -> str | None:
        """Extract UPC from LoCG HTML.

        Args:
            html: Raw HTML from LoCG

        Returns:
            UPC string or None
        """
        patterns = [
            r'<span[^>]*class="[^"]*upc[^"]*"[^>]*>(\d{12,})</span>',
            r"barcode[^:]*:\s*(\d{12,})",
            r"UPC[^<]*</[^>]+>\s*(\d{12,})",
            r"UPC[^:]*:\s*(\d{12,})",
            r"isbn[^:]*:\s*([\d-]{12,})",  # ISBN format with dashes
            r">(\d{12,})<",  # Generic 12+ digit number
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.I)
            if match:
                upc = match.group(1).strip()
                if upc and len(upc.replace("-", "")) >= 12:
                    return upc

        return None
