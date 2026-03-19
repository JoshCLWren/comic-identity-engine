"""CLZ (ComicBookDB/Comic Collector) CSV import adapter implementation.

This adapter ingests data from CLZ CSV exports (91-column format) and maps it
to internal candidate models. CLZ is personal collection management software
that exports to CSV format.

CLZ CSV Format:
- 91 columns total
- Uses compact variant notation (e.g., "#-1A" for issue -1, variant A)
- Separates release date from cover date
- Includes UPC/Barcode for cross-platform validation
"""

import csv
import re
from datetime import date
from io import StringIO
from pathlib import Path
from typing import Any

from comic_identity_engine.adapters import (
    SourceAdapter,
    ValidationError,
)
from longbox_commons import parse_issue_candidate
from longbox_commons.models import IssueCandidate, SeriesCandidate


# Format codes used by CLZ as "issue numbers" for collected editions.
# These are not real issue numbers — default to "1" and treat the code as a variant.
FORMAT_ISSUE_CODES = frozenset(
    {
        "TP",  # Trade Paperback
        "HC",  # Hardcover
        "GN",  # Graphic Novel
        "SC",  # Softcover
        "TPB",  # Trade Paperback (alternate)
        "OGN",  # Original Graphic Novel
        "OM",  # Omnibus
    }
)


