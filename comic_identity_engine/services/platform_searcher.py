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

from comic_identity_engine.config import get_adapter_settings
from comic_identity_engine.database.connection import AsyncSessionLocal
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
        "request_timeout_sec": 15,
        "strategies": ["exact", "no_year", "subtitle_only", "normalized_title"],
        "circuit_breaker": {
            "failure_threshold": 10,
            "reset_timeout_seconds": 120,
        },
        "notes": "Excellent search, authoritative source",
    },
    "locg": {
        "request_timeout_sec": 30,
        "strategies": [
            "exact",
            "no_year",
            "subtitle_only",
            "normalized_title",
            "fuzzy_title",
        ],
        "circuit_breaker": {
            "failure_threshold": 5,
            "reset_timeout_seconds": 180,
        },
        "notes": "Good search but rate limited - need backoff",
    },
    "aa": {
        "request_timeout_sec": 10,
        "strategies": [
            "exact",
            "no_year",
            "subtitle_only",
            "normalized_title",
            "fuzzy_title",
            "simplified_tokens",
        ],
        "circuit_breaker": {
            "failure_threshold": 5,
            "reset_timeout_seconds": 120,
        },
        "notes": "Finicky HTML parsing, needs multiple strategies",
    },
    "ccl": {
        "request_timeout_sec": 10,
        "strategies": [
            "exact",
            "no_year",
            "normalized_title",
            "fuzzy_title",
            "alt_issue_format",
        ],
        "circuit_breaker": {
            "failure_threshold": 5,
            "reset_timeout_seconds": 120,
        },
        "notes": "Requires session cookies, session issues common",
    },
    "cpg": {
        "request_timeout_sec": 10,
        "strategies": ["exact", "no_year"],
        "circuit_breaker": {
            "failure_threshold": 3,
            "reset_timeout_seconds": 60,
        },
        "notes": "Poor search functionality, don't waste time",
    },
    "hip": {
        "request_timeout_sec": 10,
        "strategies": ["exact", "no_year", "normalized_title", "fuzzy_title"],
        "circuit_breaker": {
            "failure_threshold": 5,
            "reset_timeout_seconds": 120,
        },
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
            "gcd": GCDScraper(
                timeout=PLATFORM_SEARCH_CONFIG["gcd"]["request_timeout_sec"]
            ),
            "locg": LoCGScraper(
                timeout=PLATFORM_SEARCH_CONFIG["locg"]["request_timeout_sec"]
            ),
            "aa": AtomicAvenueScraper(
                timeout=PLATFORM_SEARCH_CONFIG["aa"]["request_timeout_sec"]
            ),
            "ccl": CCLScraper(
                timeout=PLATFORM_SEARCH_CONFIG["ccl"]["request_timeout_sec"]
            ),
            "cpg": CPGScraper(
                timeout=PLATFORM_SEARCH_CONFIG["cpg"]["request_timeout_sec"]
            ),
            "hip": HipScraper(
                timeout=PLATFORM_SEARCH_CONFIG["hip"]["request_timeout_sec"]
            ),
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

        ⚠️ IMPORTANT: When to use this function ⚠️

        **USE THIS FOR:**
        - Single issue lookups (CLI: cie-find)
        - Testing and debugging
        - Edge cases where series page extraction failed

        **DO NOT USE FOR:**
        - CSV imports (use series_page_extractor instead!)
        - Bulk operations (use series_page_extractor instead!)
        - Any operation with >5 issues from the same series

        **WHY:**
        This function searches for ONE issue on ALL platforms.
        For bulk imports, you should:
        1. Find ONE issue from a series on all platforms (using this function)
        2. Extract series page URLs from the results
        3. Scrape ALL issues from each series page
        4. Create mappings for all issues at once

        See: SERIES_PAGE_STRATEGY.md for the bulk extraction pattern.

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
        all_platforms = [
            "gcd",
            "locg",
            "aa",
            "ccl",
            "cpg",
        ]  # hip disabled - auth issues

        # Mark source platform as found immediately
        platform_status: dict[str, Any] = {
            source_platform: {
                "status": "found",
                "reason": "source_mapping",
            }
        }

        # Create tasks for all other platforms
        tasks: list[asyncio.Task[tuple[str, dict[str, Any]]]] = []
        for platform in all_platforms:
            if platform == source_platform:
                continue

            platform_status[platform] = {"status": "searching"}
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
        initial_events = [
            self._build_platform_event(
                source_platform,
                "found",
                reason="source_mapping",
            ),
            *[
                self._build_platform_event(platform, "searching")
                for platform in all_platforms
                if platform != source_platform
            ],
        ]
        await self._persist_operation_progress(
            operation_id=operation_id,
            platform_status=dict(platform_status),
            new_events=initial_events,
        )
        event_log = list(initial_events)

        found_urls = {}
        for completed_task in asyncio.as_completed(tasks):
            logger.debug(
                "DEBUG: Task completed, processing result",
                task_type=type(completed_task),
            )
            try:
                platform, result = await completed_task
                logger.debug(
                    "DEBUG: Task result received",
                    platform=platform,
                    result_type=type(result),
                    has_url="url" in result,
                    url=result.get("url") if isinstance(result, dict) else "not_a_dict",
                )
            except Exception as e:
                platform = getattr(e, "platform", "unknown")
                platform_status[platform] = {
                    "status": "failed",
                    "reason": "task_crashed",
                    "detail": str(e),
                }
                logger.warning(
                    "Platform search failed",
                    platform=platform,
                    error=str(e),
                )
            else:
                if result.get("url"):
                    found_urls[platform] = result.get("url")
                    logger.info(
                        "DEBUG: Added URL to found_urls",
                        platform=platform,
                        url=result.get("url"),
                        total_found=len(found_urls),
                    )
                    platform_status[platform] = self._build_platform_entry(
                        status="found",
                        strategy=result.get("strategy"),
                        retry=result.get("retry"),
                        reason=result.get("reason"),
                        detail=result.get("detail"),
                    )
                else:
                    logger.debug(
                        "DEBUG: Platform search result has no URL",
                        platform=platform,
                        result_keys=list(result.keys())
                        if isinstance(result, dict)
                        else "not_a_dict",
                        result_status=result.get("status"),
                        result_url=result.get("url"),
                    )
                    platform_status[platform] = self._build_platform_entry(
                        status=result.get("status", "not_found"),
                        strategy=result.get("strategy"),
                        retry=result.get("retry"),
                        reason=result.get("reason"),
                        detail=result.get("detail"),
                    )

            # Update operation with current platform_status for real-time progress
            try:
                new_events = [
                    self._build_platform_event(
                        platform,
                        platform_status[platform]["status"],
                        strategy=platform_status[platform].get("strategy"),
                        retry=platform_status[platform].get("retry"),
                        reason=platform_status[platform].get("reason"),
                        detail=platform_status[platform].get("detail"),
                    )
                ]
                event_log.extend(new_events)
                await self._persist_operation_progress(
                    operation_id=operation_id,
                    platform_status=dict(platform_status),
                    new_events=new_events,
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
            "events": event_log,
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
    ) -> tuple[str, dict[str, Any]]:
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
    ) -> dict[str, Any]:
        """Run a single platform search with an optional hard wall-clock timeout."""
        timeout_seconds = self._get_platform_timeout_seconds()
        if timeout_seconds is None:
            return await self._search_single_platform_with_strategies(
                platform=platform,
                issue_id=issue_id,
                series_title=series_title,
                issue_number=issue_number,
                year=year,
                publisher=publisher,
                operation_id=operation_id,
            )

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
            return {
                "url": None,
                "status": "not_found",
                "reason": "timeout",
                "detail": f"hit {timeout_seconds:.1f}s platform timeout",
            }

    async def _search_single_platform_with_strategies(
        self,
        platform: str,
        issue_id: UUID,
        series_title: str,
        issue_number: str,
        year: Optional[int],
        publisher: Optional[str],
        operation_id: UUID,
    ) -> dict[str, Any]:
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
            return {
                "url": None,
                "status": "not_found",
                "reason": "scraper_unavailable",
                "detail": f"scraper not configured for platform={platform}",
            }

        start_time = time.time()
        attempted_strategies: list[str] = []
        attempts = 0
        last_error: str | None = None

        # Try each strategy in order
        for strategy in config["strategies"]:
            attempted_strategies.append(strategy)
            # Update status to show current strategy
            status_key = f"searching_{strategy}" if strategy != "exact" else "searching"
            await self._update_platform_status(
                operation_id, platform, status_key, strategy=strategy, retry=1
            )

            try:
                timeout_seconds = self._get_platform_timeout_seconds()
                if (
                    timeout_seconds is not None
                    and time.time() - start_time > timeout_seconds
                ):
                    logger.warning(
                        "Platform search timeout",
                        platform=platform,
                        duration_sec=timeout_seconds,
                    )
                    return {
                        "url": None,
                        "status": "not_found",
                        "strategy": strategy,
                        "retry": 1,
                        "reason": "timeout",
                        "detail": (
                            f"exceeded {timeout_seconds:.1f}s while "
                            f"running strategy={strategy}"
                        ),
                    }

                # Execute search with this strategy (scraper handles retries internally via circuit breaker)
                result = await self._execute_strategy(
                    scraper=scraper,
                    strategy=strategy,
                    series_title=series_title,
                    issue_number=issue_number,
                    year=year,
                    publisher=publisher,
                )

                logger.debug(
                    "DEBUG: Strategy completed",
                    platform=platform,
                    strategy=strategy,
                    has_result=result is not None,
                    result_url=getattr(result, "url", None) if result else None,
                )

                candidate_url, candidate_detail = self._select_candidate_url(
                    platform=platform,
                    result=result,
                    series_title=series_title,
                    issue_number=issue_number,
                )
                if candidate_url:
                    # FOUND! Return the exact discovered URL.
                    url = await self._create_mapping_from_search_result(
                        platform=platform,
                        issue_id=issue_id,
                        result=result,
                        selected_url=candidate_url,
                    )
                    return {
                        "url": url,
                        "status": "found",
                        "strategy": strategy,
                        "retry": 1,
                        "reason": "match_found",
                        "detail": candidate_detail
                        or f"matched via strategy={strategy}",
                    }

                # Clean empty or mismatched results should move to the next
                # strategy, not be retried as if they were transient failures.
                if candidate_detail:
                    last_error = candidate_detail

            except NetworkError as e:
                last_error = str(e)
                logger.error(
                    "Platform search failed (network error)",
                    platform=platform,
                    strategy=strategy,
                    error=str(e),
                )
                # Try next strategy
                continue
            except Exception as e:
                last_error = str(e)
                logger.error(
                    "Strategy failed",
                    platform=platform,
                    strategy=strategy,
                    error=str(e),
                )
                # Try next strategy
                continue

        # All strategies exhausted
        reason = "no_match"
        detail = (
            f"no match after {attempts} attempts across "
            f"{', '.join(attempted_strategies)}"
        )
        if last_error:
            reason = "no_match_after_errors"
            detail = f"{detail}; last_error={last_error}"
        return {
            "url": None,
            "status": "not_found",
            "reason": reason,
            "detail": detail,
        }

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
        elif strategy == "subtitle_only":
            if ":" in series_title:
                search_title = series_title.split(":", 1)[1].strip()
            else:
                return None
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

        # DEBUG: Print search parameters BEFORE calling scraper
        platform = scraper.__class__.__name__.replace("Scraper", "").lower()
        print(f"\n{'=' * 80}")
        print(f"🔍 DEBUG: [{platform.upper()}] Executing strategy: {strategy}")
        print(f"   Search parameters:")
        print(f"     title:    '{search_title}'")
        print(f"     issue:    '{search_issue}'")
        print(f"     year:     {search_year}")
        print(f"     publisher: '{search_publisher}'")
        print(f"{'=' * 80}\n")

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
            if listing_issue != normalized_issue:
                continue

            score = jellyfish.jaro_winkler_similarity(
                self._normalize_title(title),
                self._normalize_title(getattr(listing, "title", "") or ""),
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

    def _select_candidate_url(
        self,
        platform: str,
        result: Optional[Any],
        series_title: str,
        issue_number: str,
    ) -> tuple[Optional[str], Optional[str]]:
        """Select a matching candidate URL from a scraper result.

        The cross-platform search used to treat any result as a match and then
        take the first listing URL. That produced false positives such as Hip
        listings for the wrong issue and Atomic Avenue series pages standing in
        for issue pages. This method only accepts URLs that match the requested
        title/issue pair closely enough to be credible.
        """
        logger.debug(
            "DEBUG: _select_candidate_url called",
            platform=platform,
            has_result=result is not None,
            result_type=type(result).__name__ if result else None,
        )

        if not result:
            logger.debug("DEBUG: _select_candidate_url - no result, returning None")
            return None, None

        if platform == "aa":
            direct_url = getattr(result, "url", None)
            logger.debug(
                "DEBUG: _select_candidate_url - AA platform",
                has_url=direct_url is not None,
                url=direct_url,
                has_item_slash=direct_url and "/item/" in direct_url,
            )
            if direct_url and "/item/" in direct_url:
                logger.info(
                    "DEBUG: AA URL selected",
                    url=direct_url,
                    reason="matched issue page via strategy result",
                )
                return direct_url, "matched issue page via strategy result"
            logger.warning(
                "DEBUG: AA URL rejected",
                url=direct_url,
                reason="result did not identify an issue page",
            )
            return None, "result did not identify an issue page"

        listings = getattr(result, "listings", None) or []
        for listing in listings:
            if self._listing_matches_target(
                platform=platform,
                listing=listing,
                series_title=series_title,
                issue_number=issue_number,
            ):
                return listing.url, "matched listing title and issue"

        direct_url = getattr(result, "url", None)
        if direct_url and self._url_matches_target(platform, direct_url, issue_number):
            return direct_url, "matched direct result URL"

        return None, "results did not match the requested issue"

    def _listing_matches_target(
        self,
        platform: str,
        listing: Any,
        series_title: str,
        issue_number: str,
    ) -> bool:
        """Return True when a scraper listing credibly matches the target issue."""
        url = getattr(listing, "url", None)
        if not url:
            return False

        title = getattr(listing, "title", "") or ""
        if title and not self._title_matches_target(series_title, title):
            return False

        extracted_issue = self._extract_issue_from_text(title)
        if extracted_issue is None:
            extracted_issue = self._extract_issue_from_url(platform, url)

        if extracted_issue is None:
            return False

        return extracted_issue == self._normalize_issue(issue_number)

    def _title_matches_target(self, series_title: str, listing_title: str) -> bool:
        """Check whether a listing title looks like the requested series."""
        target = self._normalize_title(series_title)
        listing = self._normalize_title(listing_title)
        if not target or not listing:
            return False
        return target in listing or listing in target

    def _normalize_title(self, text: str) -> str:
        """Normalize comic titles for loose comparison."""
        normalized = text.lower()
        normalized = re.sub(r"\(\d{4}\)", "", normalized)
        normalized = re.sub(r"#[^\s]+", "", normalized)
        normalized = re.sub(r"[^a-z0-9\s-]", " ", normalized)
        normalized = normalized.replace("-", " ")
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _extract_issue_from_text(self, text: str) -> Optional[str]:
        """Extract an issue number from listing text."""
        if not text:
            return None

        hash_match = re.search(r"#\s*([-\w./]+)", text)
        if hash_match:
            return self._normalize_issue_token(hash_match.group(1))

        year_paren_match = re.search(r"\(\d{4}\)\s+([-\w./]+)", text)
        if year_paren_match:
            return self._normalize_issue_token(year_paren_match.group(1))

        trailing_match = re.search(r"\b([-\d]+(?:[-/][A-Za-z0-9]+)?)\b", text)
        if trailing_match:
            return self._normalize_issue_token(trailing_match.group(1))

        return None

    def _extract_issue_from_url(self, platform: str, url: str) -> Optional[str]:
        """Extract an issue number from a platform URL when possible."""
        if platform == "cpg":
            match = re.search(r"/titles/[^/]+/([^/]+)/[^/]+/?$", url)
            if match:
                return self._normalize_issue_token(match.group(1))
        if platform == "ccl":
            match = re.search(r"/issue/comic-books/[^/]+/([^/]+)/[^/]+/?$", url)
            if match:
                return self._normalize_issue_token(match.group(1))
        return None

    def _url_matches_target(
        self,
        platform: str,
        url: str,
        issue_number: str,
    ) -> bool:
        """Check whether a direct result URL identifies the target issue."""
        extracted_issue = self._extract_issue_from_url(platform, url)
        if extracted_issue is None:
            if platform == "aa":
                return "/item/" in url
            return False
        return extracted_issue == self._normalize_issue(issue_number)

    def _normalize_issue_token(self, token: str) -> Optional[str]:
        """Normalize issue text extracted from listings or URLs."""
        cleaned = token.lower().strip()
        cleaned = cleaned.lstrip("#")
        cleaned = cleaned.rstrip(".,:;)")
        cleaned = cleaned.strip()
        if not cleaned:
            return None

        if re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned):
            return cleaned
        if re.fullmatch(r"-?\d+(?:[-/][a-z0-9]+)+", cleaned):
            match = re.match(r"-?\d+(?:\.\d+)?", cleaned)
            if match:
                return match.group(0)
        if cleaned == "1/2":
            return cleaned
        return None

    async def _create_mapping_from_search_result(
        self,
        platform: str,
        issue_id: UUID,
        result,
        selected_url: str,
    ) -> str:
        """Return the exact discovered URL without persisting inferred mappings.

        Args:
            platform: Platform code
            issue_id: Canonical issue UUID
            result: SearchResult with listings

        Returns:
            Platform URL for the found issue
        """
        logger.info(
            "Using transient platform URL from search result",
            platform=platform,
            issue_id=str(issue_id),
            url=selected_url,
        )

        return selected_url

    def _extract_ids_from_url(
        self, platform: str, url: str
    ) -> tuple[str, Optional[str]]:
        """Reject URL-derived ID inference until mappings store source_url.

        This code path used to reverse-engineer platform IDs from scraped URLs
        and write them into the database. That violates the implementation plan:
        the exact discovered URL should be stored authoritatively on the mapping,
        not repeatedly inferred into new IDs with platform-specific regexes.
        """
        raise NotImplementedError(
            "URL-derived mapping inference has been removed. Persist the exact "
            "source_url on external mappings and derive identifiers from adapter "
            "payloads instead of scraping them back out of URLs."
        )

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
        platform = scraper_class.replace("Scraper", "").lower()

        # Scrapers that accept Comic object or dict
        if scraper_class in ("LoCGScraper", "CCLScraper", "HipScraper"):
            comic_dict = {
                "title": title,
                "issue": issue,
                "year": year,
                "publisher": publisher,
            }
            print(f"🔗 DEBUG: Calling {scraper_class}.search_comic() with dict:")
            print(f"   {comic_dict}")
            result = await scraper.search_comic(comic_dict)
        else:
            # Scrapers that accept individual parameters
            # GCDScraper, CPGScraper, AtomicAvenueScraper
            print(f"🔗 DEBUG: Calling {scraper_class}.search_comic() with args:")
            print(
                f"   title={title!r}, issue={issue!r}, year={year}, publisher={publisher!r}"
            )
            result = await scraper.search_comic(
                title=title,
                issue=issue,
                year=year,
                publisher=publisher,
            )

        # DEBUG: Print result after search completes
        print(f"\n📊 DEBUG: [{platform.upper()}] Search completed:")
        if result:
            result_url = getattr(result, "url", None)
            print(f"   ✓ Result found!")
            print(f"   Result URL: {result_url}")
            listings = getattr(result, "listings", None)
            if listings:
                print(f"   Listings count: {len(listings)}")
                for i, listing in enumerate(listings[:5]):
                    listing_url = getattr(listing, "url", "N/A")
                    listing_title = getattr(listing, "title", "N/A")
                    print(f"     Listing {i + 1}: {listing_url}")
                    print(f"       Title: {listing_title}")
                    if hasattr(listing, "metadata") and listing.metadata:
                        print(f"       Metadata: {listing.metadata}")
            else:
                print(f"   ⚠️  No listings found in result")
        else:
            print(f"   ✗ No result returned")
        print(f"{'=' * 80}\n")

        return result

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

    def _get_platform_timeout_seconds(self) -> float | None:
        """Return the optional hard timeout for platform searches."""
        configured_timeout = get_adapter_settings().platform_search_timeout
        if configured_timeout is None:
            return None
        return float(configured_timeout)

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
        reason: Optional[str] = None,
        detail: Optional[str] = None,
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
            platform_entry = self._build_platform_entry(
                status=status,
                strategy=strategy,
                retry=retry,
                reason=reason,
                detail=detail,
            )

            async with self._progress_lock:
                async with AsyncSessionLocal() as session:
                    ops_manager = OperationsManager(session)
                    operation = await ops_manager.get_operation(operation_id)

                    if operation:
                        current_result = operation.result or {}
                        platform_status = current_result.get("platform_status", {})
                        platform_status[platform] = platform_entry
                        current_result["platform_status"] = platform_status
                        current_result.setdefault("platform_events", []).append(
                            self._build_platform_event(
                                platform=platform,
                                status=status,
                                strategy=strategy,
                                retry=retry,
                                reason=reason,
                                detail=detail,
                            )
                        )

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
        new_events: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        """Persist aggregated platform progress using an isolated session."""
        async with self._progress_lock:
            async with AsyncSessionLocal() as session:
                ops_manager = OperationsManager(session)
                operation = await ops_manager.get_operation(operation_id)

                if operation:
                    current_result = operation.result or {}
                    current_result["platform_status"] = platform_status
                    if new_events:
                        current_result.setdefault("platform_events", []).extend(
                            new_events
                        )
                    await ops_manager.update_operation(
                        operation_id,
                        "running",
                        result=current_result,
                    )
                    await session.commit()

    def _build_platform_event(
        self,
        platform: str,
        status: str,
        strategy: Optional[str] = None,
        retry: Optional[int] = None,
        reason: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build a persisted platform event for later CLI inspection."""
        event: dict[str, Any] = {
            "platform": platform,
            "status": status,
            "timestamp": round(time.time(), 3),
        }
        if strategy:
            event["strategy"] = strategy
        if retry is not None:
            event["retry"] = retry
        if reason:
            event["reason"] = reason
        if detail:
            event["detail"] = detail
        return event

    def _build_platform_entry(
        self,
        status: str,
        strategy: Optional[str] = None,
        retry: Optional[int] = None,
        reason: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build a persisted platform-status payload for operation results."""
        entry: dict[str, Any] = {"status": status}
        if strategy:
            entry["strategy"] = strategy
        if retry is not None:
            entry["retry"] = retry
        if reason:
            entry["reason"] = reason
        if detail:
            entry["detail"] = detail
        return entry
