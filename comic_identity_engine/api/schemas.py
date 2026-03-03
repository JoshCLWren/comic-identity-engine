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
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "file_path": "/uploads/collections/clz_collection_2024.csv",
                }
            ]
        }
    )

    file_path: str = Field(
        ...,
        description="Path to the uploaded CLZ collection CSV file",
        examples=["/uploads/collections/clz_collection_2024.csv"],
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
        ...,
        description="Mapping of platform identifiers to issue URLs",
        examples=[{"gcd": "https://www.comics.org/issue/12345/"}],
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