class CLZAdapter(SourceAdapter):
    """Adapter for CLZ (ComicBookDB/Comic Collector) CSV imports.

    This adapter works with pre-loaded CSV data. It does not make any
    network calls - it accepts CSV file paths or CSV strings.
    """

    SOURCE = "clz"

    def __init__(self) -> None:
        """Initialize CLZ adapter."""
        pass

    async def fetch_series(self, source_series_id: str) -> SeriesCandidate:
        """Fetch series from CLZ CSV data.

        Args:
            source_series_id: CLZ series identifier (e.g., "X-Men, Vol. 1")

        Returns:
            SeriesCandidate with validated metadata

        Raises:
            NotImplementedError: Use fetch_series_from_csv_row() instead
        """
        raise NotImplementedError(
            "Use fetch_series_from_csv_row() instead - this adapter "
            "does not fetch data from remote sources"
        )

    async def fetch_issue(
        self, source_issue_id: str, full_url: str | None = None
    ) -> IssueCandidate:
        """Fetch issue from CLZ CSV data.

        Args:
            source_issue_id: CLZ issue identifier (row index or CSV ID)

        Returns:
            IssueCandidate with validated metadata

        Raises:
            NotImplementedError: Use fetch_issue_from_csv_row() instead
        """
        raise NotImplementedError(
            "Use fetch_issue_from_csv_row() instead - this adapter "
            "does not fetch data from remote sources"
        )

    def load_csv_from_file(self, file_path: str | Path) -> list[dict[str, str]]:
        """Load CSV file and return list of row dictionaries.

        Args:
            file_path: Path to CLZ CSV export file

        Returns:
            List of dictionaries, one per CSV row

        Raises:
            ValidationError: If CSV cannot be parsed
        """
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                return self._parse_csv_content(f.read())
        except FileNotFoundError as e:
            raise ValidationError(f"CSV file not found: {file_path}") from e
        except UnicodeDecodeError as e:
            raise ValidationError(f"CSV file encoding error: {e}") from e

    def load_csv_from_string(self, csv_content: str) -> list[dict[str, str]]:
        """Load CSV from string and return list of row dictionaries.

        Args:
            csv_content: CSV content as string

        Returns:
            List of dictionaries, one per CSV row

        Raises:
            ValidationError: If CSV cannot be parsed
        """
        return self._parse_csv_content(csv_content)

    def _parse_csv_content(self, content: str) -> list[dict[str, str]]:
        """Parse CSV content into list of dictionaries.

        Args:
            content: CSV content as string

        Returns:
            List of dictionaries, one per CSV row

        Raises:
            ValidationError: If CSV cannot be parsed
        """
        if not content or not content.strip():
            raise ValidationError("CSV content is empty")

        try:
            # Strip UTF-8 BOM if present
            if content.startswith("\ufeff"):
                content = content[1:]

            reader = csv.DictReader(StringIO(content))
            rows = list(reader)

            if not rows:
                raise ValidationError("CSV contains no data rows")

            return rows

        except csv.Error as e:
            raise ValidationError(f"CSV parsing error: {e}") from e

    def fetch_series_from_csv_row(
        self, source_series_id: str, row: dict[str, str]
    ) -> SeriesCandidate:
        """Parse series from CLZ CSV row.

        Args:
            source_series_id: CLZ series identifier (e.g., "X-Men, Vol. 1")
            row: Single CSV row as dictionary

        Returns:
            SeriesCandidate with validated metadata

        Raises:
            ValidationError: Required fields missing
        """
        if not row:
            raise ValidationError("CLZ CSV row is empty")

        series_title = self._extract_series_title(row)
        if not series_title:
            raise ValidationError(
                "CLZ series missing required field: series title (Series)"
            )

        publisher = row.get("Publisher")
        year_began = self._parse_year(
            row.get("Year") or row.get("Cover Year") or row.get("Release Year")
        )

        return SeriesCandidate(
            source=self.SOURCE,
            source_series_id=source_series_id,
            series_title=series_title,
            series_start_year=year_began,
            publisher=publisher,
            raw_payload=row,
        )

    def fetch_issue_from_csv_row(self, row: dict[str, str]) -> IssueCandidate:
        """Parse issue from CLZ CSV row.

        Args:
            row: Single CSV row as dictionary

        Returns:
            IssueCandidate with validated metadata

        Raises:
            ValidationError: Required fields missing or issue number invalid
        """
        if not row:
            raise ValidationError("CLZ CSV row is empty")

        core_comic_id = row.get("Core ComicID")
        if not core_comic_id:
            raise ValidationError("CLZ issue missing required field: Core ComicID")
        source_issue_id = str(core_comic_id).strip()

        series_title = self._extract_series_title(row)
        if not series_title:
            raise ValidationError(
                "CLZ issue missing required field: series title (Series)"
            )

        issue_number_raw = (row.get("Issue") or "").strip()

        # Handle CLZ "NN" (No Number) placeholders
        # These appear when CLZ can't determine the actual issue number
        # Patterns: NN, NN-NN, 1998NN-NN (number + NN + optional suffix)
        if re.match(
            r"^(NN|NN-NN|\d+NN(-[A-Za-z0-9]+)*)$", issue_number_raw, re.IGNORECASE
        ):
            # Check if there's a numeric issue number in "Issue Nr" column
            issue_nr = (row.get("Issue Nr") or "").strip()
            if issue_nr and issue_nr.isdigit():
                issue_number_raw = issue_nr
            else:
                # Default to issue 1 if no Issue Nr available
                issue_number_raw = "1"

        if not issue_number_raw:
            # Missing issue number — default to "1" if Format is present
            # (e.g., Trade Paperback with no issue number)
            fmt = (row.get("Format") or "").strip()
            if fmt:
                issue_number_raw = "1"
            else:
                raise ValidationError("CLZ issue missing required field: Issue")

        # Normalize unicode fraction characters to ASCII equivalents
        issue_number_raw = self._normalize_unicode_symbols(issue_number_raw)

        # Handle format codes (TP, HC, GN, etc.) that CLZ uses as issue numbers
        # for collected editions — default to issue "1" with the format as variant.
        parse_result = None
        format_result = self._parse_format_issue(issue_number_raw.strip())
        if format_result:
            canonical_issue_number, variant_suffix_override = format_result
        else:
            variant_suffix_override = None
            parse_result = parse_issue_candidate(issue_number_raw)
            if not parse_result.success:
                raise ValidationError(
                    f"Invalid issue number '{issue_number_raw}': {parse_result.error_code}"
                )

            if parse_result.canonical_issue_number is None:
                raise ValidationError(
                    f"Issue number '{issue_number_raw}' parsed successfully but produced no canonical form"
                )
            canonical_issue_number = parse_result.canonical_issue_number

        publisher = row.get("Publisher")
        year_began = self._parse_year(
            row.get("Year") or row.get("Cover Year") or row.get("Release Year")
        )

        cover_date = self._parse_date(row.get("Cover Date"))
        publication_date = self._parse_date(row.get("Release Date"))

        price = self._parse_price(row.get("Price") or row.get("Cover Price"))
        page_count = self._parse_page_count(row.get("Pages") or row.get("No. of Pages"))
        upc = self._clean_upc(row.get("Barcode") or row.get("UPC"))

        if variant_suffix_override:
            variant_suffix = variant_suffix_override
        else:
            variant_suffix = parse_result.variant_suffix if parse_result else None

        variant_name = (row.get("Variant Description") or "").strip() or None

        return IssueCandidate(
            source=self.SOURCE,
            source_series_id=self._extract_series_id(row),
            source_issue_id=source_issue_id,
            series_title=series_title,
            series_start_year=year_began,
            publisher=publisher,
            issue_number=canonical_issue_number,
            variant_suffix=variant_suffix,
            variant_name=variant_name,
            cover_date=cover_date,
            publication_date=publication_date,
            price=price,
            page_count=page_count,
            upc=upc,
            raw_payload=row,
        )

    # Unicode symbol → ASCII mapping for issue number normalization
    _UNICODE_SYMBOLS: dict[str, str] = {
        "½": "1/2",
        "⅓": "1/3",
        "⅔": "2/3",
        "¼": "1/4",
        "¾": "3/4",
        "⅕": "1/5",
        "⅙": "1/6",
        "⅛": "1/8",
        "∞": "INF",
    }

    @classmethod
    def _normalize_unicode_symbols(cls, raw: str) -> str:
        """Replace unicode symbols with ASCII equivalents.

        CLZ exports may use characters like ½ instead of 1/2, or ∞ for infinity issues.
        Also normalizes CLZ's "½-A" separator style to "1/2A" for the parser.
        """
        for char, replacement in cls._UNICODE_SYMBOLS.items():
            if char in raw:
                raw = raw.replace(char, replacement)
                # Remove hyphen separator before variant letter after fractions
                # e.g. "½-A" → "1/2-A" → "1/2A"
                # Also for INF issues: "INF-A" → "INFA"
                if "/" in replacement:
                    raw = re.sub(r"(\d/\d+)-([A-Za-z])", r"\1\2", raw)
                if replacement == "INF":
                    raw = re.sub(r"^INF-([A-Za-z])", r"INF\1", raw)
        return raw

    @staticmethod
    def _parse_format_issue(raw: str) -> tuple[str, str] | None:
        """Parse CLZ format-as-issue-number patterns.

        CLZ sometimes uses format codes as issue numbers for collected editions:
          - "TP"    → issue "1", variant "TP"
          - "HC"    → issue "1", variant "HC"
          - "TP-1"  → issue "1", variant "TP"  (TP volume 1)
          - "HC-2"  → issue "2", variant "HC"  (HC volume 2)
          - "1HC-E" → issue "1", variant "HC-E" (issue 1, hardcover variant E)

        Returns:
            (canonical_issue_number, variant_suffix) tuple, or None if not a format pattern.
        """
        upper = raw.upper()

        # Pattern 1: bare format code → "TP", "HC", etc.
        if upper in FORMAT_ISSUE_CODES:
            return ("1", upper)

        # Pattern 2: format code with suffix → "TP-1", "HC-2", "TP-D", "TP-B"
        fmt_suffix = re.match(r"^([A-Z]+)-([A-Z0-9]+)$", upper)
        if fmt_suffix and fmt_suffix.group(1) in FORMAT_ISSUE_CODES:
            suffix = fmt_suffix.group(2)
            # If suffix is digits, it's a volume number → use as issue number
            if suffix.isdigit():
                return (suffix, fmt_suffix.group(1))
            # Otherwise it's a variant letter → default to issue 1
            return ("1", f"{fmt_suffix.group(1)}-{suffix}")

        # Pattern 3: number + format code + optional variant → "1HC-E", "2TP"
        num_fmt = re.match(r"^(\d+)([A-Z]+)(?:-([A-Za-z]+))?$", upper)
        if num_fmt and num_fmt.group(2) in FORMAT_ISSUE_CODES:
            variant = num_fmt.group(2)
            if num_fmt.group(3):
                variant = f"{variant}-{num_fmt.group(3)}"
            return (num_fmt.group(1), variant)

        return None

    def _extract_series_title(self, row: dict[str, str]) -> str | None:
        """Extract series title from CSV row.

        CLZ typically uses "Series" column. May include volume info.

        Args:
            row: CSV row dictionary

        Returns:
            Series title or None
        """
        series = row.get("Series")
        if series:
            return series.strip()

        return None

    def _extract_series_id(self, row: dict[str, str]) -> str:
        """Extract series identifier from CSV row.

        Uses series title as ID since CLZ doesn't provide numeric series IDs.

        Args:
            row: CSV row dictionary

        Returns:
            Series identifier string
        """
        series_title = self._extract_series_title(row)
        return series_title if series_title else ""

    def _parse_year(self, year_str: str | None) -> int | None:
        """Parse year from CLZ year string.

        Args:
            year_str: Year string (e.g., "1997", "1991")

        Returns:
            Year as int or None
        """
        if not year_str:
            return None

        try:
            year = int(str(year_str).strip())
            if 1800 <= year <= 2100:
                return year
        except ValueError:
            pass

        return None

    def _parse_date(self, date_str: str | None) -> date | None:
        """Parse date from CLZ date string.

        CLZ formats: "May 21, 1997", "Jul 1997", "1997-07-01"

        Args:
            date_str: Date string from CSV

        Returns:
            Date object or None
        """
        if not date_str:
            return None

        date_str = date_str.strip()

        if not date_str:
            return None

        try:
            from datetime import datetime

            for fmt in ("%B %d, %Y", "%b %d, %Y", "%B %Y", "%b %Y", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(date_str, fmt)
                    return parsed.date()
                except ValueError:
                    continue
        except (AttributeError, TypeError, RuntimeError):
            pass

        return None

    def _parse_price(self, price_str: str | None) -> float | None:
        """Parse price from CLZ price string.

        CLZ format: "$1.95", "1.95", "1.95 USD"

        Args:
            price_str: Price string from CSV

        Returns:
            Price as float or None
        """
        if not price_str:
            return None

        try:
            cleaned = str(price_str).strip().replace("$", "").strip()
            if cleaned:
                return float(cleaned)
        except ValueError:
            pass

        return None

    def _parse_page_count(self, page_str: Any) -> int | None:
        """Parse page count from CLZ page count string.

        Args:
            page_str: Page count string (e.g., "32", "32 pages")

        Returns:
            Page count as int or None
        """
        if not page_str:
            return None

        try:
            cleaned = str(page_str).strip().split()[0]
            if cleaned.isdigit():
                return int(cleaned)
        except (ValueError, AttributeError):
            pass

        return None

    def _clean_upc(self, upc_str: str | None) -> str | None:
        """Clean UPC/barcode string.

        Removes spaces and formatting.

        Args:
            upc_str: UPC string from CSV

        Returns:
            Cleaned UPC string or None
        """
        if not upc_str:
            return None

        cleaned = str(upc_str).strip().replace(" ", "").replace("-", "")
        if cleaned and cleaned.isdigit():
            return cleaned

        return None
