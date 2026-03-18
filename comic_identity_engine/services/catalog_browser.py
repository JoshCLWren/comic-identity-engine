"""Catalog browser service for deterministic comic lookup.

This service implements hierarchical catalog traversal:
- Level 1: Publisher catalog
- Level 2: Series within publisher
- Level 3: Issues within series

Scoring System:
- Publisher match: 30 points
- Series match: 30 points
- Issue match: 30 points
- Year confirmation: 10 points (bonus)
- Minimum for high confidence: 90 points

USAGE:
    from comic_identity_engine.services.catalog_browser import CatalogBrowser

    browser = CatalogBrowser(session)
    result = await browser.find_comic(
        publisher="Marvel",
        series_title="X-Men",
        issue_number="1",
        year=1963,
    )
    if result.confidence_score >= 90:
        # High confidence - use this match
        issue_id = result.issue_id
    else:
        # Low confidence - fallback to search
        searcher = PlatformSearcher(session)
        search_result = await searcher.search_all_platforms(...)
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from comic_identity_engine.database.repositories import (
    IssueRepository,
    SeriesRunRepository,
)

logger = structlog.get_logger(__name__)


@dataclass
class CatalogMatchResult:
    """Result of catalog browsing with confidence scoring.

    Attributes:
        issue_id: Canonical issue UUID (if found)
        series_run_id: Parent series run UUID (if found)
        publisher: Publisher name used for matching
        series_title: Series title used for matching
        issue_number: Issue number used for matching
        year: Year used for matching
        confidence_score: Confidence score (0-100)
        match_explanation: Human-readable explanation of match
        found_via: How the match was found ("catalog" or "none")
        year_confirmed: True if year matched successfully
        publisher_score: Publisher match score (0-30)
        series_score: Series match score (0-40)
        issue_score: Issue match score (0-30)
        year_bonus: Year confirmation bonus (0-10)
    """

    issue_id: Optional[uuid.UUID]
    series_run_id: Optional[uuid.UUID]
    publisher: str
    series_title: str
    issue_number: str
    year: Optional[int]
    confidence_score: int
    match_explanation: str
    found_via: str = "none"
    year_confirmed: bool = False
    publisher_score: int = 0
    series_score: int = 0
    issue_score: int = 0
    year_bonus: int = 0

    @property
    def is_high_confidence(self) -> bool:
        """Check if this is a high-confidence match (>= 90 points)."""
        return self.confidence_score >= 90

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "issue_id": str(self.issue_id) if self.issue_id else None,
            "series_run_id": str(self.series_run_id) if self.series_run_id else None,
            "publisher": self.publisher,
            "series_title": self.series_title,
            "issue_number": self.issue_number,
            "year": self.year,
            "confidence_score": self.confidence_score,
            "is_high_confidence": self.is_high_confidence,
            "match_explanation": self.match_explanation,
            "found_via": self.found_via,
            "year_confirmed": self.year_confirmed,
            "publisher_score": self.publisher_score,
            "series_score": self.series_score,
            "issue_score": self.issue_score,
            "year_bonus": self.year_bonus,
        }


class CatalogBrowser:
    """Service for deterministic comic lookup via catalog traversal.

    This service implements a three-level traversal strategy:
    1. Publisher level: Fetch all series for a publisher
    2. Series level: Filter for matching series, fetch all issues
    3. Issue level: Filter for matching issue, score the match

    Scoring:
    - Publisher match: 30 points (exact match required)
    - Series match: 30 points (normalized title match)
    - Issue match: 30 points (exact or normalized match)
    - Year confirmation: 10 points (bonus if year matches)

    High confidence threshold: 90 points

    Attributes:
        session: Async database session
        issue_repo: Issue repository
        series_repo: Series run repository
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize catalog browser.

        Args:
            session: Async database session
        """
        self.session = session
        self.issue_repo = IssueRepository(session)
        self.series_repo = SeriesRunRepository(session)

    async def find_comic(
        self,
        publisher: str,
        series_title: str,
        issue_number: str,
        year: Optional[int] = None,
    ) -> CatalogMatchResult:
        """Find a comic via catalog traversal.

        This method implements the three-level traversal strategy:
        1. Search database for series matching publisher + title
        2. For each matching series, search for issues matching issue_number
        3. Score each candidate and return the best match

        Args:
            publisher: Publisher name (e.g., "Marvel", "DC Comics")
            series_title: Series title (e.g., "X-Men", "Batman")
            issue_number: Issue number (e.g., "1", "2", "½", "-1")
            year: Publication year (optional, for confirmation bonus)

        Returns:
            CatalogMatchResult with confidence score and match details

        Examples:
            >>> browser = CatalogBrowser(session)
            >>> result = await browser.find_comic(
            ...     publisher="Marvel",
            ...     series_title="X-Men",
            ...     issue_number="1",
            ...     year=1963,
            ... )
            >>> if result.is_high_confidence:
            ...     print(f"Found: {result.issue_id}")
            ...     print(f"Confidence: {result.confidence_score}")
        """
        logger.info(
            "Starting catalog browser lookup",
            publisher=publisher,
            series_title=series_title,
            issue_number=issue_number,
            year=year,
        )

        # Normalize inputs for matching
        normalized_publisher = self._normalize_publisher(publisher)
        normalized_series_title = self._normalize_series_title(series_title)
        normalized_issue_number = self._normalize_issue_number(issue_number)

        # Level 1: Find matching series (publisher + title)
        series_candidates = await self._find_series_candidates(
            normalized_publisher, normalized_series_title
        )

        if not series_candidates:
            logger.info(
                "No series candidates found in catalog",
                publisher=publisher,
                series_title=series_title,
            )
            return self._no_match_result(publisher, series_title, issue_number, year)

        # Level 2: Find matching issues within each series
        issue_candidates = await self._find_issue_candidates(
            series_candidates, normalized_issue_number
        )

        if not issue_candidates:
            logger.info(
                "No issue candidates found in catalog",
                publisher=publisher,
                series_title=series_title,
                issue_number=issue_number,
            )
            return self._no_match_result(publisher, series_title, issue_number, year)

        # Level 3: Score all candidates and return best match
        best_match = await self._score_and_select_best_match(
            issue_candidates,
            normalized_publisher,
            normalized_series_title,
            normalized_issue_number,
            year,
        )

        logger.info(
            "Catalog browser lookup completed",
            found_issue_id=str(best_match.issue_id) if best_match.issue_id else None,
            confidence_score=best_match.confidence_score,
            is_high_confidence=best_match.is_high_confidence,
        )

        return best_match

    async def _find_series_candidates(
        self,
        normalized_publisher: str,
        normalized_series_title: str,
    ) -> list[tuple[uuid.UUID, str, int, str | None]]:
        """Find series matching publisher and title.

        Args:
            normalized_publisher: Normalized publisher name
            normalized_series_title: Normalized series title

        Returns:
            List of (series_run_id, title, start_year, publisher) tuples
        """
        # Query database for matching series
        series_list = await self.series_repo.find_by_publisher_and_title(
            publisher=normalized_publisher,
            title=normalized_series_title,
        )

        candidates = [
            (series.id, series.title, series.start_year, series.publisher)
            for series in series_list
        ]

        logger.debug(
            "Found series candidates",
            count=len(candidates),
            candidates=[c[1] for c in candidates],
        )

        return candidates

    async def _find_issue_candidates(
        self,
        series_candidates: list[tuple[uuid.UUID, str, int, str | None]],
        normalized_issue_number: str,
    ) -> list[tuple[uuid.UUID, uuid.UUID, str, str, Optional[datetime], str]]:
        """Find issues matching issue_number within series candidates.

        Args:
            series_candidates: List of (series_run_id, title, start_year, publisher)
            normalized_issue_number: Normalized issue number

        Returns:
            List of (issue_id, series_run_id, issue_number, series_title, cover_date, publisher)

        Note:
            This method has an N+1 query concern. Each series triggers a separate query.
            Recommended: Add index on issues(series_run_id, issue_number) for performance.
        """
        candidates = []

        for series_run_id, series_title, start_year, publisher in series_candidates:
            # Fetch all issues for this series
            issues = await self.issue_repo.find_by_series_run_id(series_run_id)

            for issue in issues:
                # Normalize issue number for comparison
                if self._issue_numbers_match_exact(
                    issue.issue_number, normalized_issue_number
                ) or self._issue_numbers_match_normalized(
                    issue.issue_number, normalized_issue_number
                ):
                    candidates.append(
                        (
                            issue.id,
                            series_run_id,
                            issue.issue_number,
                            series_title,
                            issue.cover_date,
                            publisher,
                        )
                    )

        logger.debug(
            "Found issue candidates",
            count=len(candidates),
        )

        return candidates

    async def _score_and_select_best_match(
        self,
        issue_candidates: list[
            tuple[uuid.UUID, uuid.UUID, str, str, Optional[datetime], str]
        ],
        normalized_publisher: str,
        normalized_series_title: str,
        normalized_issue_number: str,
        year: Optional[int],
    ) -> CatalogMatchResult:
        """Score all candidates and return the best match.

        Scoring:
        - Publisher match: 30 points (exact match required)
        - Series match: 30 points (normalized title match)
        - Issue match: 30 points (exact or normalized match)
        - Year confirmation: 10 points (bonus if year matches cover_date)

        Args:
            issue_candidates: List of (issue_id, series_run_id, issue_number, series_title, cover_date, publisher)
            normalized_publisher: Normalized publisher name
            normalized_series_title: Normalized series title
            normalized_issue_number: Normalized issue number
            year: Year for confirmation bonus

        Returns:
            CatalogMatchResult with best match and scoring details
        """
        best_score = 0
        best_candidate = None

        for (
            issue_id,
            series_run_id,
            issue_number,
            series_title,
            cover_date,
            publisher,
        ) in issue_candidates:
            # Score publisher match (30 points)
            publisher_score = self._score_publisher_match(
                publisher, normalized_publisher
            )

            # Score series match (40 points)
            series_score = self._score_series_match(
                series_title, normalized_series_title
            )

            # Score issue match (30 points)
            issue_score = self._score_issue_match(issue_number, normalized_issue_number)

            # Calculate base score
            total_score = publisher_score + series_score + issue_score

            # Add year confirmation bonus (10 points)
            year_bonus = 0
            year_confirmed = False
            if year and cover_date:
                if self._year_matches(year, cover_date):
                    year_bonus = 10
                    year_confirmed = True
                    total_score += year_bonus

            # Check if this is the best candidate
            if total_score > best_score:
                best_score = total_score
                best_candidate = (
                    issue_id,
                    series_run_id,
                    publisher,
                    series_title,
                    issue_number,
                    cover_date,
                    publisher_score,
                    series_score,
                    issue_score,
                    year_bonus,
                    year_confirmed,
                )

        if best_candidate is None:
            # Should not happen, but handle gracefully
            return self._no_match_result(
                normalized_publisher,
                normalized_series_title,
                normalized_issue_number,
                year,
            )

        (
            issue_id,
            series_run_id,
            publisher,
            series_title,
            issue_number,
            cover_date,
            publisher_score,
            series_score,
            issue_score,
            year_bonus,
            year_confirmed,
        ) = best_candidate

        # Build explanation
        explanation_parts = []
        if publisher_score >= 30:
            explanation_parts.append(f"Publisher '{publisher}' matched exactly")
        if series_score >= 35:
            explanation_parts.append(f"Series '{series_title}' matched")
        if issue_score >= 25:
            explanation_parts.append(f"Issue #{issue_number} matched")
        if year_bonus > 0 and cover_date:
            explanation_parts.append(
                f"Year {year} confirmed (cover date {cover_date.year})"
            )

        match_explanation = "; ".join(explanation_parts)

        return CatalogMatchResult(
            issue_id=issue_id,
            series_run_id=series_run_id,
            publisher=publisher,
            series_title=series_title,
            issue_number=issue_number,
            year=year,
            confidence_score=best_score,
            match_explanation=match_explanation,
            found_via="catalog",
            year_confirmed=year_confirmed,
            publisher_score=publisher_score,
            series_score=series_score,
            issue_score=issue_score,
            year_bonus=year_bonus,
        )

    def _score_publisher_match(self, publisher: str, normalized_publisher: str) -> int:
        """Score publisher match.

        Exact match: 30 points
        No match: 0 points

        Args:
            publisher: Publisher name from database
            normalized_publisher: Normalized publisher name from input

        Returns:
            Score (0-30)
        """
        if self._publishers_match(publisher, normalized_publisher):
            return 30
        return 0

    def _score_series_match(
        self, series_title: str, normalized_series_title: str
    ) -> int:
        """Score series match.

        Exact match: 30 points
        Normalized match: 25 points
        No match: 0 points

        Args:
            series_title: Series title from database
            normalized_series_title: Normalized series title from input

        Returns:
            Score (0-30)
        """
        if self._series_titles_match_exact(series_title, normalized_series_title):
            return 30
        if self._series_titles_match_normalized(series_title, normalized_series_title):
            return 25
        return 0

    def _score_issue_match(
        self, issue_number: str, normalized_issue_number: str
    ) -> int:
        """Score issue match.

        Exact match: 30 points
        Normalized match: 25 points
        No match: 0 points

        Args:
            issue_number: Issue number from database
            normalized_issue_number: Normalized issue number from input

        Returns:
            Score (0-30)
        """
        if self._issue_numbers_match_exact(issue_number, normalized_issue_number):
            return 30
        if self._issue_numbers_match_normalized(issue_number, normalized_issue_number):
            return 25
        return 0

    def _no_match_result(
        self,
        publisher: str,
        series_title: str,
        issue_number: str,
        year: Optional[int],
    ) -> CatalogMatchResult:
        """Return a no-match result.

        Args:
            publisher: Publisher name
            series_title: Series title
            issue_number: Issue number
            year: Year

        Returns:
            CatalogMatchResult with zero confidence
        """
        return CatalogMatchResult(
            issue_id=None,
            series_run_id=None,
            publisher=publisher,
            series_title=series_title,
            issue_number=issue_number,
            year=year,
            confidence_score=0,
            match_explanation="No match found in catalog",
            found_via="none",
        )

    # Normalization methods

    def _normalize_publisher(self, publisher: str) -> str:
        """Normalize publisher name for matching.

        Args:
            publisher: Raw publisher name

        Returns:
            Normalized publisher name
        """
        # Common publisher aliases
        publisher_aliases = {
            "marvel": "Marvel",
            "marvel comics": "Marvel",
            "dc": "DC Comics",
            "dc comics": "DC Comics",
            "image": "Image Comics",
            "image comics": "Image Comics",
            "dark horse": "Dark Horse Comics",
            "dark horse comics": "Dark Horse Comics",
            "idw": "IDW Publishing",
            "idw publishing": "IDW Publishing",
        }

        normalized = publisher.strip().lower()
        return publisher_aliases.get(normalized, publisher.strip())

    def _normalize_series_title(self, series_title: str) -> str:
        """Normalize series title for matching.

        Args:
            series_title: Raw series title

        Returns:
            Normalized series title
        """
        # Remove leading/trailing whitespace
        normalized = series_title.strip()

        # Remove common prefixes/suffixes
        normalized = re.sub(r"^(the|a|an)\s+", "", normalized, flags=re.IGNORECASE)

        # Convert to lowercase for case-insensitive comparison
        normalized = normalized.lower()

        # Remove special characters
        normalized = re.sub(r"[^\w\s]", "", normalized)

        # Collapse multiple spaces
        normalized = re.sub(r"\s+", " ", normalized)

        return normalized.strip()

    def _normalize_issue_number(self, issue_number: str) -> str:
        """Normalize issue number for matching.

        Args:
            issue_number: Raw issue number

        Returns:
            Normalized issue number
        """
        # Remove leading/trailing whitespace
        normalized = issue_number.strip()

        # Convert to lowercase
        normalized = normalized.lower()

        # Remove spaces around special characters
        normalized = re.sub(r"\s*([½/°])\s*", r"\1", normalized)

        return normalized

    # Matching methods

    def _publishers_match(self, publisher1: str, publisher2: str) -> bool:
        """Check if two publisher names match.

        Args:
            publisher1: First publisher name
            publisher2: Second publisher name

        Returns:
            True if publishers match
        """
        norm1 = self._normalize_publisher(publisher1).lower()
        norm2 = self._normalize_publisher(publisher2).lower()
        return norm1 == norm2

    def _series_titles_match_exact(self, title1: str, title2: str) -> bool:
        """Check if two series titles match exactly.

        Args:
            title1: First series title
            title2: Second series title

        Returns:
            True if titles match exactly
        """
        norm1 = self._normalize_series_title(title1)
        norm2 = self._normalize_series_title(title2)
        return norm1 == norm2

    def _series_titles_match_normalized(self, title1: str, title2: str) -> bool:
        """Check if two series titles match with fuzzy normalization.

        Args:
            title1: First series title
            title2: Second series title

        Returns:
            True if titles match with fuzzy normalization
        """
        # Remove volume numbers for comparison
        norm1 = re.sub(r"\bvol\.?\s*\d+", "", title1, flags=re.IGNORECASE)
        norm2 = re.sub(r"\bvol\.?\s*\d+", "", title2, flags=re.IGNORECASE)

        norm1 = self._normalize_series_title(norm1)
        norm2 = self._normalize_series_title(norm2)

        return norm1 == norm2

    def _issue_numbers_match_exact(self, number1: str, number2: str) -> bool:
        """Check if two issue numbers match exactly.

        Args:
            number1: First issue number
            number2: Second issue number

        Returns:
            True if issue numbers match exactly
        """
        norm1 = self._normalize_issue_number(number1)
        norm2 = self._normalize_issue_number(number2)
        return norm1 == norm2

    def _issue_numbers_match_normalized(self, number1: str, number2: str) -> bool:
        """Check if two issue numbers match with normalization.

        Args:
            number1: First issue number
            number2: Second issue number

        Returns:
            True if issue numbers match with normalization
        """
        # Handle special cases
        special_cases = {
            "-1": ["−1", "negative 1", "neg. 1"],
            "½": ["0.5", "1/2"],
            "¼": ["0.25"],
            "0": ["#0", "no. 0"],
        }

        norm1 = self._normalize_issue_number(number1)
        norm2 = self._normalize_issue_number(number2)

        # Check special cases
        for key, aliases in special_cases.items():
            if norm1 in [key] + aliases and norm2 in [key] + aliases:
                return True

        # Fallback to exact normalized match
        return norm1 == norm2

    def _year_matches(self, input_year: int, cover_date: datetime) -> bool:
        """Check if input year matches issue cover date.

        Args:
            input_year: Year from input
            cover_date: Issue cover date from database

        Returns:
            True if year matches (within 1 year tolerance)
        """
        # Allow 1 year tolerance for publication delays
        return abs(input_year - cover_date.year) <= 1
