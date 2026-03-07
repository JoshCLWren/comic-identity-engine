"""Platform searcher service for thorough cross-platform comic search.

This service implements exhaustive search across all comic platforms with:
- Multiple search strategies per platform
- Exponential backoff retries
- Real-time status updates
- Parallel execution for speed
- Platform-specific configurations

USAGE:
    searcher = PlatformSearcher(session)
    result = await searcher.search_all_platforms(
        issue_id=uuid.uuid4(),
        series_title="X-Men",
        issue_number="1",
        year=1963,
        publisher="Marvel",
        operation_id=operation_uuid,
        source_platform="gcd",
    )
    # result = {
    #     "urls": {"aa": "https://...", "ccl": "https://..."},
    #     "status": {"gcd": "found", "aa": "found", "ccl": "searching_retry_1", ...}
    # }
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

import jellyfish
import structlog

from comic_identity_engine.database.connection import AsyncSessionLocal
from comic_identity_engine.database.repositories import ExternalMappingRepository
from comic_identity_engine.errors import DuplicateEntityError
from comic_identity_engine.errors import NetworkError
from comic_identity_engine.services.operations import OperationsManager

logger = structlog.get_logger(__name__)


def _prefer_workspace_comic_search_lib() -> None:
    """Prefer the vendored comic-search-lib checkout over site-packages."""
    workspace_lib = Path(__file__).resolve().parents[2] / "comic-search-lib"
    if not workspace_lib.exists():
        return

    workspace_lib_str = str(workspace_lib)
    if workspace_lib_str in sys.path:
        sys.path.remove(workspace_lib_str)
    sys.path.insert(0, workspace_lib_str)


# Platform-specific search configurations
PLATFORM_SEARCH_CONFIG = {
    "gcd": {
        "max_retries": 2,
        "max_duration_sec": 12,
        "request_timeout_sec": 6,
        "strategies": ["exact", "no_year", "normalized_title"],
        "retry_delay_sec": 1,
        "notes": "Excellent search, authoritative source",
    },
    "locg": {
        "max_retries": 3,
        "max_duration_sec": 12,
        "request_timeout_sec": 6,
        "strategies": ["exact", "no_year", "normalized_title", "fuzzy_title"],
        "retry_delay_sec": 2,
        "notes": "Good search but rate limited - need backoff",
    },
    "aa": {
        "max_retries": 3,
        "max_duration_sec": 12,
        "request_timeout_sec": 6,
        "strategies": [
            "exact",
            "no_year",
            "normalized_title",
            "fuzzy_title",
            "simplified_tokens",
        ],
        "retry_delay_sec": 2,
        "notes": "Finicky HTML parsing, needs multiple strategies",
    },
    "ccl": {
        "max_retries": 3,
        "max_duration_sec": 12,
        "request_timeout_sec": 6,
        "strategies": [
            "exact",
            "no_year",
            "normalized_title",
            "fuzzy_title",
            "alt_issue_format",
        ],
        "retry_delay_sec": 2,
        "notes": "Requires session cookies, session issues common",
    },
    "cpg": {
        "max_retries": 2,
        "max_duration_sec": 8,
        "request_timeout_sec": 5,
        "strategies": ["exact", "no_year"],
        "retry_delay_sec": 1,
        "notes": "Poor search functionality, don't waste time",
    },
    "hip": {
        "max_retries": 2,
        "max_duration_sec": 12,
        "request_timeout_sec": 6,
        "strategies": ["exact", "no_year", "normalized_title", "fuzzy_title"],
        "retry_delay_sec": 2,
        "notes": "Occasional timeouts, needs retries",
    },
}


class PlatformSearcher:
    """Search all platforms thoroughly with multiple strategies and retries."""

    def __init__(self, session):
        """Initialize platform searcher.

        Args:
            session: Database session from the caller. Cross-platform search does
                not reuse it for progress writes or mapping inserts because each
                platform runner operates concurrently.
        """
        self.session = session
        self._progress_lock = asyncio.Lock()

        # Import scrapers here to avoid circular imports
        _prefer_workspace_comic_search_lib()
        from comic_search_lib.scrapers.atomic_avenue import AtomicAvenueScraper
        from comic_search_lib.scrapers.ccl import CCLScraper
        from comic_search_lib.scrapers.cpg import CPGScraper
        from comic_search_lib.scrapers.gcd import GCDScraper
        from comic_search_lib.scrapers.hip import HipScraper
        from comic_search_lib.scrapers.locg import LoCGScraper

        self.scrapers = {
            "gcd": GCDScraper(timeout=PLATFORM_SEARCH_CONFIG["gcd"]["request_timeout_sec"]),
            "locg": LoCGScraper(timeout=PLATFORM_SEARCH_CONFIG["locg"]["request_timeout_sec"]),
            "aa": AtomicAvenueScraper(timeout=PLATFORM_SEARCH_CONFIG["aa"]["request_timeout_sec"]),
            "ccl": CCLScraper(timeout=PLATFORM_SEARCH_CONFIG["ccl"]["request_timeout_sec"]),
            "cpg": CPGScraper(timeout=PLATFORM_SEARCH_CONFIG["cpg"]["request_timeout_sec"]),
            "hip": HipScraper(timeout=PLATFORM_SEARCH_CONFIG["hip"]["request_timeout_sec"]),
        }

    async def search_all_platforms(
        self,
        issue_id: UUID,
        series_title: str,
        issue_number: str,
        year: Optional[int],
        publisher: Optional[str],
        operation_id: UUID,
        source_platform: str,
        operations_manager: OperationsManager,
    ) -> dict[str, Any]:
        """Search all platforms in parallel with multiple strategies.

        Args:
            issue_id: Canonical issue UUID
            series_title: Series title
            issue_number: Issue number
            year: Publication year (optional)
            publisher: Publisher name (optional)
            operation_id: Operation UUID for status updates
            source_platform: Platform we started from (already mapped)
            operations_manager: OperationsManager for updating operation metadata

        Returns:
            Dict with:
                - urls: dict mapping platform -> URL (for found platforms)
                - status: dict mapping platform -> status string
        """
        all_platforms = ["gcd", "locg", "aa", "ccl", "cpg", "hip"]

        # Mark source platform as found immediately
        platform_status = {source_platform: "found"}

        # Create tasks for all other platforms
        tasks: list[asyncio.Task[tuple[str, Optional[str]]]] = []
        for platform in all_platforms:
            if platform == source_platform:
                continue

            platform_status[platform] = "searching"
            task = asyncio.create_task(
                self._run_platform_search_task(
                    platform=platform,
                    issue_id=issue_id,
                    series_title=series_title,
                    issue_number=issue_number,
                    year=year,
                    publisher=publisher,
                    operation_id=operation_id,
                )
            )
            tasks.append(task)

        # Persist the initial snapshot before any platform finishes so the CLI can
        # show that the full parallel search fan-out has started.
        await self._persist_operation_progress(
            operation_id=operation_id,
            platform_status=dict(platform_status),
        )

        found_urls = {}
        for completed_task in asyncio.as_completed(tasks):
            try:
                platform, result = await completed_task
            except Exception as e:
                platform = getattr(e, "platform", "unknown")
                platform_status[platform] = "failed"
                logger.warning(
                    "Platform search failed",
                    platform=platform,
                    error=str(e),
                )
            else:
                if result:
                    found_urls[platform] = result
                    platform_status[platform] = "found"
                else:
                    platform_status[platform] = "not_found"

            # Update operation with current platform_status for real-time progress
            try:
                await self._persist_operation_progress(
                    operation_id=operation_id,
                    platform_status=dict(platform_status),
                )
            except Exception as e:
                logger.warning(
                    "Failed to update operation progress",
                    operation_id=str(operation_id),
                    platform=platform,
                    error=str(e),
                )

        return {
            "urls": found_urls,
            "status": platform_status,
        }

    async def _run_platform_search_task(
        self,
        platform: str,
        issue_id: UUID,
        series_title: str,
        issue_number: str,
        year: Optional[int],
        publisher: Optional[str],
        operation_id: UUID,
    ) -> tuple[str, Optional[str]]:
        """Return the platform alongside the search result for as_completed()."""
        result = await self._run_platform_search_with_timeout(
            platform=platform,
            issue_id=issue_id,
            series_title=series_title,
            issue_number=issue_number,
            year=year,
            publisher=publisher,
            operation_id=operation_id,
        )
        return platform, result

    async def _run_platform_search_with_timeout(
        self,
        platform: str,
        issue_id: UUID,
        series_title: str,
        issue_number: str,
        year: Optional[int],
        publisher: Optional[str],
        operation_id: UUID,
    ) -> Optional[str]:
        """Run a single platform search with a hard wall-clock timeout."""
        timeout_seconds = PLATFORM_SEARCH_CONFIG[platform]["max_duration_sec"]
        try:
            return await asyncio.wait_for(
                self._search_single_platform_with_strategies(
                    platform=platform,
                    issue_id=issue_id,
                    series_title=series_title,
                    issue_number=issue_number,
                    year=year,
                    publisher=publisher,
                    operation_id=operation_id,
                ),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Platform search hit hard timeout",
                platform=platform,
                duration_sec=timeout_seconds,
            )
            return None

    async def _search_single_platform_with_strategies(
        self,
        platform: str,
        issue_id: UUID,
        series_title: str,
        issue_number: str,
        year: Optional[int],
        publisher: Optional[str],
        operation_id: UUID,
    ) -> Optional[str]:
        """Search a single platform using multiple strategies with retries.

        Args:
            platform: Platform code (e.g., "gcd", "aa")
            issue_id: Canonical issue UUID
            series_title: Series title
            issue_number: Issue number
            year: Publication year (optional)
            publisher: Publisher name (optional)
            operation_id: Operation UUID for status updates

        Returns:
            Platform URL if found, None if all strategies exhausted
        """
        config = PLATFORM_SEARCH_CONFIG[platform]
        scraper = self.scrapers.get(platform)

        if not scraper:
            logger.warning("Scraper not available", platform=platform)
            return None

        start_time = time.time()

        # Try each strategy in order
        for strategy in config["strategies"]:
            # Update status to show current strategy
            status_key = f"searching_{strategy}" if strategy != "exact" else "searching"
            await self._update_platform_status(
                operation_id, platform, status_key, strategy=strategy, retry=1
            )

            # Retry with exponential backoff
            for attempt in range(config["max_retries"]):
                try:
                    # Check timeout
                    if time.time() - start_time > config["max_duration_sec"]:
                        logger.warning(
                            "Platform search timeout",
                            platform=platform,
                            duration_sec=config["max_duration_sec"],
                        )
                        return None

                    # Execute search with this strategy
                    result = await self._execute_strategy(
                        scraper=scraper,
                        strategy=strategy,
                        series_title=series_title,
                        issue_number=issue_number,
                        year=year,
                        publisher=publisher,
                    )

                    if result and result.has_results:
                        # FOUND! Create mapping immediately and return URL
                        url = await self._create_mapping_from_search_result(
                            platform=platform,
                            issue_id=issue_id,
                            result=result,
                        )
                        return url

                    # No results - retry if not last attempt
                    if attempt < config["max_retries"] - 1:
                        # Update status to show retry
                        await self._update_platform_status(
                            operation_id,
                            platform,
                            f"searching_retry_{attempt + 1}",
                            strategy=strategy,
                            retry=attempt + 2,
                        )
                        # Exponential backoff
                        await asyncio.sleep(config["retry_delay_sec"] * (2**attempt))

                except NetworkError as e:
                    if attempt < config["max_retries"] - 1:
                        await asyncio.sleep(config["retry_delay_sec"] * (2**attempt))
                    else:
                        logger.error(
                            "Platform search failed after retries",
                            platform=platform,
                            error=str(e),
                        )
                        raise
                except Exception as e:
                    logger.error(
                        "Strategy failed",
                        platform=platform,
                        strategy=strategy,
                        error=str(e),
                    )
                    # Try next strategy
                    break

        # All strategies exhausted
        return None

    async def _execute_strategy(
        self,
        scraper,
        strategy: str,
        series_title: str,
        issue_number: str,
        year: Optional[int],
        publisher: Optional[str],
    ) -> Optional[Any]:
        """Execute a single search strategy.

        Args:
            scraper: Platform scraper instance
            strategy: Strategy name (exact, no_year, normalized_title, etc.)
            series_title: Series title
            issue_number: Issue number
            year: Publication year (optional)
            publisher: Publisher name (optional)

        Returns:
            SearchResult if found, None otherwise
        """
        # Determine search params based on strategy
        search_title = series_title
        search_issue = issue_number
        search_year = year
        search_publisher = publisher

        if strategy == "no_year":
            search_year = None
        elif strategy == "normalized_title":
            search_title = self._normalize_series_name(series_title)
        elif strategy == "fuzzy_title":
            return await self._fuzzy_search(
                scraper=scraper,
                title=search_title,
                issue=search_issue,
                year=search_year,
                publisher=search_publisher,
            )
        elif strategy == "alt_issue_format":
            alt_formats = self._get_alternate_issue_formats(issue_number)
            for alt_issue in alt_formats:
                result = await self._call_scraper(
                    scraper=scraper,
                    title=search_title,
                    issue=alt_issue,
                    year=search_year,
                    publisher=search_publisher,
                )
                if result and result.has_results:
                    return result
            return None
        elif strategy == "simplified_tokens":
            tokens = self._tokenize(series_title)
            search_title = " ".join(tokens)
        elif strategy not in ("exact",):
            raise ValueError(f"Unknown strategy: {strategy}")

        return await self._call_scraper(
            scraper=scraper,
            title=search_title,
            issue=search_issue,
            year=search_year,
            publisher=search_publisher,
        )

    async def _fuzzy_search(
        self,
        scraper,
        title: str,
        issue: str,
        year: Optional[int],
        publisher: Optional[str],
    ) -> Optional[Any]:
        """Fuzzy search using Jaro-Winkler similarity.

        Args:
            scraper: Platform scraper
            title: Series title
            issue: Issue number
            year: Publication year
            publisher: Publisher name

        Returns:
            SearchResult with best match, None if no good match
        """
        # Get broad results (search without issue to get all issues in series)
        broad_result = await self._call_scraper(
            scraper=scraper,
            title=title,
            issue="",  # Empty string to get broader results
            year=year,
            publisher=publisher,
        )

        if not broad_result or not broad_result.listings:
            return None

        # Find best match using Jaro-Winkler
        from comic_search_lib.models import Comic, SearchResult

        normalized_issue = self._normalize_issue(issue)
        best_match = None
        best_score = 0.0

        for listing in broad_result.listings:
            # Extract issue from listing title or metadata
            listing_issue = issue
            if hasattr(listing, "title") and "#" in listing.title:
                listing_issue = listing.title.split("#")[-1].split()[0]

            listing_issue = self._normalize_issue(listing_issue)
            score = jellyfish.jaro_winkler_similarity(
                normalized_issue,
                listing_issue,
            )

            if score > best_score and score >= 0.85:
                best_match = listing
                best_score = score

        if best_match:
            # Create SearchResult with the best match
            comic = Comic(
                id="fuzzy-search",
                title=title,
                issue=issue,
                year=year,
                publisher=publisher,
            )
            return SearchResult(comic=comic, listings=[best_match], prices=[])

        return None

    async def _create_mapping_from_search_result(
        self,
        platform: str,
        issue_id: UUID,
        result,
    ) -> str:
        """Create external mapping from search result and return URL.

        Args:
            platform: Platform code
            issue_id: Canonical issue UUID
            result: SearchResult with listings

        Returns:
            Platform URL for the found issue
        """
        url = None
        if getattr(result, "listings", None):
            best_listing = result.listings[0]
            url = best_listing.url
        if not url:
            url = getattr(result, "url", None)
        if not url:
            raise ValueError(
                f"Search result for platform {platform} had no usable listing URL"
            )

        # Extract source IDs from URL
        source_issue_id, source_series_id = self._extract_ids_from_url(platform, url)

        async with AsyncSessionLocal() as session:
            mapping_repo = ExternalMappingRepository(session)
            existing = await mapping_repo.find_by_source(platform, source_issue_id)

            if existing is None:
                await mapping_repo.create_mapping(
                    issue_id=issue_id,
                    source=platform,
                    source_issue_id=source_issue_id,
                    source_series_id=source_series_id,
                )
                await session.commit()
            elif existing.issue_id == issue_id:
                logger.info(
                    "Reused existing external mapping from search result",
                    platform=platform,
                    issue_id=str(issue_id),
                    source_issue_id=source_issue_id,
                    url=url,
                )
            else:
                raise DuplicateEntityError(
                    f"External mapping with source={platform} and "
                    f"source_issue_id={source_issue_id} already exists",
                    entity_type="ExternalMapping",
                    existing_id=str(existing.id),
                )

        logger.info(
            "Created external mapping from search result",
            platform=platform,
            issue_id=str(issue_id),
            source_issue_id=source_issue_id,
            url=url,
        )

        return url

    def _extract_ids_from_url(
        self, platform: str, url: str
    ) -> tuple[str, Optional[str]]:
        """Extract source_issue_id and source_series_id from platform URL.

        Args:
            platform: Platform code
            url: Platform URL

        Returns:
            Tuple of (source_issue_id, source_series_id)
        """
        if platform == "aa":
            # /item/{source_issue_id}/1/details
            match = re.search(r"/item/(\d+)/", url)
            if match:
                return match.group(1), None

        elif platform == "ccl":
            # /issue/{source_series_id}/{source_issue_id}
            match = re.search(r"/issue/([^/]+)/([^/]+)", url)
            if match:
                return match.group(2), match.group(1)

        elif platform == "hip":
            # /comic/{source_series_id}/{source_issue_id}/
            match = re.search(r"/comic/([^/]+)/([^/]+)/", url)
            if match:
                return match.group(2), match.group(1)

        elif platform == "cpg":
            # /titles/{title}/{series_id}/{issue_id}
            match = re.search(r"/titles/([^/]+)/(\d+)/([^/]+)", url)
            if match:
                return match.group(3), match.group(2)

        elif platform == "gcd":
            # /issue/{source_issue_id}/
            match = re.search(r"/issue/(\d+)/", url)
            if match:
                return match.group(1), None

        elif platform == "locg":
            # /item/{source_issue_id}
            match = re.search(r"/item/([^/]+)", url)
            if match:
                return match.group(1), None

        # Fallback: extract last numeric part
        numbers = re.findall(r"\d+", url)
        if numbers:
            return numbers[-1], None

        raise ValueError(f"Could not extract IDs from URL: {url}")

    async def _call_scraper(
        self,
        scraper,
        title: str,
        issue: str,
        year: Optional[int],
        publisher: Optional[str],
    ) -> Optional[Any]:
        """Call scraper with correct arguments based on its signature.

        Args:
            scraper: Platform scraper instance
            title: Series title
            issue: Issue number
            year: Publication year (optional)
            publisher: Publisher name (optional)

        Returns:
            SearchResult if found, None otherwise
        """
        # Determine scraper type by class name
        scraper_class = scraper.__class__.__name__

        # Scrapers that accept Comic object or dict
        if scraper_class in ("LoCGScraper", "CCLScraper", "HipScraper"):
            comic_dict = {
                "title": title,
                "issue": issue,
                "year": year,
                "publisher": publisher,
            }
            return await scraper.search_comic(comic_dict)

        # Scrapers that accept individual parameters
        # GCDScraper, CPGScraper, AtomicAvenueScraper
        return await scraper.search_comic(
            title=title,
            issue=issue,
            year=year,
            publisher=publisher,
        )

    def _normalize_series_name(self, name: str) -> str:
        """Normalize series name for fuzzy matching.

        From IMPLEMENTATION_PLAN.md lines 576-594

        Args:
            name: Raw series name

        Returns:
            Normalized series name
        """
        name = name.lower().strip()
        name = re.sub(r"\s+", " ", name)  # Normalize whitespace
        name = re.sub(r"\(.*?\)", "", name)  # Remove parentheticals
        name = re.sub(r"vol\.?\s*\d+", "", name)  # Remove volume numbers
        name = name.strip()

        return name

    def _normalize_issue(self, issue: str) -> str:
        """Normalize issue number for comparison.

        Args:
            issue: Raw issue number

        Returns:
            Normalized issue number
        """
        return issue.lower().strip()

    def _tokenize(self, text: str) -> list[str]:
        """Break a string into lowercase alphanumeric tokens.

        From comics_backend/app/routers/library/search_utils.py

        Args:
            text: Input text

        Returns:
            List of tokens
        """
        _TOKEN_RE = re.compile(r"[0-9a-zA-Z]+")
        return [token for token in _TOKEN_RE.findall(text.lower()) if token]

    def _get_alternate_issue_formats(self, issue: str) -> list[str]:
        """Generate alternative issue number formats.

        Args:
            issue: Original issue number

        Returns:
            List of alternative formats
        """
        alternatives = []

        # Remove hash prefix
        if issue.startswith("#"):
            alternatives.append(issue[1:])

        # Add leading zero
        if issue.isdigit() and len(issue) == 1:
            alternatives.append(f"0{issue}")

        # Add hash prefix
        if not issue.startswith("#"):
            alternatives.append(f"#{issue}")

        # Remove variant suffixes for base search
        base_issue = re.split(r"[A-Z]", issue)[0]
        if base_issue != issue:
            alternatives.append(base_issue)

        return list(set(alternatives))  # Deduplicate

    async def _update_platform_status(
        self,
        operation_id: UUID,
        platform: str,
        status: str,
        strategy: Optional[str] = None,
        retry: Optional[int] = None,
    ) -> None:
        """Update platform status in operation metadata.

        Args:
            operation_id: Operation UUID
            platform: Platform code
            status: Status string (searching, found, not_found, failed, etc.)
            strategy: Current strategy being attempted
            retry: Current retry number (1-indexed)
        """
        try:
            platform_entry: dict[str, Any] = {"status": status}
            if strategy:
                platform_entry["strategy"] = strategy
            if retry is not None:
                platform_entry["retry"] = retry

            async with self._progress_lock:
                async with AsyncSessionLocal() as session:
                    ops_manager = OperationsManager(session)
                    operation = await ops_manager.get_operation(operation_id)

                    if operation:
                        current_result = operation.result or {}
                        platform_status = current_result.get("platform_status", {})
                        platform_status[platform] = platform_entry
                        current_result["platform_status"] = platform_status

                        await ops_manager.update_operation(
                            operation_id,
                            "running",
                            result=current_result,
                        )
                        await session.commit()
        except Exception as e:
            logger.warning(
                "Failed to update platform status",
                operation_id=str(operation_id),
                platform=platform,
                status=status,
                error=str(e),
            )

    async def _persist_operation_progress(
        self,
        operation_id: UUID,
        platform_status: dict[str, Any],
    ) -> None:
        """Persist aggregated platform progress using an isolated session."""
        async with self._progress_lock:
            async with AsyncSessionLocal() as session:
                ops_manager = OperationsManager(session)
                operation = await ops_manager.get_operation(operation_id)

                if operation:
                    current_result = operation.result or {}
                    current_result["platform_status"] = platform_status
                    await ops_manager.update_operation(
                        operation_id,
                        "running",
                        result=current_result,
                    )
                    await session.commit()
