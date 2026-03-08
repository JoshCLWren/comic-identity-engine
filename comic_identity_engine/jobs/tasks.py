"""ARQ job tasks for Comic Identity Engine.

This module provides background task functions for arq that handle:
- Identity resolution from URLs
- Bulk resolution operations
- CLZ CSV imports
- Data exports
- Cross-platform reconciliation

All tasks follow AIP-151 operation tracking patterns and use the
OperationsManager for status updates.

USAGE:
    # Enqueue a task from an API endpoint or CLI
    job = await arq_redis.enqueue_job(
        "resolve_identity_task",
        url="https://www.comics.org/issue/125295/",
        operation_id="550e8400-e29b-41d4-a716-446655440000"
    )
"""

import csv
import json
import tempfile
import uuid
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.exc import SQLAlchemyError

from comic_identity_engine.adapters import (
    AAAdapter,
    CCLAdapter,
    CLZAdapter,
    CPGAdapter,
    GCDAdapter,
    HIPAdapter,
    LoCGAdapter,
    NotFoundError,
    SourceAdapter,
    SourceError,
    ValidationError as AdapterValidationError,
)
from comic_identity_engine.database.connection import AsyncSessionLocal
from comic_identity_engine.database.repositories import (
    ExternalMappingRepository,
    IssueRepository,
    SeriesRunRepository,
    VariantRepository,
)
from comic_identity_engine.errors import (
    DuplicateEntityError,
    NetworkError,
    ParseError,
    ResolutionError,
    ValidationError,
)
from comic_identity_engine.services import (
    IdentityResolver,
    OperationsManager,
    parse_url,
)

logger = structlog.get_logger(__name__)


def _mapping_conflict_message(source: str, source_issue_id: str) -> str:
    """Build a consistent user-facing message for source mapping conflicts."""
    return (
        "Existing external mapping points to a different canonical "
        f"issue for {source}:{source_issue_id}; use --clear-mappings "
        f"{source_issue_id} to replace it"
    )


async def _ensure_source_mapping(
    mapping_repo: ExternalMappingRepository,
    issue_id: uuid.UUID,
    source: str,
    source_issue_id: str,
    source_series_id: str | None,
) -> str:
    """Ensure a source mapping exists and points at the resolved issue.

    Returns:
        "created" if a new mapping was inserted, "reused" if an existing mapping
        already pointed at the same issue.

    Raises:
        ValidationError: If the existing mapping points at a different issue.
    """
    existing = await mapping_repo.find_by_source(source, source_issue_id)
    if existing is not None:
        if existing.issue_id == issue_id:
            return "reused"
        raise ValidationError(_mapping_conflict_message(source, source_issue_id))

    try:
        await mapping_repo.create_mapping(
            issue_id=issue_id,
            source=source,
            source_issue_id=source_issue_id,
            source_series_id=source_series_id,
        )
        return "created"
    except DuplicateEntityError:
        # Handle races against older workers or concurrent requests.
        existing = await mapping_repo.find_by_source(source, source_issue_id)
        if existing is not None and existing.issue_id == issue_id:
            return "reused"
        raise ValidationError(
            _mapping_conflict_message(source, source_issue_id)
        ) from None


def get_adapter(platform: str) -> SourceAdapter:
    """Get the appropriate adapter for a platform.

    Args:
        platform: Platform code (e.g., "gcd", "locg", "ccl", "aa", "cpg", "hip")

    Returns:
        SourceAdapter instance for the platform

    Raises:
        ValueError: If platform is not supported
    """
    from comic_identity_engine.core.http_client import HttpClient

    # CCL has SSL certificate issues, so disable verification for now
    verify_ssl = platform != "ccl"

    adapters = {
        "gcd": (GCDAdapter, verify_ssl),
        "locg": (LoCGAdapter, verify_ssl),
        "ccl": (CCLAdapter, False),
        "aa": (AAAdapter, verify_ssl),
        "cpg": (CPGAdapter, verify_ssl),
        "hip": (HIPAdapter, verify_ssl),
    }

    if platform not in adapters:
        raise ValueError(f"Unsupported platform: {platform}")

    adapter_class, should_verify = adapters[platform]
    http_client = HttpClient(platform=platform, verify_ssl=should_verify)

    return adapter_class(http_client=http_client)


