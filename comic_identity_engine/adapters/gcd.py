"""Grand Comics Database (GCD) adapter implementation.

This adapter ingests data from the GCD API and maps it to internal
candidate models. GCD is one of the most authoritative sources for
comic metadata, with excellent coverage of Golden/Silver/Bronze Age.

GCD API format: https://www.comics.org/api/issue/{id}/?format=json
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


class GCDAdapter(SourceAdapter):
    """Adapter for Grand Comics Database (comics.org).

    This adapter works with pre-fetched GCD API responses. It does not
    make any network calls - it accepts raw JSON payloads.
    """

    SOURCE = "gcd"

    def __init__(self) -> None:
        """Initialize GCD adapter."""
        pass

    def fetch_series(self, source_series_id: str) -> SeriesCandidate:
        """Fetch series from GCD API response.

        Args:
            source_series_id: GCD series ID (e.g., "4254")

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
        """Fetch issue from GCD API response.

        Args:
            source_issue_id: GCD issue ID (e.g., "125295")

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
        """Parse series from pre-fetched GCD API payload.

        Args:
            source_series_id: GCD series ID (e.g., "4254")
            payload: Raw GCD series API response as dict

        Returns:
            SeriesCandidate with validated metadata

        Raises:
            ValidationError: Required fields missing
        """
        if not payload:
            raise ValidationError("GCD series payload is empty")

        name = payload.get("name")
        if not name:
            raise ValidationError("GCD series missing required field: name")

        year_began = payload.get("year_began")
        if year_began is None:
            raise ValidationError("GCD series missing required field: year_began")

        publisher = self._extract_publisher_from_series(payload)

        return SeriesCandidate(
            source=self.SOURCE,
            source_series_id=source_series_id,
            series_title=name,
            series_start_year=int(year_began),
            publisher=publisher,
            series_end_year=payload.get("year_ended"),
            raw_payload=payload,
        )

    def fetch_issue_from_payload(
        self, source_issue_id: str, payload: dict[str, Any]
    ) -> IssueCandidate:
        """Parse issue from pre-fetched GCD API payload.

        Args:
            source_issue_id: GCD issue ID (e.g., "125295")
            payload: Raw GCD issue API response as dict

        Returns:
            IssueCandidate with validated metadata

        Raises:
            ValidationError: Required fields missing or issue number invalid
        """
        if not payload:
            raise ValidationError("GCD issue payload is empty")

        series_name = payload.get("series_name")
        if not series_name:
            raise ValidationError("GCD issue missing required field: series_name")

        number = payload.get("number")
        if not number:
            raise ValidationError("GCD issue missing required field: number")

        parse_result = parse_issue_candidate(number)
        if not parse_result.success:
            raise ValidationError(
                f"Invalid issue number '{number}': {parse_result.error_code}"
            )

        if parse_result.canonical_issue_number is None:
            raise ValidationError(
                f"Issue number '{number}' parsed successfully but produced no canonical form"
            )

        series_title, start_year = self._parse_series_name(series_name)
        publisher = payload.get("indicia_publisher")

        variant_suffix = self._extract_variant_suffix_from_descriptor(
            payload.get("descriptor", "")
        )
        variant_name = payload.get("variant_name")

        cover_date = self._parse_key_date(payload.get("key_date"))
        publication_date = self._parse_on_sale_date(payload.get("on_sale_date"))

        price = self._parse_price(payload.get("price", ""))
        page_count = self._parse_page_count(payload.get("page_count"))
        upc = payload.get("barcode") or None

        return IssueCandidate(
            source=self.SOURCE,
            source_series_id=self._extract_series_id_from_payload(payload),
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

    def _parse_series_name(self, series_name: str) -> tuple[str, int | None]:
        """Extract series title and start year from GCD series name.

        GCD format: "X-Men (1991 series)" or "Amazing Spider-Man (1963 series)"

        Args:
            series_name: GCD series name string

        Returns:
            Tuple of (series_title, start_year)
        """
        match = re.search(r"\((\d{4}) series\)", series_name)
        if match:
            year = int(match.group(1))
            title = series_name[: match.start()].strip()
            return title, year
        return series_name, None

    def _extract_variant_suffix_from_descriptor(self, descriptor: str) -> str | None:
        """Extract variant suffix from GCD descriptor.

        GCD descriptors like "-1 [Direct Edition]" or "100 [Adams cover]"

        Args:
            descriptor: GCD issue descriptor

        Returns:
            Variant suffix code or None
        """
        if not descriptor:
            return None

        # Distribution markers - not variants
        distribution_markers = [
            "Direct",
            "Direct Edition",
            "Newsstand",
            "Australian",
            "Edition",  # "Direct Edition" splits to "Direct" and "Edition"
        ]

        # Split by brackets and space
        parts = descriptor.strip("[]").split()

        # Remove issue number from parts (looks like "-1", "100", "1/2", etc.)
        # This filters out numbers and negative numbers
        variant_parts = []
        for part in parts:
            part = part.strip("[]")
            # Skip if it looks like an issue number (starts with digit or minus)
            if part and not (part[0].isdigit() or part[0] == "-"):
                variant_parts.append(part)

        # Check for distribution-only descriptors
        if all(p in distribution_markers for p in variant_parts):
            return None

        # Check for variant indicators
        for part in variant_parts:
            # Skip distribution markers
            if part in distribution_markers:
                continue

            # Explicit variant markers
            if part in ["Variant Edition", "Variant"]:
                return "VARIANT"

            # Single letter variants (A, B, C, etc.)
            if len(part) == 1 and part.isalpha():
                return part.upper()

            # Cover artist references (e.g., "Adams cover", "Cover A")
            if "cover" in part.lower() and part != "Direct Edition cover":
                # Extract the artist/letter part
                if " " in part:
                    prefix = part.split()[0]
                    if len(prefix) == 1 and prefix.isalpha():
                        return prefix.upper()

        # If we have non-distribution descriptors but couldn't extract a code,
        # mark as variant for human review
        non_distribution = [p for p in variant_parts if p not in distribution_markers]
        if non_distribution:
            return "VARIANT"

        return None

    def _extract_publisher_from_series(self, payload: dict[str, Any]) -> str | None:
        """Extract publisher from GCD series payload.

        GCD provides publisher as URL, we'd need to fetch it separately.
        For now, return None.

        Args:
            payload: GCD series API response

        Returns:
            Publisher name or None
        """
        return None

    def _extract_series_id_from_payload(self, payload: dict[str, Any]) -> str:
        """Extract series ID from GCD issue payload.

        Args:
            payload: GCD issue API response

        Returns:
            Series ID as string
        """
        series_url = payload.get("series", "")
        if series_url:
            match = re.search(r"/series/(\d+)/", series_url)
            if match:
                return match.group(1)
        return ""

    def _parse_key_date(self, key_date: str | None) -> date | None:
        """Parse GCD key_date (YYYY-MM-DD format).

        Args:
            key_date: GCD key_date string

        Returns:
            Date object or None
        """
        if not key_date:
            return None
        try:
            if len(key_date) >= 7:
                return date.fromisoformat(key_date[:7] + "-01")
        except ValueError:
            pass
        return None

    def _parse_on_sale_date(self, on_sale_date: str | None) -> date | None:
        """Parse GCD on_sale_date.

        Args:
            on_sale_date: GCD on_sale_date string

        Returns:
            Date object or None
        """
        if not on_sale_date:
            return None
        try:
            return date.fromisoformat(on_sale_date)
        except ValueError:
            return None

    def _parse_price(self, price_str: str) -> float | None:
        """Parse price from GCD price string.

        GCD format: "1.95 USD; 2.75 CAD"

        Args:
            price_str: GCD price string

        Returns:
            Price as float or None
        """
        if not price_str:
            return None
        match = re.search(r"([\d.]+)\s*USD", price_str)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return None

    def _parse_page_count(self, page_count: str | None) -> int | None:
        """Parse page count from GCD page_count string.

        GCD format: "44.000"

        Args:
            page_count: GCD page_count string

        Returns:
            Page count as int or None
        """
        if not page_count:
            return None
        try:
            return int(float(page_count))
        except ValueError:
            return None
