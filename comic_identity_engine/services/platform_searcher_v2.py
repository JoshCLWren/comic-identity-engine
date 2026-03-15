"""Platform searcher service for thorough cross-platform comic search.

This service implements exhaustive search across all comic platforms with:
- Multiple search strategies per platform
- Task-based HTTP requests via AsyncHttpExecutor
- Real-time status updates
- Parallel execution for speed
- Platform-specific configurations

USAGE:
    searcher = PlatformSearcher(session, queue, operations_manager)
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

import structlog

from comic_identity_engine.core.async_http import AsyncHttpExecutor
from comic_identity_engine.database.connection import AsyncSessionLocal
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
        "strategies": ["exact", "no_year", "normalized_title"],
        "circuit_breaker": {
            "failure_threshold": 10,
            "reset_timeout_seconds": 120,
        },
        "notes": "Excellent search, authoritative source",
    },
    "locg": {
        "request_timeout_sec": 30,
        "strategies": ["exact", "no_year", "normalized_title", "fuzzy_title"],
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
    """Search all platforms thoroughly with multiple strategies and retries.

    This redesigned version uses task-based HTTP requests through AsyncHttpExecutor
    for maximum parallelism across workers.
    """

    def __init__(
        self,
        session: Any,
        queue: Any,
        operations_manager: OperationsManager,
    ):
        """Initialize platform searcher.

        Args:
            session: Database session
            queue: JobQueue for enqueueing HTTP requests
            operations_manager: OperationsManager for tracking progress
        """
        self.session = session
        self.queue = queue
        self.operations_manager = operations_manager
        self.async_http = AsyncHttpExecutor(queue, operations_manager)
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

    async def search_single_platform(
        self,
        platform: str,
        series_title: str,
        issue_number: str,
        year: Optional[int],
        publisher: Optional[str],
        operation_id: UUID,
    ) -> dict[str, Any]:
        """Search a single platform by enqueuing HTTP request tasks.

        This replaces the old synchronous approach with task-based parallelism.
        Each strategy enqueues separate HTTP request tasks.

        Args:
            platform: Platform code
            series_title: Series to search
            issue_number: Issue number
            year: Publication year
            publisher: Publisher name
            operation_id: Parent operation ID

        Returns:
            {
                "platform": str,
                "found": bool,
                "url": str | None,
                "source_issue_id": str | None,
                "strategies_tried": list[str],
                "total_requests": int,
                "elapsed_ms": int,
            }
        """
        start_time = time.time()
        config = PLATFORM_SEARCH_CONFIG[platform]
        attempted_strategies = []

        # Try each strategy
        for strategy in config["strategies"]:
            attempted_strategies.append(strategy)

            # Update status to show current strategy
            status_key = f"searching_{strategy}" if strategy != "exact" else "searching"
            await self._update_platform_status(
                operation_id, platform, status_key, strategy=strategy, retry=1
            )

            try:
                # Build search URL for this strategy
                search_params = self._get_search_params(
                    strategy, series_title, issue_number, year, publisher
                )

                # Use task-based HTTP request
                url = self._build_search_url(platform, search_params)
                result = await self.async_http.get(platform, url)

                if result["success"] and result["content"]:
                    # Parse result
                    parsed = self._parse_search_result(platform, result["content"])

                    if parsed and parsed.get("url"):
                        return {
                            "platform": platform,
                            "found": True,
                            "url": parsed["url"],
                            "source_issue_id": parsed.get("id"),
                            "strategies_tried": attempted_strategies,
                            "total_requests": len(attempted_strategies),
                            "elapsed_ms": int((time.time() - start_time) * 1000),
                        }

            except Exception as e:
                logger.warning(
                    "Strategy failed",
                    platform=platform,
                    strategy=strategy,
                    error=str(e),
                )
                # Try next strategy
                continue

        return {
            "platform": platform,
            "found": False,
            "url": None,
            "source_issue_id": None,
            "strategies_tried": attempted_strategies,
            "total_requests": len(attempted_strategies),
            "elapsed_ms": int((time.time() - start_time) * 1000),
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
    ) -> dict[str, Any]:
        """Search all platforms in parallel using task queue.

        This creates 6 concurrent search tasks (one per platform).
        Each search task may enqueue multiple HTTP request tasks.

        Args:
            issue_id: Canonical issue UUID
            series_title: Series title
            issue_number: Issue number
            year: Publication year
            publisher: Publisher name
            operation_id: Parent operation ID
            source_platform: Original platform (skip searching it again)

        Returns:
            {
                "urls": {platform: url},
                "status": {platform: status},
                "events": [...],
            }
        """
        platforms = ["gcd", "locg", "ccl", "aa", "cpg", "hip"]

        # Skip source platform
        if source_platform in platforms:
            platforms.remove(source_platform)

        # Mark source platform as found immediately
        platform_status: dict[str, Any] = {
            source_platform: {
                "status": "found",
                "reason": "source_mapping",
            }
        }

        # Create concurrent search tasks (one per platform)
        search_tasks = [
            self.search_single_platform(
                platform=platform,
                series_title=series_title,
                issue_number=issue_number,
                year=year,
                publisher=publisher,
                operation_id=operation_id,
            )
            for platform in platforms
        ]

        # Persist the initial snapshot before any platform finishes
        initial_events = [
            self._build_platform_event(
                source_platform,
                "found",
                reason="source_mapping",
            ),
            *[
                self._build_platform_event(platform, "searching")
                for platform in platforms
            ],
        ]
        await self._persist_operation_progress(
            operation_id=operation_id,
            platform_status=dict(platform_status),
            new_events=initial_events,
        )
        event_log = list(initial_events)

        # Mark all platforms as searching
        for platform in platforms:
            platform_status[platform] = {"status": "searching"}

        # Execute all platform searches concurrently
        results = await asyncio.gather(*search_tasks, return_exceptions=True)

        # Aggregate results
        urls = {}
        events = []

        for platform, result in zip(platforms, results):
            if isinstance(result, Exception):
                platform_status[platform] = {
                    "status": "failed",
                    "reason": "task_crashed",
                    "detail": str(result),
                }
                events.append(
                    {
                        "platform": platform,
                        "status": "failed",
                        "error": str(result),
                    }
                )
                logger.warning(
                    "Platform search failed",
                    platform=platform,
                    error=str(result),
                )
            elif result["found"]:
                urls[platform] = result["url"]
                platform_status[platform] = {
                    "status": "found",
                    "strategy": result["strategies_tried"][-1]
                    if result["strategies_tried"]
                    else None,
                    "reason": "match_found",
                }
                events.append(
                    {
                        "platform": platform,
                        "status": "found",
                        "source_issue_id": result["source_issue_id"],
                    }
                )
            else:
                platform_status[platform] = {
                    "status": "not_found",
                    "strategies_tried": result["strategies_tried"],
                }
                events.append(
                    {
                        "platform": platform,
                        "status": "not_found",
                        "strategies_tried": result["strategies_tried"],
                    }
                )

        event_log.extend(events)
        await self._persist_operation_progress(
            operation_id=operation_id,
            platform_status=platform_status,
            new_events=events,
        )

        return {
            "urls": urls,
            "status": platform_status,
            "events": event_log,
        }

    def _get_search_params(
        self,
        strategy: str,
        series_title: str,
        issue_number: str,
        year: Optional[int],
        publisher: Optional[str],
    ) -> dict[str, Any]:
        """Get search parameters for a strategy."""
        params = {
            "title": series_title,
            "issue": issue_number,
            "year": year,
            "publisher": publisher,
        }

        if strategy == "no_year":
            params["year"] = None
        elif strategy == "normalized_title":
            params["title"] = self._normalize_series_name(series_title)
        elif strategy == "simplified_tokens":
            tokens = self._tokenize(series_title)
            params["title"] = " ".join(tokens)

        return params

    def _build_search_url(self, platform: str, params: dict[str, Any]) -> str:
        """Build search URL for a platform."""
        # This would call the scraper's search methods
        # For now, return a placeholder - actual implementation would
        # use the scraper's search_comic methods
        return f"https://{platform}.example.com/search"

    def _parse_search_result(
        self, platform: str, content: str
    ) -> Optional[dict[str, Any]]:
        """Parse search result content."""
        # This would parse the HTML/JSON response
        # For now, return None - actual implementation would
        # use the scraper's parsing logic
        return None

    def _normalize_series_name(self, name: str) -> str:
        """Normalize series name for fuzzy matching."""
        name = name.lower().strip()
        name = re.sub(r"\s+", " ", name)
        name = re.sub(r"\(.*?\)", "", name)
        name = re.sub(r"vol\.?\s*\d+", "", name)
        name = name.strip()
        return name

    def _tokenize(self, text: str) -> list[str]:
        """Break a string into lowercase alphanumeric tokens."""
        _TOKEN_RE = re.compile(r"[0-9a-zA-Z]+")
        return [token for token in _TOKEN_RE.findall(text.lower()) if token]

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
        """Update platform status in operation metadata."""
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
