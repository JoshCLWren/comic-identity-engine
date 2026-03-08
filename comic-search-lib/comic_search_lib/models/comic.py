"""
Data models for comic search library.

Simplified models extracted from comic-web-scrapers.
"""

import datetime
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Comic:
    """Represents a comic book with basic information.

    Attributes:
        id: Unique identifier for the comic
        title: Comic title
        issue: Issue number
        year: Publication year if known
        publisher: Publisher name if known
        series_start_year: First year of the series if known
        series_end_year: Last year of the series if known
        metadata: Additional comic metadata
    """

    id: str
    title: str
    issue: str
    year: Optional[int] = None
    publisher: Optional[str] = None
    series_start_year: Optional[int] = None
    series_end_year: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Normalize the title after initialization."""
        if "#" in self.title:
            self.title = self.title.split("#")[0].strip()
        self.normalized_title = self._normalize_title()

    def _normalize_title(self) -> str:
        """Normalize a comic title for consistent matching.

        Removes common prefixes, articles, special characters, and extra whitespace.
        Handles special cases like X-Men, Spider-Man, etc.

        Returns:
            str: Normalized title
        """
        if not self.title:
            raise ValueError("Must have title")

        normalized = self.title.lower()

        # Create a list of character name patterns where hyphens should be preserved
        preserve_patterns = [
            r"x-men",
            r"x-force",
            r"x-factor",
            r"spider-man",
            r"iron-man",
            r"ant-man",
        ]

        # Handle embedded years (common pattern like X-Men-2012)
        normalized = re.sub(r"-\d{4}(?:\b|$)", "", normalized)

        # Replace these patterns with temporary markers
        for i, pattern in enumerate(preserve_patterns):
            normalized = re.sub(
                r"\b" + re.escape(pattern) + r"\b", f"PRESERVE_HYPHEN_{i}", normalized
            )

        # Convert remaining hyphens to spaces
        normalized = normalized.replace("-", " ")

        # Restore preserved hyphenated names
        for i, pattern in enumerate(preserve_patterns):
            normalized = normalized.replace(f"PRESERVE_HYPHEN_{i}", pattern)

        # Remove special issue designations
        for designation in ["special", "annual", "ongoing"]:
            normalized = re.sub(
                r"\b" + designation + r"\b", "", normalized, flags=re.IGNORECASE
            )

        # Remove text in parentheses
        normalized = re.sub(r"\s*\(.*?\)", "", normalized)

        # Remove "the" prefix
        if normalized.startswith("the "):
            normalized = normalized[4:]

        # Remove publisher prefixes
        publishers = ["marvel", "dc", "image", "dark horse", "idw", "vertigo"]
        for publisher in publishers:
            if normalized.startswith(f"{publisher} "):
                normalized = normalized[len(publisher) + 1 :]
            if normalized.endswith(f" {publisher}"):
                normalized = normalized[: -len(publisher) - 1]

        # Remove special characters and extra whitespace
        normalized = re.sub(r"[^\w\s-]", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()

        if not normalized:
            raise ValueError("Must have title")
        return normalized


@dataclass
class ComicListing:
    """Represents a listing for a comic book found on a marketplace.

    Attributes:
        store: Store or seller name
        title: Title of the listing
        price: Price of the comic
        grade: Condition grade if provided
        url: URL to the listing
        image_url: URL to the listing image
        store_type: Type of store (hip, aa, ccl, etc.)
        metadata: Additional listing metadata
    """

    store: str
    title: str
    price: str
    grade: Optional[str] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    store_type: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComicPrice:
    """Represents a price for a comic book.

    Attributes:
        store: Store or seller name
        value: Price value as a string (e.g., "$4.99")
        grade: Condition grade if provided
        url: URL to the listing
        store_type: Type of store (hip, aa, ccl, etc.)
        timestamp: When this price was recorded
        metadata: Additional price metadata
    """

    store: str
    value: str
    grade: Optional[str] = None
    url: Optional[str] = None
    store_type: str = "unknown"
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """Represents the result of a comic search operation.

    Attributes:
        comic: Original comic that was searched for
        listings: List of comic listings found
        prices: List of comic prices extracted
        metadata: Additional search result metadata
        url: Direct URL to the search result (if available)
        source_issue_id: Source issue ID extracted from URL
    """

    comic: Comic
    listings: List[ComicListing] = field(default_factory=list)
    prices: List[ComicPrice] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    url: Optional[str] = None
    source_issue_id: Optional[str] = None

    @property
    def has_results(self) -> bool:
        """Check if the search found any results."""
        return len(self.listings) > 0 or len(self.prices) > 0 or self.url is not None
