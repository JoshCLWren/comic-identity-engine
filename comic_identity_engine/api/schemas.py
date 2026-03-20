"""Pydantic request/response schemas for Comic Identity Engine HTTP API.

This module provides Pydantic v2 schemas for API request validation and
response serialization. All schemas follow AIP-151 for long-running operations.

SOURCE: OpenAPI schema definitions
USAGE:
    from comic_identity_engine.api.schemas import (
        ResolveIdentityRequest,
        IdentityResolutionResponse,
        OperationResponse,
    )
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Request Schemas
# =============================================================================


class ResolveIdentityRequest(BaseModel):
    """Request to resolve a single comic identity from a URL.

    Attributes:
        url: URL to a comic issue on any supported platform
        force: Skip existing mapping cache and always fetch from platform
        clear_mappings: Delete all external mappings for this source_issue_id before searching
        dry_run: Show what would happen without executing the search
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "url": "https://www.comics.org/issue/12345/",
                },
                {
                    "url": "https://leagueofcomicgeeks.com/comic/12345678/x-men-1",
                },
            ]
        }
    )

    url: str = Field(
        ...,
        description="URL to a comic issue on any supported platform (GCD, LoCG, CCL, CLZ, AA, CPG, HipComic)",
        examples=["https://www.comics.org/issue/12345/"],
    )
    force: bool = Field(
        default=False,
        description="Skip existing mapping cache and always fetch from platform (for debugging)",
        examples=[False],
    )
    clear_mappings: Optional[str] = Field(
        default=None,
        description="Delete all external mappings for this source_issue_id before searching",
        examples=[None],
    )
    dry_run: bool = Field(
        default=False,
        description="Show what would happen without executing the search",
        examples=[False],
    )


class BulkResolveRequest(BaseModel):
    """Request to resolve multiple comic identities from URLs.

    Attributes:
        urls: List of URLs to comic issues on supported platforms
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "urls": [
                        "https://www.comics.org/issue/12345/",
                        "https://leagueofcomicgeeks.com/comic/12345678/x-men-1",
                    ],
                }
            ]
        }
    )

    urls: list[str] = Field(
        ...,
        description="List of URLs to comic issues on supported platforms",
        examples=[["https://www.comics.org/issue/12345/"]],
        min_length=1,
        max_length=1000,
    )


class ImportClzRequest(BaseModel):
    """Request to import a CLZ collection CSV file.

    Attributes:
        file_path: Path to the uploaded CSV file
        retry_failed_only: Requeue only rows that previously failed for this file
        force: Clear all existing results and reprocess all rows
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "file_path": "/uploads/collections/clz_collection_2024.csv",
                    "retry_failed_only": True,
                    "force": False,
                }
            ]
        }
    )

    file_path: str = Field(
        ...,
        description="Path to the uploaded CLZ collection CSV file",
        examples=["/uploads/collections/clz_collection_2024.csv"],
    )
    retry_failed_only: bool = Field(
        default=False,
        description="Requeue failed rows from an existing same-file import without reposting resolved work",
        examples=[False],
    )
    force: bool = Field(
        default=False,
        description="Force reprocessing by clearing all existing row results",
        examples=[False],
    )


# =============================================================================
# Response Schemas
# =============================================================================


