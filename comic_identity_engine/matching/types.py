"""Matching strategy types and confidence levels."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MatchConfidence(Enum):
    """Confidence levels for match results.

    Used by round-robin strategy selection to pick the best match.
    Higher is better. Unknown/None means no match.
    """

    # Barcode matches are authoritative
    BARCODE = 100

    # Exact name + exact issue number (series has only one issue with that number)
    EXACT_ONE_ISSUE = 90

    # Exact name + closest year by issue cover date
    EXACT_CLOSEST_YEAR = 85

    # Exact name match (no issue-level info needed)
    EXACT_SERIES = 80

    # Normalized name match (punctuation differences, &/and)
    NORMALIZED_SERIES = 75

    # Word-order match (X-Men Classic vs Classic X-Men)
    WORD_ORDER_SERIES = 70

    # Colon/comma variant match
    COLON_COMMA_SERIES = 68

    # Reverse lookup: issue+year found unique series
    REVERSE_LOOKUP_ONE = 65

    # Article prefix/suffix match (The/X-Men)
    ARTICLE_SERIES = 60

    # Reverse lookup: issue+year found multiple series, pick by name similarity
    REVERSE_LOOKUP_SIMILARITY = 55

    # Substring match (last resort for name)
    SUBSTRING_SERIES = 50

    # No match found
    NO_MATCH = 0


@dataclass
class StrategyResult:
    """Result from a single matching strategy."""

    confidence: MatchConfidence
    gcd_issue_id: int | None = None
    gcd_series_id: int | None = None
    strategy_name: str = ""
    match_details: str = ""
    series_name: str = ""
    issue_number: str = ""
    year_distance: int | None = None  # |cover_year - clz_year|

    def is_match(self) -> bool:
        return (
            self.confidence != MatchConfidence.NO_MATCH
            and self.gcd_issue_id is not None
        )


@dataclass
class CLZInput:
    """Normalized input from a CLZ CSV row."""

    comic_id: str
    series_name: str
    series_name_normalized: str
    series_name_strict: str
    series_group: str
    series_group_normalized: str
    series_group_strict: str
    issue_nr: str  # Parsed issue number (digits only, or "1" if empty)
    issue_full: str  # Full issue field (may include variant suffix)
    year: int | None
    barcode: str
    cover_year: int | None
    publisher: str  # Normalized publisher name from CLZ
    publisher_normalized: str  # Normalized for matching

    @classmethod
    def from_csv_row(cls, row: dict) -> CLZInput:
        """Parse a CLZ CSV row into normalized input."""
        from . import normalizers

        raw_series = row.get("Series", "")
        raw_series_group = row.get("Series Group", "")
        raw_publisher = row.get("Publisher", "")
        issue_full = row.get("Issue", "").strip()
        issue_nr_raw = row.get("Issue Nr", "").strip()

        return cls(
            comic_id=row.get("Core ComicID", ""),
            series_name=raw_series,
            series_name_normalized=normalizers.normalize_series_name(raw_series),
            series_name_strict=normalizers.normalize_series_name_strict(raw_series),
            series_group=raw_series_group,
            series_group_normalized=normalizers.normalize_series_name(raw_series_group),
            series_group_strict=normalizers.normalize_series_name_strict(
                raw_series_group
            ),
            issue_nr=normalizers.parse_issue_nr({"Issue Nr": issue_nr_raw}) or "1",
            issue_full=issue_full,
            year=cls._parse_year(row.get("Cover Year")),
            barcode=row.get("Barcode", ""),
            cover_year=cls._parse_year(row.get("Cover Year")),
            publisher=raw_publisher,
            publisher_normalized=normalizers.normalize_publisher(raw_publisher),
        )

    @staticmethod
    def _parse_year(value: str | int | None) -> int | None:
        """Parse year from various formats."""
        if value is None:
            return None
        if isinstance(value, int):
            return value if 1950 <= value <= 2026 else None
        try:
            year = int(float(value))
            return year if 1950 <= year <= 2026 else None
        except (ValueError, TypeError):
            return None
