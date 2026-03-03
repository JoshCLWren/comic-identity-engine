"""Comics Price Guide (CPG) adapter implementation.

This adapter ingests pre-fetched CPG data and maps it to internal
candidate models. CPG provides comic pricing and marketplace data
with coverage of both older and modern comics.

CPG URL format:
- comicspriceguide.com/titles/SERIES_SLUG/ISSUE_NUM/ISSUE_ID
- comicspriceguide.com/titles/SERIES_SLUG/ISSUE_NUM-VARIANT/ISSUE_ID
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


class CPGAdapter(SourceAdapter):
    """Adapter for Comics Price Guide (comicspriceguide.com).

    This adapter works with pre-fetched CPG data payloads. It does not
    make any network calls - it accepts raw JSON/dict payloads.
    """

    SOURCE = "cpg"

    def fetch_series(self, source_series_id: str) -> SeriesCandidate:
        """Fetch series from CPG data payload.

        Args:
            source_series_id: CPG series slug (e.g., "x-men")

        Returns:
            SeriesCandidate with validated metadata

        Raises:
            NotImplementedError: Use fetch_series_from_payload() instead
        """
        raise NotImplementedError(
            "Use fetch_series_from_payload() instead - this adapter "
            "does not fetch data from remote sources"
        )

    def fetch_issue(self, source_issue_id: str) -> IssueCandidate:
        """Fetch issue from CPG data payload.

        Args:
            source_issue_id: CPG resource ID

        Returns:
            IssueCandidate with validated metadata

        Raises:
            NotImplementedError: Use fetch_issue_from_payload() instead
        """
        raise NotImplementedError(
            "Use fetch_issue_from_payload() instead - this adapter "
            "does not fetch data from remote sources"
        )

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
        if not price_val:
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