async def resolve_identity_task(
    ctx: dict[str, Any],
    url: str,
    operation_id: str,
    force: bool = False,
    clear_mappings: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Resolve comic identity from a URL.

    This task parses a comic platform URL, resolves the identity using
    the IdentityResolver, and updates the operation status.

    Args:
        ctx: ARQ context dictionary
        url: URL from a comic platform (GCD, LoCG, CCL, etc.)
        operation_id: UUID of the operation to track
        force: Skip idempotency check and re-search even if mapping exists
        clear_mappings: Delete all external mappings for this source_issue_id before searching
        dry_run: Show what would happen without executing the search

    Returns:
        Dictionary with resolution results:
        - issue_id: Resolved canonical issue UUID
        - confidence: Match confidence score (0.0-1.0)
        - urls: Dictionary of platform URLs for the issue
        - created_new: True if a new issue was created
        - explanation: Human-readable resolution explanation
        - dry_run: True if this was a dry run

    Raises:
        No exceptions raised - all errors are caught and operation marked as failed.

    Examples:
        >>> result = await resolve_identity_task(
        ...     {},
        ...     "https://www.comics.org/issue/125295/",
        ...     "550e8400-e29b-41d4-a716-446655440000"
        ... )
        >>> print(result["issue_id"])
        '550e8400-e29b-41d4-a716-446655440001'
        >>> print(result["confidence"])
        0.95
    """
    async with AsyncSessionLocal() as session:
        operation_uuid = None
        parsed_url = None
        try:
            operation_uuid = uuid.UUID(operation_id)
            operations_manager = OperationsManager(session)

            await operations_manager.mark_running(operation_uuid)
            await session.commit()

            logger.info(
                "Starting identity resolution task",
                operation_id=operation_id,
                url=url,
                force=force,
                clear_mappings=clear_mappings,
                dry_run=dry_run,
            )

            parsed_url = parse_url(url)
            mapping_repo = ExternalMappingRepository(session)
            series_repo = SeriesRunRepository(session)

            # Handle clear_mappings: delete all external mappings for this source_issue_id
            if clear_mappings:
                logger.info(
                    "Clearing external mappings",
                    operation_id=operation_id,
                    source_issue_id=clear_mappings,
                )
                deleted_count = await mapping_repo.delete_by_source_issue_id(
                    clear_mappings
                )
                logger.info(
                    "Deleted external mappings",
                    operation_id=operation_id,
                    source_issue_id=clear_mappings,
                    deleted_count=deleted_count,
                )

            # Handle dry_run: return what would happen without executing
            if dry_run:
                logger.info(
                    "Dry run mode - returning without executing search",
                    operation_id=operation_id,
                    url=url,
                )
                result_dict = {
                    "canonical_uuid": None,
                    "confidence": 0.0,
                    "platform_urls": {},
                    "platform_status": {},
                    "created_new": False,
                    "explanation": f"DRY RUN: Would resolve URL {url}",
                    "dry_run": True,
                }
                await operations_manager.mark_completed(operation_uuid, result_dict)
                await session.commit()
                return result_dict

            # Check for existing mapping first (unless force is True)
            existing = None
            if not force:
                existing = await mapping_repo.find_by_source(
                    parsed_url.platform,
                    parsed_url.source_issue_id,
                )
            else:
                logger.info(
                    "Force mode enabled, skipping existing mapping check",
                    operation_id=operation_id,
                    platform=parsed_url.platform,
                    source_issue_id=parsed_url.source_issue_id,
                )
            if existing and not force:
                logger.info(
                    "Found existing mapping",
                    operation_id=operation_id,
                    issue_id=str(existing.issue_id),
                    platform=parsed_url.platform,
                    source_issue_id=parsed_url.source_issue_id,
                )

                # Cross-platform search: find this issue on other platforms
                resolver = IdentityResolver(session)
                issue_repo = IssueRepository(session)
                issue = await issue_repo.find_by_id(existing.issue_id)
                series = (
                    await series_repo.find_by_id(issue.series_run_id) if issue else None
                )

                cross_platform_urls = {}
                platform_status = {}

                # Mark source platform as found since we have a mapping for it
                platform_status[parsed_url.platform] = "found"

                if issue and series:
                    try:
                        from comic_identity_engine.services.platform_searcher import (
                            PlatformSearcher,
                        )

                        searcher = PlatformSearcher(session)
                        cross_platform_result = await searcher.search_all_platforms(
                            issue_id=existing.issue_id,
                            series_title=series.title,
                            issue_number=issue.issue_number,
                            year=series.start_year,
                            publisher=series.publisher,
                            operation_id=operation_uuid,
                            source_platform=parsed_url.platform,
                            operations_manager=operations_manager,
                        )
                        cross_platform_urls = cross_platform_result.get("urls", {})

                        # Merge platform_status - source platform stays "found"
                        for platform, status in cross_platform_result.get(
                            "status", {}
                        ).items():
                            if platform not in platform_status:
                                platform_status[platform] = status

                        logger.info(
                            "Cross-platform search completed",
                            operation_id=operation_id,
                            issue_id=str(existing.issue_id),
                            found_platforms=list(cross_platform_urls.keys()),
                            platform_status=cross_platform_result.get("status", {}),
                        )
                    except Exception as e:
                        logger.warning(
                            "Cross-platform search failed, continuing without it",
                            operation_id=operation_id,
                            issue_id=str(existing.issue_id),
                            error=str(e),
                        )
                        cross_platform_urls = {}

                urls = {parsed_url.platform: url}
                # TODO: once external mappings persist authoritative source URLs,
                # merge the stored per-platform URLs here. Until then, only return
                # exact URLs from this request or from the live cross-platform run.
                for platform, found_url in cross_platform_urls.items():
                    if not urls.get(platform):
                        urls[platform] = found_url

                result_dict = {
                    "canonical_uuid": str(existing.issue_id),
                    "confidence": 1.0,
                    "platform_urls": urls,
                    "platform_status": platform_status,
                    "platform_events": cross_platform_result.get("events", []),
                    "created_new": False,
                    "explanation": f"Found existing external mapping for {parsed_url.platform}:{parsed_url.source_issue_id}",
                }
                await operations_manager.mark_completed(operation_uuid, result_dict)
                await session.commit()
                return result_dict

            # Fetch from platform
            logger.info(
                "Fetching issue from platform",
                operation_id=operation_id,
                platform=parsed_url.platform,
                source_issue_id=parsed_url.source_issue_id,
            )
            adapter = get_adapter(parsed_url.platform)

            # Some platforms need the original source URL to fetch the issue page.
            if parsed_url.platform in {"aa", "hip"} and parsed_url.full_url:
                candidate = await adapter.fetch_issue(
                    parsed_url.source_issue_id, full_url=parsed_url.full_url
                )
            else:
                candidate = await adapter.fetch_issue(parsed_url.source_issue_id)

            # Resolve with fetched data
            resolver = IdentityResolver(session)
            result = await resolver.resolve_issue(
                parsed_url,
                upc=candidate.upc,
                series_title=candidate.series_title,
                series_start_year=candidate.series_start_year,
                issue_number=candidate.issue_number,
                cover_date=candidate.cover_date,
            )

            # Create external mapping if successful
            cross_platform_urls = {}
            cross_platform_result = {"urls": {}, "status": {}, "events": []}
            platform_status = {}
            source_mapping_action = None

            if result.issue_id:
                source_mapping_action = await _ensure_source_mapping(
                    mapping_repo=mapping_repo,
                    issue_id=result.issue_id,
                    source=parsed_url.platform,
                    source_issue_id=parsed_url.source_issue_id,
                    source_series_id=candidate.source_series_id,
                )
                if source_mapping_action == "created":
                    logger.info(
                        "Created external mapping",
                        operation_id=operation_id,
                        issue_id=str(result.issue_id),
                        platform=parsed_url.platform,
                        source_issue_id=parsed_url.source_issue_id,
                    )
                else:
                    logger.info(
                        "Reused existing external mapping",
                        operation_id=operation_id,
                        issue_id=str(result.issue_id),
                        platform=parsed_url.platform,
                        source_issue_id=parsed_url.source_issue_id,
                    )

                # Mark source platform as found since we just created a mapping for it
                platform_status[parsed_url.platform] = "found"

                # Cross-platform search: find this issue on other platforms
                try:
                    from comic_identity_engine.services.platform_searcher import (
                        PlatformSearcher,
                    )

                    searcher = PlatformSearcher(session)
                    cross_platform_result = await searcher.search_all_platforms(
                        issue_id=result.issue_id,
                        series_title=candidate.series_title,
                        issue_number=candidate.issue_number,
                        year=candidate.series_start_year,
                        publisher=None,
                        operation_id=operation_uuid,
                        source_platform=parsed_url.platform,
                        operations_manager=operations_manager,
                    )
                    cross_platform_urls = cross_platform_result.get("urls", {})

                    # Merge platform_status - source platform stays "found"
                    for platform, status in cross_platform_result.get(
                        "status", {}
                    ).items():
                        if platform not in platform_status:
                            platform_status[platform] = status

                    logger.info(
                        "Cross-platform search completed",
                        operation_id=operation_id,
                        issue_id=str(result.issue_id),
                        found_platforms=list(cross_platform_urls.keys()),
                        platform_status=cross_platform_result.get("status", {}),
                    )
                except Exception as e:
                    logger.warning(
                        "Cross-platform search failed, continuing without it",
                        operation_id=operation_id,
                        issue_id=str(result.issue_id),
                        error=str(e),
                    )
                    cross_platform_urls = {}
                    cross_platform_result = {"urls": {}, "status": {}, "events": []}

            urls = {}
            if result.issue_id:
                urls = {parsed_url.platform: url}
                # TODO: once external mappings persist authoritative source URLs,
                # merge the stored per-platform URLs here. Until then, only return
                # exact URLs from this request or from the live cross-platform run.
                for platform, found_url in cross_platform_urls.items():
                    if not urls.get(platform):
                        urls[platform] = found_url

            result_dict = {
                "canonical_uuid": str(result.issue_id) if result.issue_id else None,
                "confidence": (
                    result.best_match.overall_confidence if result.best_match else 1.0
                ),
                "platform_urls": urls,
                "platform_status": platform_status if result.issue_id else {},
                "platform_events": (
                    cross_platform_result.get("events", []) if result.issue_id else []
                ),
                "created_new": result.created_new,
                "explanation": result.explanation,
                "source_mapping_action": source_mapping_action,
            }

            await operations_manager.mark_completed(operation_uuid, result_dict)
            await session.commit()

            logger.info(
                "Identity resolution task completed",
                operation_id=operation_id,
                issue_id=str(result.issue_id) if result.issue_id else None,
                confidence=result_dict["confidence"],
            )

            return result_dict

        except ParseError as e:
            error_msg = f"URL parsing failed: {e}"
            logger.error(
                "Identity resolution task failed - parse error",
                operation_id=operation_id,
                error=error_msg,
            )
            await _mark_failed_safe(
                session,
                operation_uuid,
                error_msg,
                result={"error_type": "parse_error", "input_url": url},
            )
            await session.commit()
            return {"error": error_msg, "error_type": "parse_error"}

        except NotFoundError as e:
            error_msg = f"Issue not found on platform: {e}"
            logger.error(
                "Identity resolution task failed - issue not found",
                operation_id=operation_id,
                error=error_msg,
            )
            await _mark_failed_safe(
                session,
                operation_uuid,
                error_msg,
                result={"error_type": "not_found", "input_url": url},
            )
            await session.commit()
            return {"error": error_msg, "error_type": "not_found"}

        except NetworkError as e:
            error_msg = f"Network error communicating with platform: {e}"
            logger.error(
                "Identity resolution task failed - network error",
                operation_id=operation_id,
                error=error_msg,
            )
            await _mark_failed_safe(
                session,
                operation_uuid,
                error_msg,
                result={"error_type": "network_error", "input_url": url},
            )
            await session.commit()
            return {"error": error_msg, "error_type": "network_error"}

        except SourceError as e:
            error_msg = f"Platform communication error: {e}"
            logger.error(
                "Identity resolution task failed - platform error",
                operation_id=operation_id,
                error=error_msg,
            )
            await _mark_failed_safe(
                session,
                operation_uuid,
                error_msg,
                result={"error_type": "platform_error", "input_url": url},
            )
            await session.commit()
            return {"error": error_msg, "error_type": "platform_error"}

        except AdapterValidationError as e:
            error_msg = f"Invalid data from platform: {e}"
            logger.error(
                "Identity resolution task failed - validation error",
                operation_id=operation_id,
                error=error_msg,
            )
            await _mark_failed_safe(
                session,
                operation_uuid,
                error_msg,
                result={"error_type": "platform_validation_error", "input_url": url},
            )
            await session.commit()
            return {"error": error_msg, "error_type": "platform_validation_error"}

        except ValidationError as e:
            error_msg = f"Validation error during resolution: {e}"
            failure_result: dict[str, Any] = {
                "error_type": "validation_error",
                "input_url": url,
            }
            if parsed_url is not None:
                failure_result["source"] = parsed_url.platform
                failure_result["source_issue_id"] = parsed_url.source_issue_id
            if "use --clear-mappings" in str(e):
                failure_result["hint"] = (
                    "Retry with --clear-mappings to replace the existing mapping"
                )
            logger.error(
                "Identity resolution task failed - validation error",
                operation_id=operation_id,
                error=error_msg,
                source=getattr(parsed_url, "platform", None),
                source_issue_id=getattr(parsed_url, "source_issue_id", None),
            )
            await _mark_failed_safe(
                session,
                operation_uuid,
                error_msg,
                result=failure_result,
            )
            await session.commit()
            return {"error": error_msg, **failure_result}

        except ResolutionError as e:
            error_msg = f"Identity resolution failed: {e}"
            logger.error(
                "Identity resolution task failed - resolution error",
                operation_id=operation_id,
                error=error_msg,
            )
            await _mark_failed_safe(
                session,
                operation_uuid,
                error_msg,
                result={"error_type": "resolution_error", "input_url": url},
            )
            await session.commit()
            return {"error": error_msg, "error_type": "resolution_error"}

        except SQLAlchemyError as e:
            error_msg = f"Database error during resolution: {e}"
            logger.error(
                "Identity resolution task failed - database error",
                operation_id=operation_id,
                error=error_msg,
            )
            await _mark_failed_safe(
                session,
                operation_uuid,
                error_msg,
                result={"error_type": "database_error", "input_url": url},
            )
            await session.commit()
            return {"error": error_msg, "error_type": "database_error"}

        except Exception as e:
            error_msg = f"Unexpected error during resolution: {e}"
            logger.error(
                "Identity resolution task failed - unexpected error",
                operation_id=operation_id,
                error=error_msg,
                error_type=type(e).__name__,
            )
            if operation_uuid:
                await _mark_failed_safe(
                    session,
                    operation_uuid,
                    error_msg,
                    result={
                        "error_type": "unexpected_error",
                        "exception_type": type(e).__name__,
                        "input_url": url,
                    },
                )
                await session.commit()
            return {"error": error_msg, "error_type": "unexpected_error"}


async def bulk_resolve_task(
    ctx: dict[str, Any],
    urls: list[str],
    operation_id: str,
) -> dict[str, Any]:
    """Resolve multiple comic URLs in bulk.

    This task processes a list of URLs sequentially, updating the operation
    with progress information after each URL is processed.

    Args:
        ctx: ARQ context dictionary
        urls: List of URLs from comic platforms
        operation_id: UUID of the operation to track

    Returns:
        Dictionary with bulk resolution results:
        - total: Total number of URLs processed
        - completed: Number of successful resolutions
        - failed: Number of failed resolutions
        - results: List of individual resolution results
        - summary: Brief text summary of the operation

    Raises:
        No exceptions raised - all errors are caught and operation marked as failed.

    Examples:
        >>> result = await bulk_resolve_task(
        ...     {},
        ...     [
        ...         "https://www.comics.org/issue/125295/",
        ...         "https://www.comics.org/issue/125296/",
        ...     ],
        ...     "550e8400-e29b-41d4-a716-446655440000"
        ... )
        >>> print(result["completed"])
        2
    """
    async with AsyncSessionLocal() as session:
        try:
            operation_uuid = uuid.UUID(operation_id)
            operations_manager = OperationsManager(session)

            await operations_manager.mark_running(operation_uuid)

            logger.info(
                "Starting bulk resolution task",
                operation_id=operation_id,
                total_urls=len(urls),
            )

            results = []
            completed = 0
            failed = 0

            for idx, url in enumerate(urls):
                try:
                    logger.info(
                        "Processing URL",
                        operation_id=operation_id,
                        progress=f"{idx + 1}/{len(urls)}",
                        url=url,
                    )

                    parsed_url = parse_url(url)
                    resolver = IdentityResolver(session)
                    resolution_result = await resolver.resolve_issue(parsed_url)

                    urls_dict = {}
                    if resolution_result.issue_id:
                        # TODO: bulk results should return authoritative stored
                        # source URLs once external mappings persist them.
                        urls_dict = {parsed_url.platform: url}

                    result_entry = {
                        "url": url,
                        "canonical_uuid": (
                            str(resolution_result.issue_id)
                            if resolution_result.issue_id
                            else None
                        ),
                        "confidence": (
                            resolution_result.best_match.overall_confidence
                            if resolution_result.best_match
                            else 1.0
                        ),
                        "platform_urls": urls_dict,
                        "created_new": resolution_result.created_new,
                        "explanation": resolution_result.explanation,
                        "success": True,
                    }
                    results.append(result_entry)
                    completed += 1

                except Exception as e:
                    logger.error(
                        "Failed to resolve URL in bulk operation",
                        operation_id=operation_id,
                        url=url,
                        error=str(e),
                    )
                    results.append(
                        {
                            "url": url,
                            "success": False,
                            "error": str(e),
                            "error_type": type(e).__name__,
                        }
                    )
                    failed += 1

                progress_update = {
                    "total": len(urls),
                    "completed": completed,
                    "failed": failed,
                    "current_url_index": idx,
                }
                await operations_manager.update_operation(
                    operation_uuid, "running", result=progress_update
                )

            result_dict = {
                "total": len(urls),
                "completed": completed,
                "failed": failed,
                "results": results,
                "summary": f"Processed {len(urls)} URLs: {completed} succeeded, {failed} failed",
            }

            await operations_manager.mark_completed(operation_uuid, result_dict)

            logger.info(
                "Bulk resolution task completed",
                operation_id=operation_id,
                total=len(urls),
                completed=completed,
                failed=failed,
            )

            return result_dict

        except SQLAlchemyError as e:
            error_msg = f"Database error during bulk resolution: {e}"
            logger.error(
                "Bulk resolution task failed - database error",
                operation_id=operation_id,
                error=error_msg,
            )
            await _mark_failed_safe(session, operation_uuid, error_msg)
            return {"error": error_msg, "error_type": "database_error"}

        except Exception as e:
            error_msg = f"Unexpected error during bulk resolution: {e}"
            logger.error(
                "Bulk resolution task failed - unexpected error",
                operation_id=operation_id,
                error=error_msg,
                error_type=type(e).__name__,
            )
            await _mark_failed_safe(session, operation_uuid, error_msg)
            return {"error": error_msg, "error_type": "unexpected_error"}


async def import_clz_task(
    ctx: dict[str, Any],
    csv_path: str,
    operation_id: str,
) -> dict[str, Any]:
    """Import comic data from CLZ CSV export using identity resolution pipeline.

    This task loads a CLZ CSV file and uses the IdentityResolver to find/create
    canonical issues, creates external mappings, and runs cross-platform search.

    Args:
        ctx: ARQ context dictionary
        csv_path: Path to the CLZ CSV export file
        operation_id: UUID of the operation to track

    Returns:
        Dictionary with import results:
        - total_rows: Total number of rows in CSV
        - processed: Number of rows processed
        - resolved: Number of issues successfully resolved
        - failed: Number of issues that failed to resolve
        - errors: List of errors encountered
        - summary: Brief text summary of the import

    Raises:
        No exceptions raised - all errors are caught and operation marked as failed.

    Examples:
        >>> result = await import_clz_task(
        ...     {},
        ...     "/path/to/clz_export.csv",
        ...     "550e8400-e29b-41d4-a716-446655440000"
        ... )
        >>> print(result["resolved"])
        5
    """
    async with AsyncSessionLocal() as session:
        try:
            operation_uuid = uuid.UUID(operation_id)
            operations_manager = OperationsManager(session)

            await operations_manager.mark_running(operation_uuid)

            logger.info(
                "Starting CLZ import task",
                operation_id=operation_id,
                csv_path=csv_path,
            )

            adapter = CLZAdapter()
            rows = adapter.load_csv_from_file(csv_path)

            mapping_repo = ExternalMappingRepository(session)
            resolver = IdentityResolver(session)

            processed = 0
            resolved = 0
            failed = 0
            errors = []

            for idx, row in enumerate(rows):
                try:
                    issue_candidate = adapter.fetch_issue_from_csv_row(row)
                    source_issue_id = issue_candidate.source_issue_id

                    existing_mapping = await mapping_repo.find_by_source(
                        "clz", source_issue_id
                    )

                    if existing_mapping is not None:
                        logger.info(
                            "Existing CLZ mapping found",
                            operation_id=operation_id,
                            row=idx + 1,
                            source_issue_id=source_issue_id,
                            issue_id=str(existing_mapping.issue_id),
                        )
                        resolved += 1
                    else:
                        from comic_identity_engine.services import ParsedUrl

                        parsed_url = ParsedUrl(
                            platform="clz",
                            source_issue_id=source_issue_id,
                            source_series_id=issue_candidate.source_series_id,
                        )

                        result = await resolver.resolve_issue(
                            parsed_url=parsed_url,
                            upc=issue_candidate.upc,
                            series_title=issue_candidate.series_title,
                            series_start_year=issue_candidate.series_start_year,
                            issue_number=issue_candidate.issue_number,
                            cover_date=issue_candidate.cover_date,
                        )

                        if result.issue_id:
                            source_mapping_action = await _ensure_source_mapping(
                                mapping_repo=mapping_repo,
                                issue_id=result.issue_id,
                                source="clz",
                                source_issue_id=source_issue_id,
                                source_series_id=issue_candidate.source_series_id,
                            )

                            if source_mapping_action == "created":
                                logger.info(
                                    "Created CLZ external mapping",
                                    operation_id=operation_id,
                                    row=idx + 1,
                                    source_issue_id=source_issue_id,
                                    issue_id=str(result.issue_id),
                                )
                            else:
                                logger.info(
                                    "Reused existing CLZ external mapping",
                                    operation_id=operation_id,
                                    row=idx + 1,
                                    source_issue_id=source_issue_id,
                                    issue_id=str(result.issue_id),
                                )

                            try:
                                from comic_identity_engine.services.platform_searcher import (
                                    PlatformSearcher,
                                )

                                searcher = PlatformSearcher(session)
                                cross_platform_result = (
                                    await searcher.search_all_platforms(
                                        issue_id=result.issue_id,
                                        series_title=issue_candidate.series_title,
                                        issue_number=issue_candidate.issue_number,
                                        year=issue_candidate.series_start_year,
                                        publisher=issue_candidate.publisher,
                                        operation_id=operation_uuid,
                                        source_platform="clz",
                                        operations_manager=operations_manager,
                                    )
                                )

                                logger.info(
                                    "Cross-platform search completed",
                                    operation_id=operation_id,
                                    row=idx + 1,
                                    issue_id=str(result.issue_id),
                                    found_platforms=list(
                                        cross_platform_result.get("urls", {}).keys()
                                    ),
                                )
                            except Exception as e:
                                logger.warning(
                                    "Cross-platform search failed, continuing without it",
                                    operation_id=operation_id,
                                    row=idx + 1,
                                    issue_id=str(result.issue_id),
                                    error=str(e),
                                )

                            resolved += 1
                        else:
                            error_msg = f"Failed to resolve issue: {result.explanation}"
                            logger.warning(
                                "Failed to resolve CLZ row",
                                operation_id=operation_id,
                                row=idx + 1,
                                source_issue_id=source_issue_id,
                                error=error_msg,
                            )
                            errors.append(
                                {
                                    "row": idx + 1,
                                    "source_issue_id": source_issue_id,
                                    "error": error_msg,
                                }
                            )
                            failed += 1

                    processed += 1

                    if processed % 10 == 0:
                        progress_update = {
                            "total_rows": len(rows),
                            "processed": processed,
                            "resolved": resolved,
                            "failed": failed,
                        }
                        await operations_manager.update_operation(
                            operation_uuid, "running", result=progress_update
                        )

                except AdapterValidationError as e:
                    error_msg = f"Row {idx + 1} validation error: {e}"
                    logger.warning(error_msg)
                    errors.append(
                        {"row": idx + 1, "source_issue_id": None, "error": error_msg}
                    )
                    failed += 1

                except Exception as e:
                    error_msg = f"Row {idx + 1} error: {e}"
                    logger.error(error_msg)
                    source_issue_id = row.get("Core ComicID") if row else None
                    errors.append(
                        {
                            "row": idx + 1,
                            "source_issue_id": source_issue_id,
                            "error": error_msg,
                        }
                    )
                    failed += 1

            result_dict = {
                "total_rows": len(rows),
                "processed": processed,
                "resolved": resolved,
                "failed": failed,
                "errors": errors,
                "summary": f"Processed {len(rows)} CLZ rows: {resolved} resolved, {failed} failed. {len(errors)} errors.",
            }

            await operations_manager.mark_completed(operation_uuid, result_dict)

            logger.info(
                "CLZ import task completed",
                operation_id=operation_id,
                total_rows=len(rows),
                processed=processed,
                resolved=resolved,
                failed=failed,
                errors_count=len(errors),
            )

            return result_dict

        except FileNotFoundError as e:
            error_msg = f"CSV file not found: {e}"
            logger.error(
                "CLZ import task failed - file not found",
                operation_id=operation_id,
                error=error_msg,
            )
            await _mark_failed_safe(session, operation_uuid, error_msg)
            return {"error": error_msg, "error_type": "file_not_found"}

        except ValidationError as e:
            error_msg = f"CSV validation error: {e}"
            logger.error(
                "CLZ import task failed - validation error",
                operation_id=operation_id,
                error=error_msg,
            )
            await _mark_failed_safe(session, operation_uuid, error_msg)
            return {"error": error_msg, "error_type": "validation_error"}

        except SQLAlchemyError as e:
            error_msg = f"Database error during import: {e}"
            logger.error(
                "CLZ import task failed - database error",
                operation_id=operation_id,
                error=error_msg,
            )
            await _mark_failed_safe(session, operation_uuid, error_msg)
            return {"error": error_msg, "error_type": "database_error"}

        except Exception as e:
            error_msg = f"Unexpected error during import: {e}"
            logger.error(
                "CLZ import task failed - unexpected error",
                operation_id=operation_id,
                error=error_msg,
                error_type=type(e).__name__,
            )
            await _mark_failed_safe(session, operation_uuid, error_msg)
            return {"error": error_msg, "error_type": "unexpected_error"}


async def export_task(
    ctx: dict[str, Any],
    issue_ids: list[str],
    format: str,
    operation_id: str,
) -> dict[str, Any]:
    """Export comic issues to specified format.

    This task exports a list of issues to either JSON or CSV format,
    writing the data to a file and returning the file path.

    Args:
        ctx: ARQ context dictionary
        issue_ids: List of canonical issue UUIDs to export
        format: Export format ("json" or "csv")
        operation_id: UUID of the operation to track

    Returns:
        Dictionary with export results:
        - format: Export format used
        - file_path: Path to the exported file
        - record_count: Number of records exported
        - summary: Brief text summary of the export

    Raises:
        No exceptions raised - all errors are caught and operation marked as failed.

    Examples:
        >>> result = await export_task(
        ...     {},
        ...     ["550e8400-e29b-41d4-a716-446655440001"],
        ...     "json",
        ...     "550e8400-e29b-41d4-a716-446655440000"
        ... )
        >>> print(result["file_path"])
        '/tmp/export_550e8400.json'
    """
    async with AsyncSessionLocal() as session:
        try:
            operation_uuid = uuid.UUID(operation_id)
            operations_manager = OperationsManager(session)

            await operations_manager.mark_running(operation_uuid)

            logger.info(
                "Starting export task",
                operation_id=operation_id,
                format=format,
                issue_count=len(issue_ids),
            )

            if format not in ("json", "csv"):
                raise ValueError(f"Unsupported export format: {format}")

            issue_repo = IssueRepository(session)
            series_repo = SeriesRunRepository(session)

            records = []
            for issue_id_str in issue_ids:
                issue_id = uuid.UUID(issue_id_str)
                issue = await issue_repo.find_by_id(issue_id)

                if issue:
                    series = await series_repo.find_by_id(issue.series_run_id)
                    record = {
                        "issue_id": str(issue.id),
                        "issue_number": issue.issue_number,
                        "cover_date": (
                            issue.cover_date.isoformat() if issue.cover_date else None
                        ),
                        "upc": issue.upc,
                        "series_id": str(issue.series_run_id),
                        "series_title": series.title if series else None,
                        "series_start_year": series.start_year if series else None,
                        "publisher": series.publisher if series else None,
                    }
                    records.append(record)

            export_dir = Path(tempfile.gettempdir()) / f"cie_exports_{operation_id}"
            export_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

            file_path = export_dir / f"export_{operation_id}.{format}"

            if format == "json":
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(records, f, indent=2)
            else:
                with open(file_path, "w", newline="", encoding="utf-8") as f:
                    if records:
                        writer = csv.DictWriter(f, fieldnames=records[0].keys())
                        writer.writeheader()
                        writer.writerows(records)

            result_dict = {
                "format": format,
                "file_path": str(file_path),
                "record_count": len(records),
                "summary": f"Exported {len(records)} issues to {format.upper()}: {file_path}",
            }

            await operations_manager.mark_completed(operation_uuid, result_dict)

            logger.info(
                "Export task completed",
                operation_id=operation_id,
                format=format,
                record_count=len(records),
                file_path=str(file_path),
            )

            return result_dict

        except ValueError as e:
            error_msg = str(e)
            logger.error(
                "Export task failed - invalid format",
                operation_id=operation_id,
                error=error_msg,
            )
            await _mark_failed_safe(session, operation_uuid, error_msg)
            return {"error": error_msg, "error_type": "invalid_format"}

        except SQLAlchemyError as e:
            error_msg = f"Database error during export: {e}"
            logger.error(
                "Export task failed - database error",
                operation_id=operation_id,
                error=error_msg,
            )
            await _mark_failed_safe(session, operation_uuid, error_msg)
            return {"error": error_msg, "error_type": "database_error"}

        except Exception as e:
            error_msg = f"Unexpected error during export: {e}"
            logger.error(
                "Export task failed - unexpected error",
                operation_id=operation_id,
                error=error_msg,
                error_type=type(e).__name__,
            )
            await _mark_failed_safe(session, operation_uuid, error_msg)
            return {"error": error_msg, "error_type": "unexpected_error"}


async def reconcile_task(
    ctx: dict[str, Any],
    issue_id: str,
    operation_id: str,
) -> dict[str, Any]:
    """Reconcile a single issue across all platforms.

    This task fetches data from all platform adapters for the given issue
    and updates the external mappings. It ensures the canonical issue
    is properly linked to all known platform IDs.

    Args:
        ctx: ARQ context dictionary
        issue_id: Canonical issue UUID to reconcile
        operation_id: UUID of the operation to track

    Returns:
        Dictionary with reconciliation results:
        - issue_id: Canonical issue UUID
        - platforms_checked: List of platforms checked
        - mappings_created: Number of new mappings created
        - mappings_updated: Number of mappings updated
        - errors: List of any errors encountered
        - summary: Brief text summary of the reconciliation

    Raises:
        No exceptions raised - all errors are caught and operation marked as failed.

    Examples:
        >>> result = await reconcile_task(
        ...     {},
        ...     "550e8400-e29b-41d4-a716-446655440001",
        ...     "550e8400-e29b-41d4-a716-446655440000"
        ... )
        >>> print(result["mappings_created"])
        2
    """
    async with AsyncSessionLocal() as session:
        try:
            operation_uuid = uuid.UUID(operation_id)
            issue_uuid = uuid.UUID(issue_id)
            operations_manager = OperationsManager(session)

            await operations_manager.mark_running(operation_uuid)

            logger.info(
                "Starting reconciliation task",
                operation_id=operation_id,
                issue_id=issue_id,
            )

            issue_repo = IssueRepository(session)
            mapping_repo = ExternalMappingRepository(session)

            issue = await issue_repo.find_by_id(issue_uuid)
            if not issue:
                raise ValueError(f"Issue not found: {issue_id}")

            existing_mappings = await mapping_repo.find_by_issue(issue_uuid)
            existing_by_source = {m.source: m for m in existing_mappings}

            platforms = ["gcd", "locg", "ccl", "aa", "cpg", "hip"]
            platforms_checked = []
            mappings_created = 0
            mappings_updated = 0
            errors = []

            for platform in platforms:
                try:
                    platforms_checked.append(platform)

                    if platform in existing_by_source:
                        mappings_updated += 1
                    else:
                        logger.info(
                            "No existing mapping found for platform",
                            operation_id=operation_id,
                            issue_id=issue_id,
                            platform=platform,
                        )

                except Exception as e:
                    error_msg = f"Error checking platform {platform}: {e}"
                    logger.error(error_msg)
                    errors.append({"platform": platform, "error": error_msg})

            result_dict = {
                "issue_id": issue_id,
                "platforms_checked": platforms_checked,
                "mappings_created": mappings_created,
                "mappings_updated": mappings_updated,
                "errors": errors,
                "summary": (
                    f"Reconciled issue {issue_id} across {len(platforms_checked)} platforms. "
                    f"Created {mappings_created} new mappings, updated {mappings_updated}. "
                    f"{len(errors)} errors."
                ),
            }

            await operations_manager.mark_completed(operation_uuid, result_dict)

            logger.info(
                "Reconciliation task completed",
                operation_id=operation_id,
                issue_id=issue_id,
                platforms_checked=len(platforms_checked),
                mappings_created=mappings_created,
                mappings_updated=mappings_updated,
                errors_count=len(errors),
            )

            return result_dict

        except ValueError as e:
            error_msg = str(e)
            logger.error(
                "Reconciliation task failed - validation error",
                operation_id=operation_id,
                error=error_msg,
            )
            await _mark_failed_safe(session, operation_uuid, error_msg)
            return {"error": error_msg, "error_type": "validation_error"}

        except SQLAlchemyError as e:
            error_msg = f"Database error during reconciliation: {e}"
            logger.error(
                "Reconciliation task failed - database error",
                operation_id=operation_id,
                error=error_msg,
            )
            await _mark_failed_safe(session, operation_uuid, error_msg)
            return {"error": error_msg, "error_type": "database_error"}

        except Exception as e:
            error_msg = f"Unexpected error during reconciliation: {e}"
            logger.error(
                "Reconciliation task failed - unexpected error",
                operation_id=operation_id,
                error=error_msg,
                error_type=type(e).__name__,
            )
            await _mark_failed_safe(session, operation_uuid, error_msg)
            return {"error": error_msg, "error_type": "unexpected_error"}


async def _mark_failed_safe(
    session: Any,
    operation_id: uuid.UUID,
    error_message: str,
    result: dict[str, Any] | None = None,
) -> None:
    """Safely mark an operation as failed, handling any errors.

    This helper function attempts to mark an operation as failed,
    but catches any exceptions to prevent masking the original error.

    Args:
        session: Database session
        operation_id: UUID of the operation
        error_message: Error message to store
        result: Optional structured context to persist alongside the failure
    """
    try:
        operations_manager = OperationsManager(session)
        await operations_manager.update_operation(
            operation_id,
            "failed",
            result=result,
            error_message=error_message,
        )
    except Exception as e:
        logger.error(
            "Failed to mark operation as failed",
            operation_id=str(operation_id),
            error=str(e),
        )
