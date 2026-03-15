"""Comics Price Guide (CPG) adapter implementation.

This adapter fetches data from CPG and maps it to internal
candidate models. CPG provides comic pricing and marketplace data
with coverage of both older and modern comics.

CPG URL format:
- comicspriceguide.com/titles/SERIES_SLUG/ISSUE_NUM/ISSUE_ID
- comicspriceguide.com/titles/SERIES_SLUG/ISSUE_NUM-VARIANT/ISSUE_ID

NOTE: CPG has Cloudflare protection which may block automated requests.
This adapter may require browser emulation or specialized headers.
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
from comic_identity_engine.core.http_client import HttpClient
from longbox_commons import parse_issue_candidate
from longbox_commons.models import IssueCandidate, SeriesCandidate


class CPGAdapter(SourceAdapter):
    """Adapter for Comics Price Guide (comicspriceguide.com).

    This adapter fetches data from CPG API and maps it to internal
    candidate models.
    """

    SOURCE = "cpg"
    BASE_URL = "https://www.comicspriceguide.com"

    def __init__(
        self,
        http_client: HttpClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize CPG adapter.

        Args:
            http_client: Optional HTTP client for making requests
            timeout: HTTP request timeout in seconds (used if http_client not provided)
        """
        super().__init__(http_client)
        self.timeout = timeout

    async def fetch_series(self, source_series_id: str) -> SeriesCandidate:
        """Fetch series from CPG.

        Args:
            source_series_id: CPG series slug (e.g., "x-men")

        Returns:
            SeriesCandidate with validated metadata

        Raises:
            NotFoundError: Series not found on CPG
            ValidationError: Required fields missing
            SourceError: Network or API error
        """
        url = f"{self.BASE_URL}/api/series/{source_series_id}"

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

        return self.fetch_series_from_payload(source_series_id, response.json())

    async def fetch_issue(
        self, source_issue_id: str, full_url: str | None = None
    ) -> IssueCandidate:
        """Fetch issue from CPG.

        Args:
            source_issue_id: CPG resource ID

        Returns:
            IssueCandidate with validated metadata

        Raises:
            NotFoundError: Issue not found on CPG
            ValidationError: Required fields missing or issue number invalid
            SourceError: Network or API error
        """
        url = f"{self.BASE_URL}/api/item/{source_issue_id}"

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

        return self.fetch_issue_from_payload(source_issue_id, response.json())

    def fetch_series_from_payload(
        self, source_series_id: str, payload: dict[str, Any]
    ) -> SeriesCandidate:
        """Parse series from pre-fetched CPG payload.

        Args:
            source_series_id: CPG series slug (e.g., "x-men")
            payload: Raw CPG series data as dict

        Returns:
            SeriesCandidate with validated metadata

        Raises:
            ValidationError: Required fields missing
        """
        if not payload:
            raise ValidationError("CPG series payload is empty")

        title = self._extract_title_from_payload(payload)
        if not title:
            raise ValidationError("CPG series missing required field: title/name")

        publisher = payload.get("publisher")

        year_began = self._extract_year_from_payload(payload)

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
        """Parse issue from pre-fetched CPG payload.

        Args:
            source_issue_id: CPG resource ID
            payload: Raw CPG issue data as dict

        Returns:
            IssueCandidate with validated metadata

        Raises:
            ValidationError: Required fields missing or issue number invalid
        """
        if not payload:
            raise ValidationError("CPG issue payload is empty")

        number = payload.get("number")
        if not number:
            raise ValidationError("CPG issue missing required field: number")

        parse_result = parse_issue_candidate(str(number))
        if not parse_result.success:
            raise ValidationError(
                f"Invalid issue number '{number}': {parse_result.error_code}"
            )

        if parse_result.canonical_issue_number is None:
            raise ValidationError(
                f"Issue number '{number}' parsed successfully but produced no canonical form"
            )

        title = self._extract_title_from_payload(payload)
        if not title:
            raise ValidationError("CPG issue missing required field: title")

        publisher = payload.get("publisher")

        series_slug = payload.get("name") or payload.get("nameSEO", "")
        variant_suffix = parse_result.variant_suffix or self._extract_variant_from_url(
            payload
        )

        cover_date = self._parse_date(payload.get("publicationDate"))
        publication_date = self._parse_date(payload.get("releaseDate"))

        price = self._parse_price(payload.get("price"))

        upc = payload.get("upc") or payload.get("barcode") or None

        return IssueCandidate(
            source=self.SOURCE,
            source_series_id=series_slug,
            source_issue_id=source_issue_id,
            series_title=title,
            series_start_year=self._extract_year_from_payload(payload),
            publisher=publisher,
            issue_number=parse_result.canonical_issue_number,
            variant_suffix=variant_suffix,
            cover_date=cover_date,
            publication_date=publication_date,
            price=price,
            upc=upc,
            raw_payload=payload,
        )

    def _extract_title_from_payload(self, payload: dict[str, Any]) -> str | None:
        """Extract title from CPG payload.

        CPG may provide title in different fields:
        - title.name (when title is an object)
        - title (when title is a string)
        - nameSEO (slug form)

        Args:
            payload: CPG payload

        Returns:
            Title string or None
        """
        title_field = payload.get("title", "")

        if isinstance(title_field, dict):
            title = title_field.get("name") or title_field.get("nameSEO")
            if title:
                return title

        if isinstance(title_field, str) and title_field:
            return title_field

        return payload.get("nameSEO") or payload.get("name")

    def _extract_year_from_payload(self, payload: dict[str, Any]) -> int | None:
        """Extract year from CPG payload.

        Args:
            payload: CPG payload

        Returns:
            Year as int or None
        """
        year_field = payload.get("year") or payload.get("publicationYear")

        if year_field:
            try:
                return int(year_field)
            except (ValueError, TypeError):
                pass

        return None

    def _extract_variant_from_url(self, payload: dict[str, Any]) -> str | None:
        """Extract variant suffix from CPG URL/path information.

        CPG URLs may contain variant info in the path:
        - /titles/SERIES/ISSUE-VARIANT/ID

        Args:
            payload: CPG payload

        Returns:
            Variant suffix or None
        """
        path_issue = payload.get("path_issue") or payload.get("number")

        if not path_issue:
            return None

        path_issue_str = str(path_issue)

        if "-" not in path_issue_str or path_issue_str == "-1":
            return None

        parts = path_issue_str.rsplit("-", 1)
        if len(parts) == 2:
            suffix = parts[1]
            if suffix.isalpha():
                return suffix.upper()

        return None

    def _parse_date(self, date_str: Any) -> date | None:
        """Parse date from CPG payload.

        CPG dates may be in various formats:
        - "2023-01-15" (ISO format)
        - "2023/01/15" (with slashes)
        - "2023.01.15" (with dots)
        - "January 2023"
        - "2023"

        Args:
            date_str: Date string from CPG

        Returns:
            Date object or None
        """
        if not date_str:
            return None

        if isinstance(date_str, date):
            return date_str

        date_str = str(date_str).strip()

        try:
            if "-" in date_str and len(date_str) >= 7:
                if len(date_str) >= 10:
                    return date.fromisoformat(date_str[:10])
                return date.fromisoformat(date_str[:7] + "-01")
        except (ValueError, AttributeError):
            pass

        try:
            if "/" in date_str:
                parts = date_str.split("/")
                if len(parts) >= 3:
                    year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
                    return date(year, month, day)
                elif len(parts) == 2:
                    year, month = int(parts[0]), int(parts[1])
                    return date(year, month, 1)
        except (ValueError, AttributeError):
            pass

        try:
            if "." in date_str:
                parts = date_str.split(".")
                if len(parts) >= 3:
                    year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
                    return date(year, month, day)
                elif len(parts) == 2:
                    year, month = int(parts[0]), int(parts[1])
                    return date(year, month, 1)
        except (ValueError, AttributeError):
            pass

        year_match = re.search(r"\b(19|20)\d{2}\b", date_str)
        if year_match:
            try:
                return date(int(year_match.group(0)), 1, 1)
            except ValueError:
                pass

        return None

    def _parse_price(self, price_val: Any) -> float | None:
        """Parse price from CPG payload.

        CPG prices may be in various formats:
        - "3.99"
        - "$3.99"
        - "1,299.99"
        - 3.99 (number)

        Args:
            price_val: Price value from CPG

        Returns:
            Price as float or None
        """
        if price_val is None:
            return None

        if isinstance(price_val, (int, float)):
            return float(price_val)

        if isinstance(price_val, str):
            price_str = str(price_val).replace("$", "").replace(",", "")
            price_match = re.search(r"[\d.]+", price_str)
            if price_match:
                try:
                    return float(price_match.group(0))
                except ValueError:
                    pass

        return None
