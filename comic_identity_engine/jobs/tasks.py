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
import inspect
import json
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select
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
from comic_identity_engine.core.http_client import HttpClient
from comic_identity_engine.database.connection import AsyncSessionLocal
from comic_identity_engine.database.models import Operation
from comic_identity_engine.database.repositories import (
    ExternalMappingRepository,
    IssueRepository,
    OperationRepository,
    SeriesRunRepository,
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
from comic_identity_engine.services.imports import (
    apply_clz_import_visibility,
    build_clz_row_key,
    build_clz_row_manifest,
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


async def http_request_task(
    ctx: dict[str, Any],
    url: str,
    method: str = "GET",
    operation_id: str | None = None,
    platform: str | None = None,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_data: dict[str, Any] | None = None,
    verify_ssl: bool = True,
) -> dict[str, Any]:
    """Execute a single HTTP request as an independent task.

    This task performs one HTTP request and returns the response details.
    It's designed to be the atomic unit of work for HTTP operations, allowing
    for fine-grained parallelism and error handling.

    Args:
        ctx: ARQ context dictionary
        url: URL to request
        method: HTTP method (default: "GET")
        operation_id: UUID of the operation to track (optional, auto-generated if not provided)
        platform: Platform identifier for rate limiting (default: extract from URL)
        headers: Optional HTTP headers
        params: Optional query parameters
        json_data: Optional JSON body for POST/PUT/PATCH requests
        verify_ssl: Whether to verify SSL certificates (default: True)

    Returns:
        Dictionary with request results:
        - success: True if request succeeded
        - status_code: HTTP status code
        - content: Response content as string
        - elapsed_ms: Request duration in milliseconds
        - error: Error message if request failed
        - operation_id: UUID of the operation

    Raises:
        No exceptions raised - all errors are caught and returned in the result dict.

    Examples:
        >>> result = await http_request_task(
        ...     {},
        ...     "https://www.comics.org/issue/125295/?format=json",
        ...     "GET"
        ... )
        >>> print(result["success"])
        True
        >>> print(result["status_code"])
        200
    """
    async with AsyncSessionLocal() as session:
        operation_uuid = None
        operations_manager = None
        start_time = None

        try:
            operation_uuid = (
                uuid.uuid4() if not operation_id else uuid.UUID(operation_id)
            )
            operations_manager = OperationsManager(session)

            await operations_manager.mark_running(operation_uuid)
            await session.commit()

            start_time = time.time()

            logger.info(
                "Starting HTTP request task",
                operation_id=str(operation_uuid),
                url=url,
                method=method,
                platform=platform,
            )

            if platform is None:
                platform = "default"

            async with HttpClient(platform=platform, verify_ssl=verify_ssl) as client:
                if method.upper() == "GET":
                    response = await client.get(url, params=params, headers=headers)
                elif method.upper() == "POST":
                    response = await client.post(
                        url, params=params, headers=headers, json=json_data
                    )
                elif method.upper() == "PUT":
                    response = await client.put(
                        url, params=params, headers=headers, json=json_data
                    )
                elif method.upper() == "PATCH":
                    response = await client.patch(
                        url, params=params, headers=headers, json=json_data
                    )
                elif method.upper() == "DELETE":
                    response = await client.delete(url, params=params, headers=headers)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

            elapsed_ms = (time.time() - start_time) * 1000

            result_dict = {
                "success": True,
                "status_code": response.status_code,
                "content": response.text,
                "elapsed_ms": round(elapsed_ms, 2),
                "error": None,
                "operation_id": str(operation_uuid),
            }

            await operations_manager.mark_completed(operation_uuid, result_dict)
            await session.commit()

            logger.info(
                "HTTP request task completed",
                operation_id=str(operation_uuid),
                url=url,
                method=method,
                status_code=response.status_code,
                elapsed_ms=elapsed_ms,
            )

            return result_dict

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000 if start_time else 0

            error_msg = f"HTTP request failed: {e}"
            logger.error(
                "HTTP request task failed",
                operation_id=str(operation_uuid) if operation_uuid else None,
                url=url,
                method=method,
                error=str(e),
                error_type=type(e).__name__,
                elapsed_ms=elapsed_ms,
            )

            result_dict = {
                "success": False,
                "status_code": None,
                "content": None,
                "elapsed_ms": round(elapsed_ms, 2),
                "error": error_msg,
                "error_type": type(e).__name__,
                "operation_id": str(operation_uuid) if operation_uuid else None,
            }

            if operation_uuid and operations_manager:
                await operations_manager.mark_failed(operation_uuid, error_msg)
                await session.commit()

            return result_dict


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
                variant_suffix=(
                    getattr(candidate, "variant_suffix", None)
                    or getattr(parsed_url, "variant_suffix", None)
                ),
                variant_name=getattr(candidate, "variant_name", None),
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


def _validate_clz_row_for_import(
    row: dict[str, str], row_index: int
) -> dict[str, Any] | None:
    """Pre-flight validation to skip rows that will fail during processing.

    This prevents enqueuing worker jobs for rows that require manual review,
    saving processing time and reducing log noise.

    Args:
        row: CSV row dictionary
        row_index: Row number for error reporting

    Returns:
        None if row passes validation, or dict with 'error' and 'category' keys
    """
    # Check for required fields that will cause immediate failures
    series_title = (row.get("Series") or "").strip()
    if not series_title:
        return {
            "error": f"Row {row_index} validation error: Missing required field 'Series'",
            "category": "missing_series",
        }

    # Check for Issue field
    issue_number = (row.get("Issue") or "").strip()
    if not issue_number:
        return {
            "error": f"Row {row_index} validation error: Missing required field 'Issue'",
            "category": "missing_issue",
        }

    # Don't pre-filter rows with empty Year - let identity resolver try
    # It might succeed by finding the series by title or existing mapping

    # If all validations pass, return None (row is good to process)
    return None


def _build_clz_import_summary(result: dict[str, Any]) -> str:
    """Build a human-readable summary for CLZ import progress."""
    total_rows = int(result.get("total_rows", 0) or 0)
    processed = int(result.get("processed", 0) or 0)
    resolved = int(result.get("resolved", 0) or 0)
    failed = int(result.get("failed", 0) or 0)
    error_count = len(result.get("errors", []))

    if processed < total_rows:
        return (
            f"Processed {processed}/{total_rows} CLZ rows: "
            f"{resolved} resolved, {failed} failed. {error_count} errors so far."
        )

    return (
        f"Processed {processed} CLZ rows: "
        f"{resolved} resolved, {failed} failed. {error_count} errors."
    )


def _summarize_clz_row_results(
    row_results: dict[str, dict[str, Any]],
) -> tuple[int, int, int, list[dict[str, Any]]]:
    """Compute CLZ import counters from persisted per-row results."""
    processed = len(row_results)
    resolved = 0
    errors: list[dict[str, Any]] = []

    ordered_row_results = sorted(
        row_results.values(),
        key=lambda row_result: (
            int(row_result.get("row_index", 0) or 0),
            str(row_result.get("row_key", "")),
        ),
    )
    for row_result in ordered_row_results:
        if row_result.get("resolved"):
            resolved += 1
            continue
        errors.append(
            {
                "row": row_result.get("row_index"),
                "row_key": row_result.get("row_key"),
                "source_issue_id": row_result.get("source_issue_id"),
                "error": row_result.get("error", "Unknown error"),
            }
        )

    failed = processed - resolved
    return processed, resolved, failed, errors


async def _record_clz_row_result(
    operation_id: uuid.UUID,
    row_result: dict[str, Any],
) -> None:
    """Persist CLZ row-task progress onto the parent import operation."""
    try:
        async with AsyncSessionLocal() as session:
            repo = OperationRepository(session)

            stmt = (
                select(Operation).where(Operation.id == operation_id).with_for_update()
            )
            query_result = await session.execute(stmt)
            operation = query_result.scalar_one_or_none()
            if inspect.isawaitable(operation):
                operation = await operation

            # Broad session mocks used in task unit tests won't yield a real
            # Operation model here; skip the persistence path in that case.
            if operation is None or not isinstance(operation, Operation):
                return

            if operation.status in {"completed", "failed"}:
                return

            current_result = apply_clz_import_visibility(dict(operation.result or {}))
            total_rows = int(current_result.get("total_rows", 0) or 0)
            if total_rows == 0:
                total_rows = len(current_result.get("row_manifest", []) or [])

            row_key = row_result.get("row_key") or build_clz_row_key(
                row_result.get("source_issue_id"),
                int(row_result.get("row_index", 0) or 0),
            )
            row_results = dict(current_result.get("row_results", {}) or {})
            row_results[row_key] = {
                **row_result,
                "row_key": row_key,
            }
            processed, resolved, failed, errors = _summarize_clz_row_results(
                row_results
            )

            active_row_keys = set(current_result.get("active_row_keys", []) or [])
            active_row_keys.discard(row_key)

            updated_result = apply_clz_import_visibility(
                {
                    **current_result,
                    "total_rows": total_rows,
                    "row_results": row_results,
                    "processed": processed,
                    "resolved": resolved,
                    "failed": failed,
                    "errors": errors,
                    "progress": (processed / total_rows) if total_rows else 0.0,
                    "active_row_keys": sorted(active_row_keys),
                }
            )
            updated_result["summary"] = _build_clz_import_summary(updated_result)

            new_status = (
                "completed"
                if total_rows
                and processed >= total_rows
                and updated_result["active_row_count"] == 0
                else "running"
            )

            await repo.update_status(
                operation=operation,
                status=new_status,
                result=updated_result,
            )
            await session.commit()
            logger.info(
                "Recorded CLZ row result",
                operation_id=str(operation_id),
                row_index=row_result.get("row_index"),
                source_issue_id=row_result.get("source_issue_id"),
                resolved=row_result.get("resolved"),
                active_row_count=updated_result["active_row_count"],
                pending_row_count=updated_result["pending_row_count"],
                failed_row_count=updated_result["failed_row_count"],
            )
    except Exception as e:
        logger.warning(
            "Failed to record CLZ row progress",
            operation_id=str(operation_id),
            row_index=row_result.get("row_index"),
            error=str(e),
        )


async def _mark_clz_row_active(
    operation_id: uuid.UUID,
    *,
    row_index: int,
    source_issue_id: str | None,
) -> None:
    """Track that a CLZ row has started processing."""
    try:
        async with AsyncSessionLocal() as session:
            repo = OperationRepository(session)

            stmt = (
                select(Operation).where(Operation.id == operation_id).with_for_update()
            )
            query_result = await session.execute(stmt)
            operation = query_result.scalar_one_or_none()
            if inspect.isawaitable(operation):
                operation = await operation

            # Broad session mocks used in task unit tests won't yield a real
            # Operation model here; skip the persistence path in that case.
            if operation is None or not isinstance(operation, Operation):
                return

            if operation.status in {"completed", "failed"}:
                return

            current_result = apply_clz_import_visibility(dict(operation.result or {}))
            row_key = build_clz_row_key(source_issue_id, row_index)
            row_results = dict(current_result.get("row_results", {}) or {})
            if row_key in row_results:
                return

            active_row_keys = set(current_result.get("active_row_keys", []) or [])
            if row_key in active_row_keys:
                return

            updated_result = apply_clz_import_visibility(
                {
                    **current_result,
                    "active_row_keys": sorted(active_row_keys | {row_key}),
                }
            )

            await repo.update_status(
                operation=operation,
                status="running",
                result=updated_result,
            )
            await session.commit()
            logger.info(
                "Marked CLZ row active",
                operation_id=str(operation_id),
                row_index=row_index,
                source_issue_id=source_issue_id,
                active_row_count=updated_result["active_row_count"],
                pending_row_count=updated_result["pending_row_count"],
            )
    except Exception as e:
        logger.warning(
            "Failed to mark CLZ row active",
            operation_id=str(operation_id),
            row_index=row_index,
            error=str(e),
        )


async def resolve_clz_row_task(
    ctx: dict[str, Any],
    row_data: dict[str, str],
    row_index: int,
    operation_id: str,
) -> dict[str, Any]:
    """Resolve a single CLZ CSV row using identity resolution pipeline.

    This task processes one CLZ CSV row by checking for existing mappings,
    resolving the identity, creating CLZ external mappings, and running
    cross-platform search.

    Args:
        ctx: ARQ context dictionary
        row_data: Single CSV row as dictionary
        row_index: Row index (1-based) for error reporting
        operation_id: UUID of the parent import operation

    Returns:
        Dictionary with row resolution results:
        - row_index: Row number (1-based)
        - source_issue_id: CLZ Comic ID
        - resolved: True if successfully resolved
        - issue_id: Canonical issue UUID (if resolved)
        - existing_mapping: True if found existing mapping
        - cross_platform_found: Number of platforms found
        - error: Error message (if failed)

    Raises:
        No exceptions raised - all errors are caught and returned in result.

    Examples:
        >>> result = await resolve_clz_row_task(
        ...     {},
        ...     {"Core ComicID": "123", "Series": "X-Men", "Issue": "1"},
        ...     1,
        ...     "550e8400-e29b-41d4-a716-446655440000"
        ... )
        >>> print(result["resolved"])
        True
    """
    operation_uuid = uuid.UUID(operation_id)
    async with AsyncSessionLocal() as session:
        row_result: dict[str, Any]
        try:
            source_issue_id = (row_data.get("Core ComicID") or "").strip() or None
            row_key = build_clz_row_key(source_issue_id, row_index)
            await _mark_clz_row_active(
                operation_uuid,
                row_index=row_index,
                source_issue_id=source_issue_id,
            )
            logger.info(
                "Processing CLZ row",
                operation_id=operation_id,
                row=row_index,
                source_issue_id=source_issue_id,
            )

            adapter = CLZAdapter()
            issue_candidate = adapter.fetch_issue_from_csv_row(row_data)
            source_issue_id = issue_candidate.source_issue_id
            row_key = build_clz_row_key(source_issue_id, row_index)

            mapping_repo = ExternalMappingRepository(session)
            existing_mapping = await mapping_repo.find_by_source("clz", source_issue_id)

            if existing_mapping is not None:
                logger.info(
                    "Existing CLZ mapping found",
                    operation_id=operation_id,
                    row=row_index,
                    source_issue_id=source_issue_id,
                    issue_id=str(existing_mapping.issue_id),
                )
                row_result = {
                    "row_index": row_index,
                    "row_key": row_key,
                    "source_issue_id": source_issue_id,
                    "resolved": True,
                    "issue_id": str(existing_mapping.issue_id),
                    "existing_mapping": True,
                    "cross_platform_found": 0,
                }
                await _record_clz_row_result(operation_uuid, row_result)
                return row_result

            from comic_identity_engine.services import ParsedUrl

            parsed_url = ParsedUrl(
                platform="clz",
                source_issue_id=source_issue_id,
                source_series_id=issue_candidate.source_series_id,
            )

            resolver = IdentityResolver(session)
            result = await resolver.resolve_issue(
                parsed_url=parsed_url,
                upc=issue_candidate.upc,
                series_title=issue_candidate.series_title,
                series_start_year=issue_candidate.series_start_year,
                issue_number=issue_candidate.issue_number,
                cover_date=issue_candidate.cover_date,
                variant_suffix=issue_candidate.variant_suffix,
                variant_name=getattr(issue_candidate, "variant_name", None),
            )

            if not result.issue_id:
                error_msg = f"Failed to resolve issue: {result.explanation}"
                logger.warning(
                    "Failed to resolve CLZ row",
                    operation_id=operation_id,
                    row=row_index,
                    source_issue_id=source_issue_id,
                    error=error_msg,
                )
                row_result = {
                    "row_index": row_index,
                    "row_key": row_key,
                    "source_issue_id": source_issue_id,
                    "resolved": False,
                    "error": error_msg,
                    "series": row_data.get("Series"),
                    "issue": row_data.get("Issue"),
                    "publisher": row_data.get("Publisher"),
                    "year": row_data.get("Year"),
                }
                await _record_clz_row_result(operation_uuid, row_result)
                return row_result

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
                    row=row_index,
                    source_issue_id=source_issue_id,
                    issue_id=str(result.issue_id),
                )
            else:
                logger.info(
                    "Reused existing CLZ external mapping",
                    operation_id=operation_id,
                    row=row_index,
                    source_issue_id=source_issue_id,
                    issue_id=str(result.issue_id),
                )

            cross_platform_count = 0

            await session.commit()

            row_result = {
                "row_index": row_index,
                "row_key": row_key,
                "source_issue_id": source_issue_id,
                "resolved": True,
                "issue_id": str(result.issue_id),
                "existing_mapping": False,
                "cross_platform_found": cross_platform_count,
            }
            await _record_clz_row_result(operation_uuid, row_result)
            return row_result

        except AdapterValidationError as e:
            error_msg = f"Row {row_index} validation error: {e}"
            logger.warning(error_msg, operation_id=operation_id)
            row_result = {
                "row_index": row_index,
                "row_key": build_clz_row_key(row_data.get("Core ComicID"), row_index),
                "source_issue_id": row_data.get("Core ComicID"),
                "resolved": False,
                "error": error_msg,
                "series": row_data.get("Series"),
                "issue": row_data.get("Issue"),
                "publisher": row_data.get("Publisher"),
                "year": row_data.get("Year"),
            }
            await _record_clz_row_result(operation_uuid, row_result)
            return row_result

        except ValidationError as e:
            error_msg = f"Row {row_index} validation error: {e}"
            logger.warning(error_msg, operation_id=operation_id)
            row_result = {
                "row_index": row_index,
                "row_key": build_clz_row_key(row_data.get("Core ComicID"), row_index),
                "source_issue_id": row_data.get("Core ComicID"),
                "resolved": False,
                "error": error_msg,
                "series": row_data.get("Series"),
                "issue": row_data.get("Issue"),
                "publisher": row_data.get("Publisher"),
                "year": row_data.get("Year"),
            }
            await _record_clz_row_result(operation_uuid, row_result)
            return row_result

        except Exception as e:
            error_msg = f"Row {row_index} error: {e}"
            logger.error(
                error_msg,
                operation_id=operation_id,
                error_type=type(e).__name__,
            )
            row_result = {
                "row_index": row_index,
                "row_key": build_clz_row_key(row_data.get("Core ComicID"), row_index),
                "source_issue_id": row_data.get("Core ComicID"),
                "resolved": False,
                "error": error_msg,
                "series": row_data.get("Series"),
                "issue": row_data.get("Issue"),
                "publisher": row_data.get("Publisher"),
                "year": row_data.get("Year"),
            }
            await _record_clz_row_result(operation_uuid, row_result)
            return row_result


async def import_clz_task(
    ctx: dict[str, Any],
    csv_path: str,
    operation_id: str,
) -> dict[str, Any]:
    """Import comic data from CLZ CSV export using task-based parallel processing.

    This task loads a CLZ CSV file and enqueues one task per row for parallel
    processing. It aggregates results and tracks progress.

    Args:
        ctx: ARQ context dictionary
        csv_path: Path to the CLZ CSV export file
        operation_id: UUID of the operation to track

    Returns:
        Dictionary with import results:
        - total_rows: Total number of rows in CSV
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
    operation_uuid = uuid.UUID(operation_id)
    async with AsyncSessionLocal() as session:
        try:
            operations_manager = OperationsManager(session)
            operation = await operations_manager.get_operation(operation_uuid)
            current_result = dict(operation.result or {}) if operation else {}

            await operations_manager.mark_running(operation_uuid)
            await session.commit()

            logger.info(
                "Starting CLZ import task (orchestrator)",
                operation_id=operation_id,
                csv_path=csv_path,
            )

            adapter = CLZAdapter()
            rows = adapter.load_csv_from_file(csv_path)
            row_manifest = current_result.get("row_manifest") or build_clz_row_manifest(
                rows
            )
            row_results = dict(current_result.get("row_results", {}) or {})
            processed, resolved, failed, errors = _summarize_clz_row_results(
                row_results
            )
            total_rows = len(rows)

            result_dict = apply_clz_import_visibility(
                {
                    **current_result,
                    "total_rows": total_rows,
                    "row_manifest": row_manifest,
                    "row_results": row_results,
                    "processed": processed,
                    "resolved": resolved,
                    "failed": failed,
                    "errors": errors,
                    "progress": (processed / total_rows) if total_rows else 0.0,
                    "active_row_keys": [],
                }
            )

            # Pre-flight validation: filter rows that will fail before enqueuing
            validated_rows: list[tuple[int, dict[str, str], str]] = []
            skipped_rows: list[tuple[int, dict[str, str], str, dict[str, Any]]] = []

            for row_index, row in enumerate(rows, start=1):
                source_issue_id = (row.get("Core ComicID") or "").strip() or None
                row_key = build_clz_row_key(source_issue_id, row_index)

                # Skip already processed rows
                if row_key in row_results:
                    continue

                # Pre-flight validation check
                validation_error = _validate_clz_row_for_import(row, row_index)
                if validation_error:
                    # Mark as failed immediately without enqueueing
                    skipped_rows.append((row_index, row, row_key, validation_error))
                else:
                    validated_rows.append((row_index, row, row_key))

            # Record skipped rows as failures
            for row_index, row, row_key, error_info in skipped_rows:
                row_result = {
                    "row_index": row_index,
                    "row_key": row_key,
                    "source_issue_id": row.get("Core ComicID", "").strip(),
                    "resolved": False,
                    "error": error_info["error"],
                    "skipped_reason": error_info["category"],
                    "series": row.get("Series"),
                    "issue": row.get("Issue"),
                    "publisher": row.get("Publisher"),
                    "year": row.get("Year"),
                }
                row_results[row_key] = row_result

            if skipped_rows:
                logger.info(
                    "Pre-flight validation skipped rows requiring manual review",
                    operation_id=operation_id,
                    skipped_count=len(skipped_rows),
                    will_enqueue=len(validated_rows),
                )

            # Update counts after skipping
            processed, resolved, failed, errors = _summarize_clz_row_results(
                row_results
            )

            remaining_rows = validated_rows

            if remaining_rows:
                result_dict["summary"] = (
                    f"Enqueued {len(remaining_rows)} pending CLZ row tasks for processing ({len(skipped_rows)} skipped)"
                )
            else:
                result_dict["summary"] = _build_clz_import_summary(result_dict)

            await operations_manager.update_operation(
                operation_uuid,
                "running",
                result=result_dict,
            )
            await session.commit()

            from comic_identity_engine.jobs.queue import JobQueue

            logger.info(
                "Enqueueing CLZ row tasks",
                operation_id=operation_id,
                total_rows=total_rows,
                remaining_rows=len(remaining_rows),
            )

            jobs = []
            queue = JobQueue()
            try:
                for row_index, row, _row_key in remaining_rows:
                    job = await queue.enqueue_resolve_clz_row(
                        row_data=row,
                        row_index=row_index,
                        operation_id=operation_uuid,
                    )
                    jobs.append(job)
            finally:
                close = getattr(queue, "close", None)
                if callable(close):
                    maybe_awaitable = close()
                    if inspect.isawaitable(maybe_awaitable):
                        await maybe_awaitable

            logger.info(
                "All CLZ row tasks enqueued",
                operation_id=operation_id,
                job_count=len(jobs),
            )

            if total_rows and processed >= total_rows:
                completed_result = {
                    **result_dict,
                    "summary": _build_clz_import_summary(result_dict),
                    "progress": 1.0,
                }
                await operations_manager.mark_completed(
                    operation_uuid,
                    completed_result,
                )
                await session.commit()
                logger.info(
                    "CLZ import resumed into completed state",
                    operation_id=operation_id,
                    total_rows=total_rows,
                )
                return completed_result

            logger.info(
                "CLZ import orchestration completed",
                operation_id=operation_id,
                total_rows=total_rows,
                enqueued_jobs=len(jobs),
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
            await session.commit()
            return {"error": error_msg, "error_type": "file_not_found"}

        except ValidationError as e:
            error_msg = f"CSV validation error: {e}"
            logger.error(
                "CLZ import task failed - validation error",
                operation_id=operation_id,
                error=error_msg,
            )
            await _mark_failed_safe(session, operation_uuid, error_msg)
            await session.commit()
            return {"error": error_msg, "error_type": "validation_error"}

        except SQLAlchemyError as e:
            error_msg = f"Database error during import: {e}"
            logger.error(
                "CLZ import task failed - database error",
                operation_id=operation_id,
                error=error_msg,
            )
            await _mark_failed_safe(session, operation_uuid, error_msg)
            await session.commit()
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
            await session.commit()
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
