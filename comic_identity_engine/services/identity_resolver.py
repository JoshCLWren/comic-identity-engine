"""Identity resolution service for cross-platform comic matching.

This module provides the core identity resolution logic that matches comic
issues across different platforms using a deterministic algorithm with
confidence scoring.

USAGE:
    from comic_identity_engine.services import IdentityResolver

    resolver = IdentityResolver(session)
    result = await resolver.resolve_issue(parsed_url)

ALGORITHM PRIORITY:
1. UPC exact match → 1.00 confidence
2. Series + issue + year → 0.95 confidence
3. Series + issue (no year) → 0.85 confidence
4. Fuzzy title similarity (Jaro-Winkler) → 0.70 confidence
5. No match → create new when source metadata is complete
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Dict, Optional, Protocol

import structlog
from longbox_matcher import jaro_winkler_similarity
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from comic_identity_engine.database.repositories import (
    ExternalMappingRepository,
    IssueRepository,
    SeriesRunRepository,
    VariantRepository,
)
from comic_identity_engine.errors import (
    DuplicateEntityError,
    RepositoryError,
    ResolutionError,
    ValidationError,
)

if TYPE_CHECKING:
    from comic_identity_engine.database.models import Issue
    from comic_identity_engine.services.url_parser import ParsedUrl
    from longbox_scrapers.models import Comic, ComicListing, SearchResult


class ScraperProtocol(Protocol):
    """Protocol for scrapers that can search comics."""

    async def search_comic(self, comic: Comic, /) -> SearchResult:
        """Search for a comic and return results."""
        ...


logger = structlog.get_logger(__name__)

PLACEHOLDER_SERIES_TITLES = {
    "unknown series",
}


@dataclass
class MatchCandidate:
    """Potential match candidate with scoring.

    Attributes:
        issue_id: Canonical issue UUID (None for fuzzy matches without issue number)
        series_run_id: Parent series run UUID
        issue_number: Issue number
        series_title: Series title
        series_start_year: Series start year
        match_reason: Why this candidate matched
        issue_confidence: Confidence score for issue match (0.0-1.0)
        variant_confidence: Confidence score for variant match (0.0-1.0)
        overall_confidence: Combined confidence score (0.0-1.0)
    """

    issue_id: Optional[uuid.UUID]
    series_run_id: uuid.UUID
    issue_number: str
    series_title: str
    series_start_year: int
    match_reason: str
    issue_confidence: float
    variant_confidence: float = 1.0
    overall_confidence: float = field(init=False)

    def __post_init__(self) -> None:
        """Calculate overall confidence from issue and variant confidence."""
        self.overall_confidence = self.issue_confidence * self.variant_confidence


@dataclass
class ResolutionResult:
    """Result of identity resolution.

    Attributes:
        issue_id: Resolved canonical issue UUID
        matches: List of all match candidates considered
        best_match: Best match candidate (if any)
        created_new: True if a new issue was created
        explanation: Human-readable explanation of resolution
    """

    issue_id: Optional[uuid.UUID]
    matches: list[MatchCandidate] = field(default_factory=list)
    best_match: Optional[MatchCandidate] = None
    created_new: bool = False
    explanation: str = ""


class IdentityResolver:
    """Cross-platform identity resolution for comic issues.

    This service implements deterministic matching algorithms with
    confidence scoring to resolve comic identities across platforms.

    Attributes:
        session: Async database session
        issue_repo: Issue repository
        series_repo: Series run repository
        mapping_repo: External mapping repository
        variant_repo: Variant repository
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize identity resolver.

        Args:
            session: Async database session
        """
        self.session = session
        self.issue_repo = IssueRepository(session)
        self.series_repo = SeriesRunRepository(session)
        self.mapping_repo = ExternalMappingRepository(session)
        self.variant_repo = VariantRepository(session)

    async def resolve_issue(
        self,
        parsed_url: "ParsedUrl",
        upc: Optional[str] = None,
        series_title: Optional[str] = None,
        series_start_year: Optional[int] = None,
        issue_number: Optional[str] = None,
        cover_date: Optional[date] = None,
        variant_suffix: Optional[str] = None,
        variant_name: Optional[str] = None,
    ) -> ResolutionResult:
        """Resolve comic issue identity from parsed URL and metadata.

        Args:
            parsed_url: Parsed URL data
            upc: Optional UPC for exact matching
            series_title: Optional series title for fuzzy matching
            series_start_year: Optional series start year
            issue_number: Optional issue number
            cover_date: Optional cover date
            variant_suffix: Optional variant suffix
            variant_name: Optional human-readable variant name

        Returns:
            ResolutionResult with match details

        Raises:
            ResolutionError: If repository access or matching fails unexpectedly
            ValidationError: If the source metadata is too weak or ambiguous to
                create a canonical issue safely
        """
        logger.info(
            "Starting identity resolution",
            platform=parsed_url.platform,
            source_issue_id=parsed_url.source_issue_id,
        )

        normalized_variant_suffix = self._normalize_optional_text(variant_suffix)
        normalized_variant_name = self._normalize_optional_text(variant_name)
        candidates: list[MatchCandidate] = []

        try:
            existing = await self.mapping_repo.find_by_source(
                parsed_url.platform,
                parsed_url.source_issue_id,
            )
            if existing:
                logger.info(
                    "Reconciliation attempt: existing mapping",
                    issue_id=str(existing.issue_id),
                    platform=parsed_url.platform,
                    source_issue_id=parsed_url.source_issue_id,
                    confidence=1.0,
                    attempt="existing_mapping",
                )
                issue = await self.issue_repo.find_by_id(existing.issue_id)
                if issue:
                    return ResolutionResult(
                        issue_id=issue.id,
                        best_match=MatchCandidate(
                            issue_id=issue.id,
                            series_run_id=issue.series_run_id,
                            issue_number=issue.issue_number,
                            series_title=issue.series_run.title,
                            series_start_year=issue.series_run.start_year,
                            match_reason="Existing external mapping",
                            issue_confidence=1.0,
                            variant_confidence=1.0,
                        ),
                        explanation=f"Found existing external mapping for {parsed_url.platform}:{parsed_url.source_issue_id}",
                    )

            if upc:
                logger.info(
                    "Reconciliation attempt: UPC match",
                    upc=upc,
                    attempt="upc_match",
                )
                upc_match = await self._match_by_upc(upc)
                if upc_match:
                    logger.info(
                        "UPC match successful",
                        confidence=upc_match.overall_confidence,
                    )
                    candidates.append(upc_match)
                else:
                    logger.info("UPC match failed, no match found")

            if series_title and issue_number:
                if series_start_year:
                    logger.info(
                        "Reconciliation attempt: series + issue + year",
                        series_title=series_title,
                        issue_number=issue_number,
                        series_start_year=series_start_year,
                        attempt="series_issue_year",
                    )
                    exact_match = await self._match_by_series_issue_year(
                        series_title,
                        issue_number,
                        series_start_year,
                    )
                    if exact_match:
                        logger.info(
                            "Series + issue + year match successful",
                            confidence=exact_match.overall_confidence,
                        )
                        candidates.append(exact_match)
                    else:
                        logger.info(
                            "Series + issue + year match failed, falling back to series + issue"
                        )
                        series_match = await self._match_by_series_issue(
                            series_title,
                            issue_number,
                        )
                        if series_match:
                            logger.info(
                                "Fallback series + issue match successful",
                                confidence=series_match.overall_confidence,
                            )
                            candidates.append(series_match)
                        else:
                            logger.info("Fallback series + issue match failed")
                else:
                    logger.info(
                        "Reconciliation attempt: series + issue (no year)",
                        series_title=series_title,
                        issue_number=issue_number,
                        attempt="series_issue",
                    )
                    series_match = await self._match_by_series_issue(
                        series_title,
                        issue_number,
                    )
                    if series_match:
                        logger.info(
                            "Series + issue match successful",
                            confidence=series_match.overall_confidence,
                        )
                        candidates.append(series_match)
                    else:
                        logger.info("Series + issue match failed")

            if series_title and not candidates:
                logger.info(
                    "Reconciliation attempt: fuzzy title match",
                    series_title=series_title,
                    has_issue_number=issue_number is not None,
                    attempt="fuzzy_title",
                )
                fuzzy_matches = await self._match_by_fuzzy_title(
                    series_title,
                    issue_number,
                )
                if fuzzy_matches:
                    logger.info(
                        "Fuzzy title match successful",
                        num_candidates=len(fuzzy_matches),
                        confidences=[m.overall_confidence for m in fuzzy_matches],
                    )
                    candidates.extend(fuzzy_matches)
                else:
                    logger.info(
                        "Fuzzy title match failed, no candidates above threshold"
                    )

            if candidates:
                valid_issue_matches = [c for c in candidates if c.issue_id is not None]
                if valid_issue_matches:
                    best = max(valid_issue_matches, key=lambda c: c.overall_confidence)
                    variant_note = await self._handle_variant_conflict(
                        issue_id=best.issue_id,
                        incoming_upc=upc,
                        variant_suffix=normalized_variant_suffix,
                        variant_name=normalized_variant_name,
                        cover_date=cover_date,
                    )
                    logger.info(
                        "Found valid issue match",
                        num_candidates=len(candidates),
                        num_valid_matches=len(valid_issue_matches),
                        best_confidence=best.overall_confidence,
                        best_reason=best.match_reason,
                    )

                    return ResolutionResult(
                        issue_id=best.issue_id,
                        matches=candidates,
                        best_match=best,
                        explanation=(
                            f"Matched by {best.match_reason} "
                            f"(confidence: {best.overall_confidence:.2f})"
                            f"{variant_note}"
                        ),
                    )
                else:
                    logger.info(
                        "No valid issue matches found (only series-only fuzzy candidates)",
                        num_series_only=len(candidates),
                    )

            logger.info("No matches found, creating new issue")
            (
                creation_series_title,
                creation_series_start_year,
                creation_issue_number,
            ) = self._validate_creation_inputs(
                series_title=series_title,
                series_start_year=series_start_year,
                issue_number=issue_number,
                cover_date=cover_date,
            )
            created = await self._create_new_issue(
                creation_series_title,
                creation_series_start_year,
                creation_issue_number,
                cover_date,
                upc,
            )

            if normalized_variant_suffix:
                variant_note = await self._ensure_variant(
                    issue_id=created.id,
                    variant_suffix=normalized_variant_suffix,
                    variant_name=normalized_variant_name,
                )
            else:
                variant_note = ""

            return ResolutionResult(
                issue_id=created.id,
                created_new=True,
                explanation=(
                    f"Created new issue for {parsed_url.platform}:"
                    f"{parsed_url.source_issue_id}{variant_note}"
                ),
            )

        except ValidationError:
            raise

        except (RepositoryError, SQLAlchemyError, ResolutionError) as e:
            logger.error(
                "Identity resolution failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise ResolutionError(
                f"Failed to resolve issue: {e}",
                original_error=e,
            ) from e

    async def _match_by_upc(self, upc: str) -> Optional[MatchCandidate]:
        """Match issue by exact UPC.

        Args:
            upc: Universal Product Code

        Returns:
            MatchCandidate with 1.00 confidence if found, None otherwise
        """
        issue = await self.issue_repo.find_by_upc(upc)
        if not issue:
            return None

        return MatchCandidate(
            issue_id=issue.id,
            series_run_id=issue.series_run_id,
            issue_number=issue.issue_number,
            series_title=issue.series_run.title,
            series_start_year=issue.series_run.start_year,
            match_reason=f"UPC exact match: {upc}",
            issue_confidence=1.0,
            variant_confidence=1.0,
        )

    async def _match_by_series_issue_year(
        self,
        series_title: str,
        issue_number: str,
        series_start_year: int,
    ) -> Optional[MatchCandidate]:
        """Match issue by series title, issue number, and year.

        Args:
            series_title: Series title
            issue_number: Issue number
            series_start_year: Series start year

        Returns:
            MatchCandidate with 0.95 confidence if found, None otherwise
        """
        series = await self.series_repo.find_by_title(series_title, series_start_year)
        if not series:
            return None

        issue = await self.issue_repo.find_by_number(series.id, issue_number)
        if not issue:
            return None

        return MatchCandidate(
            issue_id=issue.id,
            series_run_id=issue.series_run_id,
            issue_number=issue.issue_number,
            series_title=issue.series_run.title,
            series_start_year=issue.series_run.start_year,
            match_reason=f"Series + issue + year match: {series_title} ({series_start_year}) #{issue_number}",
            issue_confidence=0.95,
            variant_confidence=1.0,
        )

    async def _match_by_series_issue(
        self,
        series_title: str,
        issue_number: str,
    ) -> Optional[MatchCandidate]:
        """Match issue by series title and issue number (no year).

        Args:
            series_title: Series title
            issue_number: Issue number

        Returns:
            MatchCandidate with 0.85 confidence if found, None otherwise
        """
        series = await self.series_repo.find_by_title(series_title)
        if not series:
            return None

        issue = await self.issue_repo.find_by_number(series.id, issue_number)
        if not issue:
            return None

        return MatchCandidate(
            issue_id=issue.id,
            series_run_id=issue.series_run_id,
            issue_number=issue.issue_number,
            series_title=issue.series_run.title,
            series_start_year=issue.series_run.start_year,
            match_reason=f"Series + issue match: {series_title} #{issue_number}",
            issue_confidence=0.85,
            variant_confidence=1.0,
        )

    async def _match_by_fuzzy_title(
        self,
        series_title: str,
        issue_number: Optional[str] = None,
    ) -> list[MatchCandidate]:
        """Match issue by fuzzy title similarity using Jaro-Winkler.

        Args:
            series_title: Series title
            issue_number: Optional issue number for additional filtering

        Returns:
            List of MatchCandidate with 0.70 confidence (best matches first)
        """
        from sqlalchemy import select

        from comic_identity_engine.database.models import SeriesRun

        stmt = select(SeriesRun).limit(100)
        result = await self.session.execute(stmt)
        all_series = result.scalars().all()

        matches = []
        for series in all_series:
            similarity = jaro_winkler_similarity(
                series_title.lower(),
                series.title.lower(),
            )
            if similarity >= 0.85:
                if issue_number:
                    issue = await self.issue_repo.find_by_number(
                        series.id, issue_number
                    )
                    if issue:
                        matches.append(
                            MatchCandidate(
                                issue_id=issue.id,
                                series_run_id=issue.series_run_id,
                                issue_number=issue.issue_number,
                                series_title=issue.series_run.title,
                                series_start_year=issue.series_run.start_year,
                                match_reason=f"Fuzzy title match: {series.title} (similarity: {similarity:.2f})",
                                issue_confidence=0.70 * similarity,
                                variant_confidence=1.0,
                            )
                        )
                else:
                    matches.append(
                        MatchCandidate(
                            issue_id=None,
                            series_run_id=series.id,
                            issue_number="",
                            series_title=series.title,
                            series_start_year=series.start_year,
                            match_reason=f"Fuzzy title match: {series.title} (similarity: {similarity:.2f})",
                            issue_confidence=0.70 * similarity,
                            variant_confidence=1.0,
                        )
                    )

        return sorted(matches, key=lambda m: m.issue_confidence, reverse=True)[:5]

    async def _create_new_issue(
        self,
        series_title: str,
        series_start_year: int,
        issue_number: str,
        cover_date: Optional[date] = None,
        upc: Optional[str] = None,
    ) -> "Issue":
        """Create a new issue when no match is found.

        Args:
            series_title: Series title
            series_start_year: Series start year
            issue_number: Issue number
            cover_date: Optional cover date
            upc: Optional UPC

        Returns:
            Created Issue entity
        """
        series = await self.series_repo.find_by_title(series_title, series_start_year)
        if not series:
            try:
                series = await self.series_repo.create(series_title, series_start_year)
            except DuplicateEntityError as e:
                series = await self.series_repo.find_by_title(
                    series_title,
                    series_start_year,
                )
                if series is None:
                    raise ResolutionError(
                        "Series creation raced with another worker, "
                        f"but the winner could not be refetched for {series_title} "
                        f"({series_start_year})",
                        original_error=e,
                    ) from e

                logger.info(
                    "Reused canonical series created by concurrent worker",
                    series_id=str(series.id),
                    series_title=series_title,
                    series_start_year=series_start_year,
                )

        issue = await self.issue_repo.find_by_number(series.id, issue_number)
        if issue:
            logger.info(
                "Reused canonical issue created by concurrent worker",
                issue_id=str(issue.id),
                series_id=str(series.id),
                issue_number=issue_number,
            )
            return issue

        try:
            issue = await self.issue_repo.create(
                series_run_id=series.id,
                issue_number=issue_number,
                cover_date=datetime(cover_date.year, cover_date.month, cover_date.day)
                if cover_date
                else None,
                upc=upc,
            )
        except DuplicateEntityError as e:
            issue = await self.issue_repo.find_by_number(series.id, issue_number)
            if issue is None:
                raise ResolutionError(
                    "Issue creation raced with another worker, "
                    f"but the winner could not be refetched for {series_title} "
                    f"#{issue_number}",
                    original_error=e,
                ) from e

            logger.info(
                "Reused canonical issue after duplicate create",
                issue_id=str(issue.id),
                series_id=str(series.id),
                issue_number=issue_number,
            )

        logger.info(
            "Created new issue",
            issue_id=str(issue.id),
            series_title=series_title,
            issue_number=issue_number,
        )

        return issue

    def _validate_creation_inputs(
        self,
        *,
        series_title: Optional[str],
        series_start_year: Optional[int],
        issue_number: Optional[str],
        cover_date: Optional[date] = None,
    ) -> tuple[str, int, str]:
        """Reject placeholder metadata before creating a canonical issue."""
        normalized_title = re.sub(r"\s+", " ", (series_title or "")).strip()
        normalized_issue_number = (issue_number or "").strip()

        if (
            not normalized_title
            or normalized_title.lower() in PLACEHOLDER_SERIES_TITLES
        ):
            raise ValidationError(
                "Cannot create a canonical issue from placeholder series metadata; "
                "manual review is required"
            )
        if series_start_year is None:
            if cover_date:
                series_start_year = cover_date.year
                logger.info(
                    "Using cover date year as series start year fallback",
                    fallback_year=series_start_year,
                )
            else:
                raise ValidationError(
                    "Cannot create a canonical issue without a source series start year; "
                    "manual review is required"
                )
        if not normalized_issue_number:
            raise ValidationError(
                "Cannot create a canonical issue without an issue number; "
                "manual review is required"
            )

        return normalized_title, series_start_year, normalized_issue_number

    def _normalize_optional_text(self, value: object) -> Optional[str]:
        """Normalize optional text inputs and ignore mock placeholders."""
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized or None

    async def _handle_variant_conflict(
        self,
        *,
        issue_id: Optional[uuid.UUID],
        incoming_upc: Optional[str],
        variant_suffix: Optional[str],
        variant_name: Optional[str],
        cover_date: Optional[date] = None,
    ) -> str:
        """Reject ambiguous duplicate issues or capture them as variants."""
        if issue_id is None or not incoming_upc:
            return ""

        matched_issue = await self.issue_repo.find_with_variants(issue_id)
        if (
            matched_issue is None
            or not matched_issue.upc
            or matched_issue.upc == incoming_upc
        ):
            return ""

        if not variant_suffix:
            # If we have a cover date, derive a printing suffix from it
            # (e.g., "2006-10" for an Oct 2006 printing) so the row is
            # accepted as a variant instead of rejected outright.
            if cover_date:
                variant_suffix = cover_date.strftime("%Y-%m")
            else:
                raise ValidationError(
                    "Matched canonical issue has a different UPC and no variant suffix "
                    "was provided; reject this row for review instead of merging it "
                    "into the base issue"
                )

        return await self._ensure_variant(
            issue_id=matched_issue.id,
            variant_suffix=variant_suffix,
            variant_name=variant_name,
        )

    async def _ensure_variant(
        self,
        *,
        issue_id: uuid.UUID,
        variant_suffix: str,
        variant_name: Optional[str],
    ) -> str:
        """Create or reuse a variant marker on the canonical issue."""
        existing_variant = await self.variant_repo.find_by_issue_and_suffix(
            issue_id,
            variant_suffix,
        )
        if existing_variant is None:
            try:
                await self.variant_repo.create(
                    issue_id=issue_id,
                    variant_suffix=variant_suffix,
                    variant_name=variant_name,
                )
            except DuplicateEntityError:
                logger.info(
                    "Reused canonical variant created by concurrent worker",
                    issue_id=str(issue_id),
                    variant_suffix=variant_suffix,
                )
        elif existing_variant.variant_name is None and variant_name:
            existing_variant.variant_name = variant_name

        return f"; variant {variant_suffix} recorded on canonical issue"

    async def search_cross_platform(
        self,
        issue_id: uuid.UUID,
        series_title: str,
        issue_number: str,
        year: Optional[int] = None,
        publisher: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search for this issue on ALL platforms and create external mappings.

        Searches ALL supported platforms (gcd, locg, aa, ccl, cpg, hip).
        For each platform, returns status indicating whether the platform
        was found, failed, or not found.

        Args:
            issue_id: Canonical issue UUID
            series_title: Series title
            issue_number: Issue number
            year: Optional publication year (helps with filtering)
            publisher: Optional publisher name (helps with filtering)

        Returns:
            Dictionary with:
            - urls: Dictionary mapping platform code to URL for all found platforms
            - status: Dictionary mapping platform code to search status
              (searching/found/failed/not_found)

        Raises:
            ResolutionError: If cross-platform search fails
        """
        logger.info(
            "Starting cross-platform search",
            issue_id=str(issue_id),
            series_title=series_title,
            issue_number=issue_number,
            year=year,
        )

        all_platforms = ["gcd", "locg", "aa", "ccl", "cpg", "hip"]

        found_urls = {}
        platform_status: Dict[str, str] = {}

        for platform in all_platforms:
            platform_status[platform] = "searching"

        for platform in all_platforms:
            try:
                platform_url = await self._search_single_platform(
                    platform,
                    issue_id,
                    series_title,
                    issue_number,
                    year,
                    publisher,
                )
                if platform_url:
                    found_urls[platform] = platform_url
                    platform_status[platform] = "found"
                    logger.info(
                        "Found platform URL",
                        platform=platform,
                        url=platform_url,
                    )
                else:
                    platform_status[platform] = "not_found"
                    logger.info(
                        "Platform search returned no results",
                        platform=platform,
                    )
            except Exception as e:
                platform_status[platform] = "failed"
                logger.warning(
                    "Platform search failed",
                    platform=platform,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                continue

        logger.info(
            "Cross-platform search completed",
            issue_id=str(issue_id),
            found_platforms=list(found_urls.keys()),
            status_by_platform=platform_status,
        )

        return {
            "urls": found_urls,
            "status": platform_status,
        }

    async def _search_single_platform(
        self,
        platform: str,
        issue_id: uuid.UUID,
        series_title: str,
        issue_number: str,
        year: Optional[int],
        publisher: Optional[str],
    ) -> Optional[str]:
        """Search a single platform and create external mapping if found.

        Args:
            platform: Platform code (aa, ccl, hip)
            issue_id: Canonical issue UUID
            series_title: Series title
            issue_number: Issue number
            year: Optional publication year
            publisher: Optional publisher name

        Returns:
            Platform URL if found and mapped, None otherwise
        """
        scraper = None
        try:
            scraper = self._get_scraper(platform)
            if not scraper:
                logger.debug("No scraper available", platform=platform)
                return None

            from longbox_scrapers.models import Comic

            comic = Comic(
                id=f"{platform}:{series_title}:{issue_number}",
                title=series_title,
                issue=issue_number,
                year=year,
                publisher=publisher,
            )
            search_result = await scraper.search_comic(comic)

            if not search_result or not search_result.has_results:
                logger.debug(
                    "No search results",
                    platform=platform,
                    series_title=series_title,
                    issue_number=issue_number,
                )
                return None

            best_listing = self._select_best_listing(search_result, issue_number)
            if not best_listing:
                logger.debug("No suitable listing found", platform=platform)
                return None

            source_issue_id, source_series_id = self._extract_ids_from_url(
                platform, best_listing.url or ""
            )

            if source_issue_id:
                try:
                    await self.mapping_repo.create_mapping(
                        issue_id=issue_id,
                        source=platform,
                        source_issue_id=source_issue_id,
                        source_series_id=source_series_id,
                    )
                    logger.info(
                        "Created external mapping from search",
                        platform=platform,
                        source_issue_id=source_issue_id,
                        source_series_id=source_series_id,
                    )
                except DuplicateEntityError:
                    # Mapping already exists - check if it's for the same issue
                    logger.debug(
                        "External mapping already exists, reusing it",
                        platform=platform,
                        source_issue_id=source_issue_id,
                    )
                    # The mapping exists, which is fine - continue to return the URL

                return best_listing.url

        except ImportError as e:
            logger.warning(
                "Scraper not available",
                platform=platform,
                error=str(e),
            )
            return None
        except Exception as e:
            logger.error(
                "Platform search failed",
                platform=platform,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    def _get_scraper(self, platform: str) -> Optional[ScraperProtocol]:
        """Get scraper instance for platform.

        Args:
            platform: Platform code (aa, ccl, hip, cpg, gcd, locg)

        Returns:
            Scraper instance or None if not available
        """
        try:
            if platform == "aa":
                from longbox_scrapers.adapters.atomic_avenue import AtomicAvenueScraper

                return AtomicAvenueScraper(timeout=30)
            elif platform == "ccl":
                from longbox_scrapers.adapters.ccl import CCLScraper

                return CCLScraper(timeout=30)
            elif platform == "hip":
                from longbox_scrapers.adapters.hip import HIPScraper

                return HIPScraper(timeout=30)
            elif platform == "cpg":
                from longbox_scrapers.adapters.cpg import CPGScraper

                return CPGScraper(timeout=30)
            elif platform == "gcd":
                from longbox_scrapers.adapters.gcd import GCDScraper

                return GCDScraper(timeout=30)
            elif platform == "locg":
                from longbox_scrapers.adapters.locg import LoCGScraper

                return LoCGScraper(timeout=30)
            else:
                return None
        except ImportError:
            logger.warning("Scraper package not installed", platform=platform)
            return None

    def _select_best_listing(
        self, search_result, issue_number: str
    ) -> ComicListing | None:
        """Select the best listing from search results.

        Args:
            search_result: SearchResult from scraper
            issue_number: Target issue number

        Returns:
            Best listing or None
        """
        if not search_result.listings:
            return None

        # First try to find a listing with a matching issue_number
        for listing in search_result.listings:
            if (
                listing.url
                and hasattr(listing, "issue_number")
                and listing.issue_number
            ):
                if str(listing.issue_number) == str(issue_number):
                    return listing

        # If no exact match found, return the first listing with a URL
        for listing in search_result.listings:
            if listing.url:
                return listing

        return None

    def _extract_ids_from_url(
        self, platform: str, url: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Extract source_issue_id and source_series_id from platform URL.

        Args:
            platform: Platform code
            url: Platform URL

        Returns:
            Tuple of (source_issue_id, source_series_id)
        """
        if not url:
            return None, None

        try:
            if platform == "aa":
                match = re.search(r"/item/(\d+)/", url)
                if match:
                    return match.group(1), None

            elif platform == "ccl":
                match = re.search(r"/issue/([a-f0-9-]+)/(\d+)", url)
                if match:
                    return match.group(2), match.group(1)

            elif platform == "hip":
                # Try price guide URL format first
                match = re.search(r"/price-guide/.*?/(\d+)/(\d+)/", url)
                if match:
                    return match.group(2), match.group(1)
                # Try listing URL format
                match = re.search(r"/listing/.*?/(\d+)", url)
                if match:
                    return match.group(1), None

            elif platform == "cpg":
                # CPG URL format: /titles/{series_slug}/{issue_number}/{resource_id}
                match = re.search(r"/titles/[^/]+/[^/]+/([^/]+)", url)
                if match:
                    return match.group(1), None

        except Exception as e:
            logger.warning(
                "Failed to extract IDs from URL",
                platform=platform,
                url=url,
                error=str(e),
            )

        return None, None