class HealthResponse(BaseModel):
    """Health check response.

    Attributes:
        status: Service health status
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"status": "healthy"},
                {"status": "degraded"},
            ]
        }
    )

    status: str = Field(
        ...,
        description="Service health status (healthy, degraded, unhealthy)",
        examples=["healthy"],
    )


class IdentityResolutionResponse(BaseModel):
    """Response for identity resolution request.

    Attributes:
        canonical_uuid: UUID of the canonical issue
        confidence: Confidence score (0.0-1.0)
        explanation: Human-readable explanation of the match
        platform_urls: URLs to the issue on various platforms
        platform_status: Status of cross-platform search for each platform
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "canonical_uuid": "550e8400-e29b-41d4-a716-446655440000",
                    "confidence": 0.95,
                    "explanation": "Matched by series + issue + year: X-Men (1991) #1",
                    "platform_urls": {
                        "gcd": "https://www.comics.org/issue/12345/",
                        "locg": "https://leagueofcomicgeeks.com/comic/12345678/x-men-1",
                    },
                    "platform_status": {
                        "gcd": "found",
                        "locg": "found",
                        "aa": "not_found",
                        "ccl": "failed",
                        "cpg": "not_found",
                        "hip": "searching",
                    },
                }
            ]
        }
    )

    canonical_uuid: UUID = Field(
        ...,
        description="UUID of the canonical issue in the system",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )

    confidence: float = Field(
        ...,
        description="Confidence score for the match (0.0-1.0)",
        ge=0.0,
        le=1.0,
        examples=[0.95],
    )

    explanation: str = Field(
        ...,
        description="Human-readable explanation of how the match was determined",
        examples=["Matched by series + issue + year: X-Men (1991) #1"],
    )

    platform_urls: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of platform identifiers to issue URLs",
        examples=[{"gcd": "https://www.comics.org/issue/12345/"}],
    )

    platform_status: dict[str, str] = Field(
        default_factory=dict,
        description="Status of cross-platform search for each platform (searching/found/failed/not_found)",
        examples=[
            {
                "gcd": "found",
                "locg": "found",
                "aa": "not_found",
                "ccl": "failed",
                "cpg": "not_found",
                "hip": "searching",
            }
        ],
    )


class OperationResponse(BaseModel):
    """AIP-151 compliant long-running operation response.

    This schema follows the AIP-151 (https://google.aip.dev/151) specification
    for representing the status of long-running operations.

    Attributes:
        name: Unique identifier for this operation (format: operations/{operation_id})
        done: Whether the operation has completed
        metadata: Operation-specific metadata (progress, input data, etc.)
        error: Error details if the operation failed
        response: Result data if the operation succeeded
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "operations/550e8400-e29b-41d4-a716-446655440000",
                    "done": False,
                    "metadata": {
                        "progress": 0.45,
                        "total_urls": 100,
                        "processed_urls": 45,
                    },
                },
                {
                    "name": "operations/550e8400-e29b-41d4-a716-446655440000",
                    "done": True,
                    "response": {
                        "results": [
                            {
                                "canonical_uuid": "550e8400-e29b-41d4-a716-446655440001",
                                "confidence": 0.95,
                            }
                        ],
                    },
                },
            ]
        }
    )

    name: str = Field(
        ...,
        description="Unique identifier for this operation (format: operations/{operation_id})",
        examples=["operations/550e8400-e29b-41d4-a716-446655440000"],
        pattern=r"^operations/[a-f0-9-]+$",
    )

    done: bool = Field(
        ...,
        description="Whether the operation has completed (True if done, False if still running)",
        examples=[False, True],
    )

    metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Operation-specific metadata (progress, input data, timestamps, etc.)",
        examples=[{"progress": 0.45, "total_urls": 100, "processed_urls": 45}],
    )

    error: Optional[dict[str, Any]] = Field(
        default=None,
        description="Error details if the operation failed (AIP-193 format)",
        examples=[{"code": 3, "message": "Invalid URL format", "details": []}],
    )

    response: Optional[dict[str, Any]] = Field(
        default=None,
        description="Result data if the operation succeeded (only present when done=True and no error)",
        examples=[
            {"results": [{"canonical_uuid": "550e8400-e29b-41d4-a716-446655440001"}]}
        ],
    )


class JobStatusResponse(BaseModel):
    """Detailed job status response for monitoring operations.

    Attributes:
        operation_id: UUID of the operation
        status: Current operation status
        progress: Progress percentage (0.0-1.0)
        created_at: When the operation was created
        updated_at: When the operation was last updated
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "operation_id": "550e8400-e29b-41d4-a716-446655440000",
                    "status": "running",
                    "progress": 0.45,
                    "created_at": "2024-01-15T10:30:00Z",
                    "updated_at": "2024-01-15T10:35:00Z",
                },
                {
                    "operation_id": "550e8400-e29b-41d4-a716-446655440000",
                    "status": "completed",
                    "progress": 1.0,
                    "created_at": "2024-01-15T10:30:00Z",
                    "updated_at": "2024-01-15T10:40:00Z",
                },
            ]
        }
    )

    operation_id: UUID = Field(
        ...,
        description="UUID of the operation",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )

    status: str = Field(
        ...,
        description="Current operation status (pending, running, completed, failed)",
        examples=["running"],
        pattern=r"^(pending|running|completed|failed)$",
    )

    progress: Optional[float] = Field(
        default=None,
        description="Progress percentage (0.0-1.0), null if indeterminate",
        ge=0.0,
        le=1.0,
        examples=[0.45],
    )

    created_at: datetime = Field(
        ...,
        description="When the operation was created (ISO 8601 format)",
        examples=["2024-01-15T10:30:00Z"],
    )

    updated_at: datetime = Field(
        ...,
        description="When the operation was last updated (ISO 8601 format)",
        examples=["2024-01-15T10:35:00Z"],
    )


