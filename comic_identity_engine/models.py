"""Internal candidate models for source ingestion.

These models represent the intermediate state between raw source data
and the canonical entity model. They are intentionally flexible to
accommodate variations across different comic platforms.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional


@dataclass
class SeriesCandidate:
    """Intermediate series representation from a source platform.

    This is NOT the canonical series entity - it's a candidate that
    will be reconciled against the canonical database during ingestion.
    """

    # Source identification
    source: str  # e.g., "gcd", "locg", "ccl", "clz", "aa", "cpg"
    source_series_id: str

    # Core series metadata
    series_title: str
    series_start_year: Optional[int]
    publisher: Optional[str]

    # Optional fields for future enhancement
    series_end_year: Optional[int] = None
    volume_number: Optional[int] = None

    # Audit/debug
    raw_payload: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source": self.source,
            "source_series_id": self.source_series_id,
            "series_title": self.series_title,
            "series_start_year": self.series_start_year,
            "publisher": self.publisher,
            "series_end_year": self.series_end_year,
            "volume_number": self.volume_number,
        }


@dataclass
class IssueCandidate:
    """Intermediate issue representation from a source platform.

    This is NOT the canonical issue entity - it's a candidate that
    will be reconciled against the canonical database during ingestion.

    The issue_number field must be validated using parse_issue_candidate()
    before this object is created.
    """

    # Source identification
    source: str
    source_series_id: str
    source_issue_id: str

    # Series reference
    series_title: str
    series_start_year: Optional[int]
    publisher: Optional[str]

    # Issue metadata
    issue_number: str  # Canonical form, validated by parse_issue_candidate()
    variant_suffix: Optional[
        str
    ]  # Extracted variant code (e.g., "A", "DE", "WIZ.SIGNED")

    # Publication metadata
    cover_date: Optional[date] = None
    publication_date: Optional[date] = None  # On-sale date if different

    # Optional fields for future enhancement
    price: Optional[float] = None
    page_count: Optional[int] = None
    upc: Optional[str] = None  # Universal Product Code - strong cross-platform key
    isbn: Optional[str] = None
    variant_name: Optional[str] = None  # Human-readable variant description

    # Audit/debug
    raw_payload: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source": self.source,
            "source_series_id": self.source_series_id,
            "source_issue_id": self.source_issue_id,
            "series_title": self.series_title,
            "series_start_year": self.series_start_year,
            "publisher": self.publisher,
            "issue_number": self.issue_number,
            "variant_suffix": self.variant_suffix,
            "cover_date": self.cover_date.isoformat() if self.cover_date else None,
            "publication_date": self.publication_date.isoformat()
            if self.publication_date
            else None,
            "price": self.price,
            "page_count": self.page_count,
            "upc": self.upc,
            "isbn": self.isbn,
            "variant_name": self.variant_name,
        }

    def get_display_issue_number(self) -> str:
        """Get the display form of issue number with variant suffix."""
        if self.variant_suffix:
            return f"{self.issue_number}.{self.variant_suffix}"
        return self.issue_number