class MarkIncorrectRequest(BaseModel):
    """Request to mark a mapping as incorrect.

    Attributes:
        issue_id: UUID of the canonical issue
        source: Platform source (gcd, locg, ccl, aa, cpg, hip, clz)
        source_issue_id: The incorrect source issue ID
        correction_type: Type of correction (wrong_issue, wrong_series, wrong_variant, should_not_match)
        notes: Optional user notes explaining the correction
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "issue_id": "550e8400-e29b-41d4-a716-446655440000",
                    "source": "gcd",
                    "source_issue_id": "12345",
                    "correction_type": "wrong_issue",
                    "notes": "This is actually issue #2, not #1",
                }
            ]
        }
    )

    issue_id: UUID = Field(
        ...,
        description="UUID of the canonical issue",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    source: str = Field(
        ...,
        description="Platform source (gcd, locg, ccl, aa, cpg, hip, clz)",
        examples=["gcd"],
        pattern=r"^(gcd|locg|ccl|aa|cpg|hip|clz)$",
    )
    source_issue_id: str = Field(
        ...,
        description="The incorrect source issue ID",
        examples=["12345"],
    )
    correction_type: str = Field(
        ...,
        description="Type of correction",
        examples=["wrong_issue"],
        pattern=r"^(wrong_issue|wrong_series|wrong_variant|should_not_match)$",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional user notes explaining the correction",
        examples=["This is actually issue #2, not #1"],
    )


class ProvideCorrectRequest(BaseModel):
    """Request to provide the correct mapping ID.

    Attributes:
        issue_id: UUID of the canonical issue
        source: Platform source (gcd, locg, ccl, aa, cpg, hip, clz)
        incorrect_source_issue_id: The incorrect source issue ID
        correct_source_issue_id: The correct source issue ID
        notes: Optional user notes
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "issue_id": "550e8400-e29b-41d4-a716-446655440000",
                    "source": "gcd",
                    "incorrect_source_issue_id": "12345",
                    "correct_source_issue_id": "12346",
                    "notes": "Corrected to issue #2",
                }
            ]
        }
    )

    issue_id: UUID = Field(
        ...,
        description="UUID of the canonical issue",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    source: str = Field(
        ...,
        description="Platform source (gcd, locg, ccl, aa, cpg, hip, clz)",
        examples=["gcd"],
        pattern=r"^(gcd|locg|ccl|aa|cpg|hip|clz)$",
    )
    incorrect_source_issue_id: str = Field(
        ...,
        description="The incorrect source issue ID",
        examples=["12345"],
    )
    correct_source_issue_id: str = Field(
        ...,
        description="The correct source issue ID",
        examples=["12346"],
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional user notes",
        examples=["Corrected to issue #2"],
    )


class CorrectionResponse(BaseModel):
    """Response for correction operations.

    Attributes:
        id: UUID of the correction record
        issue_id: UUID of the canonical issue
        source: Platform source
        correction_type: Type of correction
        created_at: When the correction was created
    """

    id: UUID = Field(
        ...,
        description="UUID of the correction record",
        examples=["550e8400-e29b-41d4-a716-446655440001"],
    )
    issue_id: UUID = Field(
        ...,
        description="UUID of the canonical issue",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    source: str = Field(
        ...,
        description="Platform source",
        examples=["gcd"],
    )
    correction_type: str = Field(
        ...,
        description="Type of correction",
        examples=["wrong_issue"],
    )
    created_at: datetime = Field(
        ...,
        description="When the correction was created",
        examples=["2024-01-15T10:30:00Z"],
    )


class CorrectionHistoryItem(BaseModel):
    """Single item in correction history.

    Attributes:
        id: UUID of the correction record
        source: Platform source
        original_source_issue_id: The original (incorrect) ID
        correct_source_issue_id: The correct ID (if provided)
        correction_type: Type of correction
        user_notes: User-provided notes
        created_at: When the correction was created
    """

    id: UUID
    source: str
    original_source_issue_id: str
    correct_source_issue_id: Optional[str]
    correction_type: str
    user_notes: Optional[str]
    created_at: datetime


class CorrectionHistoryResponse(BaseModel):
    """Correction history for an issue.

    Attributes:
        issue_id: UUID of the canonical issue
        corrections: List of corrections
    """

    issue_id: UUID
    corrections: list[CorrectionHistoryItem]


class CorrectionStatsResponse(BaseModel):
    """Statistics about corrections.

    Attributes:
        total_corrections: Total number of corrections
        pending_review: Number pending review
        reviewed: Number reviewed
        applied: Number applied to algorithm
        rejected: Number rejected
        by_platform: Count by platform
        by_correction_type: Count by correction type
        by_review_status: Count by review status
    """

    total_corrections: int
    pending_review: int
    reviewed: int
    applied: int
    rejected: int
    by_platform: dict[str, int]
    by_correction_type: dict[str, int]
    by_review_status: dict[str, int]


class PlatformAccuracyResponse(BaseModel):
    """Accuracy metrics for a platform.

    Attributes:
        platform: Platform code
        total_mappings: Total mappings for this platform
        accurate_mappings: Number of accurate mappings
        inaccurate_mappings: Number marked as inaccurate
        corrected_mappings: Number that have been corrected
        accuracy_rate: Percentage of accurate mappings
        correction_rate: Percentage of corrected mappings
    """

    platform: str
    total_mappings: int
    accurate_mappings: int
    inaccurate_mappings: int
    corrected_mappings: int
    accuracy_rate: float
    correction_rate: float


class CorrectionPatternResponse(BaseModel):
    """Identified pattern from corrections.

    Attributes:
        pattern_type: Type of pattern identified
        description: Human-readable description
        count: Number of occurrences
        examples: Example corrections for this pattern
    """

    pattern_type: str
    description: str
    count: int
    examples: list[dict[str, Any]]


class UpdateReviewStatusRequest(BaseModel):
    """Request to update correction review status.

    Attributes:
        status: New review status (pending, reviewed, applied, rejected)
        review_notes: Optional notes about the review
    """

    status: str = Field(
        ...,
        description="New review status",
        examples=["reviewed"],
        pattern=r"^(pending|reviewed|applied|rejected)$",
    )
    review_notes: Optional[str] = Field(
        default=None,
        description="Optional notes about the review",
        examples=["Verified correction, applied to matching algorithm"],
    )


class CorrectionListItem(BaseModel):
    """Single correction in list view.

    Attributes:
        id: Correction UUID
        issue_id: Canonical issue UUID
        series_title: Series title
        issue_number: Issue number
        source: Platform source
        original_source_issue_id: Original (incorrect) ID
        correct_source_issue_id: Correct ID (if provided)
        correction_type: Type of correction
        review_status: Review status
        created_at: When correction was created
    """

    id: UUID
    issue_id: UUID
    series_title: str
    issue_number: str
    source: str
    original_source_issue_id: str
    correct_source_issue_id: Optional[str]
    correction_type: str
    review_status: str
    created_at: datetime
