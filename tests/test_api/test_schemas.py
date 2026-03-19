"""Tests for api/schemas.py - API request/response validation."""

import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

# Import schemas module directly without going through package __init__.py
# This avoids loading the full API dependencies
schemas_path = (
    Path(__file__).parent.parent.parent / "comic_identity_engine" / "api" / "schemas.py"
)
spec = importlib.util.spec_from_file_location("schemas", schemas_path)
assert spec is not None
schemas = importlib.util.module_from_spec(spec)
sys.modules["schemas"] = schemas
assert spec.loader is not None
spec.loader.exec_module(schemas)

BulkResolveRequest = schemas.BulkResolveRequest
HealthResponse = schemas.HealthResponse
IdentityResolutionResponse = schemas.IdentityResolutionResponse
ImportClzRequest = schemas.ImportClzRequest
JobStatusResponse = schemas.JobStatusResponse
OperationResponse = schemas.OperationResponse
ResolveIdentityRequest = schemas.ResolveIdentityRequest


class TestResolveIdentityRequest:
    """Tests for ResolveIdentityRequest schema."""

    def test_valid_url_passes(self):
        """Valid URL should be accepted."""
        request = ResolveIdentityRequest(url="https://www.comics.org/issue/12345/")
        assert request.url == "https://www.comics.org/issue/12345/"

    def test_valid_url_various_platforms(self):
        """Valid URLs from various platforms should be accepted."""
        urls = [
            "https://www.comics.org/issue/12345/",
            "https://leagueofcomicgeeks.com/comic/12345678/x-men-1",
            "https://comicbookrealm.com/series/12345/0/x-men-1991",
            "https://www.comicspriceguide.com/comic-book/12345",
            "https://atomicavenue.com/Title/12345/X-Men",
            "https://www.hipcomic.com/listing/x-men-1/12345",
            "https://clz.com/comics/issue/12345",
        ]
        for url in urls:
            request = ResolveIdentityRequest(url=url)
            assert request.url == url

    def test_empty_url_allowed(self):
        """Empty URL is allowed (schema has no min_length constraint)."""
        request = ResolveIdentityRequest(url="")
        assert request.url == ""

    def test_whitespace_only_url_allowed(self):
        """Whitespace-only URL is allowed (schema has no constraint)."""
        request = ResolveIdentityRequest(url="   ")
        assert request.url == "   "

    def test_missing_url_fails(self):
        """Missing URL field should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            ResolveIdentityRequest()
        assert "url" in str(exc_info.value)

    def test_url_with_special_characters(self):
        """URL with special characters should be accepted."""
        request = ResolveIdentityRequest(
            url="https://example.com/comic/x-men-vol-1-1-cgc-9.8"
        )
        assert request.url == "https://example.com/comic/x-men-vol-1-1-cgc-9.8"


class TestBulkResolveRequest:
    """Tests for BulkResolveRequest schema."""

    def test_valid_list_of_urls_passes(self):
        """Valid list of URLs should be accepted."""
        request = BulkResolveRequest(
            urls=[
                "https://www.comics.org/issue/12345/",
                "https://leagueofcomicgeeks.com/comic/12345678/x-men-1",
            ]
        )
        assert len(request.urls) == 2
        assert request.urls[0] == "https://www.comics.org/issue/12345/"

    def test_single_url_in_list_passes(self):
        """Single URL in list should be accepted."""
        request = BulkResolveRequest(urls=["https://www.comics.org/issue/12345/"])
        assert len(request.urls) == 1

    def test_empty_list_fails(self):
        """Empty list should fail validation (min_length=1)."""
        with pytest.raises(ValidationError) as exc_info:
            BulkResolveRequest(urls=[])
        assert "urls" in str(exc_info.value)

    def test_too_many_urls_fails(self):
        """More than 1000 URLs should fail validation (max_length=1000)."""
        urls = [f"https://example.com/{i}" for i in range(1001)]
        with pytest.raises(ValidationError) as exc_info:
            BulkResolveRequest(urls=urls)
        assert "urls" in str(exc_info.value)

    def test_exactly_1000_urls_passes(self):
        """Exactly 1000 URLs should be accepted."""
        urls = [f"https://example.com/{i}" for i in range(1000)]
        request = BulkResolveRequest(urls=urls)
        assert len(request.urls) == 1000

    def test_missing_urls_fails(self):
        """Missing urls field should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            BulkResolveRequest()
        assert "urls" in str(exc_info.value)

    def test_mixed_valid_urls(self):
        """Mixed valid URLs from different platforms should be accepted."""
        request = BulkResolveRequest(
            urls=[
                "https://www.comics.org/issue/12345/",
                "https://leagueofcomicgeeks.com/comic/12345678/x-men-1",
                "https://comicbookrealm.com/series/12345/0/x-men-1991",
            ]
        )
        assert len(request.urls) == 3


class TestImportClzRequest:
    """Tests for ImportClzRequest schema."""

    def test_valid_file_path_passes(self):
        """Valid file path should be accepted."""
        request = ImportClzRequest(
            file_path="/uploads/collections/clz_collection_2024.csv"
        )
        assert request.file_path == "/uploads/collections/clz_collection_2024.csv"
        assert request.retry_failed_only is True

    def test_relative_path_passes(self):
        """Relative path should be accepted."""
        request = ImportClzRequest(file_path="uploads/collection.csv")
        assert request.file_path == "uploads/collection.csv"

    def test_path_with_special_chars_passes(self):
        """Path with special characters should be accepted."""
        request = ImportClzRequest(file_path="/uploads/collection (backup).csv")
        assert request.file_path == "/uploads/collection (backup).csv"

    def test_empty_file_path_passes(self):
        """Empty file path should be accepted (no length validation)."""
        request = ImportClzRequest(file_path="")
        assert request.file_path == ""

    def test_missing_file_path_fails(self):
        """Missing file_path field should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            ImportClzRequest()
        assert "file_path" in str(exc_info.value)

    def test_retry_failed_only_flag_passes(self):
        """Explicit retry-failed-only flag should be accepted."""
        request = ImportClzRequest(
            file_path="/uploads/collections/clz_collection_2024.csv",
            retry_failed_only=True,
        )
        assert request.retry_failed_only is True


class TestHealthResponse:
    """Tests for HealthResponse schema."""

    def test_valid_healthy_status(self):
        """Healthy status should be accepted."""
        response = HealthResponse(status="healthy")
        assert response.status == "healthy"

    def test_valid_degraded_status(self):
        """Degraded status should be accepted."""
        response = HealthResponse(status="degraded")
        assert response.status == "degraded"

    def test_valid_unhealthy_status(self):
        """Unhealthy status should be accepted."""
        response = HealthResponse(status="unhealthy")
        assert response.status == "unhealthy"

    def test_any_string_status_passes(self):
        """Any string status should be accepted (no enum constraint)."""
        response = HealthResponse(status="starting")
        assert response.status == "starting"

    def test_missing_status_fails(self):
        """Missing status field should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            HealthResponse()
        assert "status" in str(exc_info.value)


class TestIdentityResolutionResponse:
    """Tests for IdentityResolutionResponse schema."""

    def test_valid_full_response(self):
        """Full response with all fields should be accepted."""
        response = IdentityResolutionResponse(
            canonical_uuid=UUID("550e8400-e29b-41d4-a716-446655440000"),
            confidence=0.95,
            explanation="Matched by series + issue + year: X-Men (1991) #1",
            platform_urls={
                "gcd": "https://www.comics.org/issue/12345/",
                "locg": "https://leagueofcomicgeeks.com/comic/12345678/x-men-1",
            },
        )
        assert response.canonical_uuid == UUID("550e8400-e29b-41d4-a716-446655440000")
        assert response.confidence == 0.95
        assert (
            response.explanation == "Matched by series + issue + year: X-Men (1991) #1"
        )
        assert response.platform_urls["gcd"] == "https://www.comics.org/issue/12345/"

    def test_uuid_as_string(self):
        """UUID can be provided as string."""
        response = IdentityResolutionResponse(
            canonical_uuid="550e8400-e29b-41d4-a716-446655440000",
            confidence=0.85,
            explanation="Matched by series name",
            platform_urls={"gcd": "https://example.com/issue/1"},
        )
        assert response.canonical_uuid == UUID("550e8400-e29b-41d4-a716-446655440000")

    def test_confidence_at_minimum(self):
        """Confidence at 0.0 should be accepted."""
        response = IdentityResolutionResponse(
            canonical_uuid=UUID("550e8400-e29b-41d4-a716-446655440000"),
            confidence=0.0,
            explanation="Low confidence match",
            platform_urls={},
        )
        assert response.confidence == 0.0

    def test_confidence_at_maximum(self):
        """Confidence at 1.0 should be accepted."""
        response = IdentityResolutionResponse(
            canonical_uuid=UUID("550e8400-e29b-41d4-a716-446655440000"),
            confidence=1.0,
            explanation="Perfect match",
            platform_urls={"gcd": "https://example.com"},
        )
        assert response.confidence == 1.0

    def test_confidence_below_minimum_fails(self):
        """Confidence below 0.0 should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            IdentityResolutionResponse(
                canonical_uuid=UUID("550e8400-e29b-41d4-a716-446655440000"),
                confidence=-0.1,
                explanation="Invalid",
                platform_urls={},
            )
        assert "confidence" in str(exc_info.value)

    def test_confidence_above_maximum_fails(self):
        """Confidence above 1.0 should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            IdentityResolutionResponse(
                canonical_uuid=UUID("550e8400-e29b-41d4-a716-446655440000"),
                confidence=1.1,
                explanation="Invalid",
                platform_urls={},
            )
        assert "confidence" in str(exc_info.value)

    def test_empty_platform_urls(self):
        """Empty platform_urls should be accepted."""
        response = IdentityResolutionResponse(
            canonical_uuid=UUID("550e8400-e29b-41d4-a716-446655440000"),
            confidence=0.5,
            explanation="Partial match",
            platform_urls={},
        )
        assert response.platform_urls == {}

    def test_multiple_platform_urls(self):
        """Multiple platform URLs should be accepted."""
        response = IdentityResolutionResponse(
            canonical_uuid=UUID("550e8400-e29b-41d4-a716-446655440000"),
            confidence=0.95,
            explanation="Multi-platform match",
            platform_urls={
                "gcd": "https://www.comics.org/issue/12345/",
                "locg": "https://leagueofcomicgeeks.com/comic/12345678/x-men-1",
                "ccl": "https://comicbookrealm.com/series/12345",
                "clz": "https://clz.com/comics/issue/12345",
            },
        )
        assert len(response.platform_urls) == 4

    def test_missing_canonical_uuid_fails(self):
        """Missing canonical_uuid should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            IdentityResolutionResponse(
                confidence=0.95,
                explanation="Test",
                platform_urls={},
            )
        assert "canonical_uuid" in str(exc_info.value)

    def test_missing_confidence_fails(self):
        """Missing confidence should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            IdentityResolutionResponse(
                canonical_uuid=UUID("550e8400-e29b-41d4-a716-446655440000"),
                explanation="Test",
                platform_urls={},
            )
        assert "confidence" in str(exc_info.value)

    def test_missing_explanation_fails(self):
        """Missing explanation should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            IdentityResolutionResponse(
                canonical_uuid=UUID("550e8400-e29b-41d4-a716-446655440000"),
                confidence=0.95,
                platform_urls={},
            )
        assert "explanation" in str(exc_info.value)

    def test_missing_platform_urls_defaults_to_empty_dict(self):
        """Missing platform_urls should default to empty dict."""
        response = IdentityResolutionResponse(
            canonical_uuid=UUID("550e8400-e29b-41d4-a716-446655440000"),
            confidence=0.95,
            explanation="Test",
        )
        assert response.platform_urls == {}
        assert response.platform_status == {}


class TestOperationResponse:
    """Tests for OperationResponse schema (AIP-151 compliance)."""

    def test_done_false_with_metadata(self):
        """AIP-151: done=False with metadata for running operation."""
        response = OperationResponse(
            name="operations/550e8400-e29b-41d4-a716-446655440000",
            done=False,
            metadata={
                "progress": 0.45,
                "total_urls": 100,
                "processed_urls": 45,
            },
        )
        assert response.done is False
        assert response.metadata["progress"] == 0.45
        assert response.response is None
        assert response.error is None

    def test_done_true_with_response(self):
        """AIP-151: done=True with response field for successful completion."""
        response = OperationResponse(
            name="operations/550e8400-e29b-41d4-a716-446655440000",
            done=True,
            response={
                "results": [
                    {
                        "canonical_uuid": "550e8400-e29b-41d4-a716-446655440001",
                        "confidence": 0.95,
                    }
                ],
            },
        )
        assert response.done is True
        assert response.response is not None
        assert response.response["results"][0]["confidence"] == 0.95
        assert response.error is None

    def test_done_true_with_error(self):
        """AIP-151: done=True with error field for failed operation."""
        response = OperationResponse(
            name="operations/550e8400-e29b-41d4-a716-446655440000",
            done=True,
            error={
                "code": 3,
                "message": "Invalid URL format",
                "details": [],
            },
        )
        assert response.done is True
        assert response.error is not None
        assert response.error["code"] == 3
        assert response.error["message"] == "Invalid URL format"
        assert response.response is None

    def test_valid_operation_name_format(self):
        """Valid operation name format should be accepted."""
        response = OperationResponse(
            name="operations/abc123-def456",
            done=False,
        )
        assert response.name == "operations/abc123-def456"

    def test_operation_name_with_uuid(self):
        """Operation name with UUID format should be accepted."""
        response = OperationResponse(
            name="operations/550e8400-e29b-41d4-a716-446655440000",
            done=False,
        )
        assert response.name == "operations/550e8400-e29b-41d4-a716-446655440000"

    def test_invalid_operation_name_no_prefix_fails(self):
        """Operation name without 'operations/' prefix should fail."""
        with pytest.raises(ValidationError) as exc_info:
            OperationResponse(
                name="550e8400-e29b-41d4-a716-446655440000",
                done=False,
            )
        assert "name" in str(exc_info.value)

    def test_invalid_operation_name_with_slash_fails(self):
        """Operation name with extra slashes should fail."""
        with pytest.raises(ValidationError) as exc_info:
            OperationResponse(
                name="operations/abc/def",
                done=False,
            )
        assert "name" in str(exc_info.value)

    def test_missing_name_fails(self):
        """Missing name field should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            OperationResponse(done=False)
        assert "name" in str(exc_info.value)

    def test_missing_done_fails(self):
        """Missing done field should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            OperationResponse(name="operations/123")
        assert "done" in str(exc_info.value)

    def test_all_optional_fields_none(self):
        """All optional fields can be None."""
        response = OperationResponse(
            name="operations/550e8400-e29b-41d4-a716-446655440000",
            done=False,
            metadata=None,
            error=None,
            response=None,
        )
        assert response.metadata is None
        assert response.error is None
        assert response.response is None

    def test_complex_metadata_structure(self):
        """Complex metadata structure should be accepted."""
        response = OperationResponse(
            name="operations/550e8400-e29b-41d4-a716-446655440000",
            done=False,
            metadata={
                "progress": 0.75,
                "total_urls": 1000,
                "processed_urls": 750,
                "errors": 5,
                "estimated_completion": "2024-01-15T11:00:00Z",
                "stage": "resolving_identities",
            },
        )
        assert response.metadata["stage"] == "resolving_identities"
        assert response.metadata["errors"] == 5

    def test_complex_error_structure(self):
        """Complex error structure following AIP-193 should be accepted."""
        response = OperationResponse(
            name="operations/550e8400-e29b-41d4-a716-446655440000",
            done=True,
            error={
                "code": 3,
                "message": "Invalid input",
                "details": [
                    {
                        "type": "comic_identity_engine.errors.InvalidURLError",
                        "message": "URL format not recognized",
                        "url": "invalid-url",
                    }
                ],
            },
        )
        assert len(response.error["details"]) == 1


class TestJobStatusResponse:
    """Tests for JobStatusResponse schema."""

    def test_valid_running_status(self):
        """Valid running status should be accepted."""
        response = JobStatusResponse(
            operation_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
            status="running",
            progress=0.45,
            created_at=datetime.fromisoformat("2024-01-15T10:30:00"),
            updated_at=datetime.fromisoformat("2024-01-15T10:35:00"),
        )
        assert response.status == "running"
        assert response.progress == 0.45

    def test_valid_pending_status(self):
        """Valid pending status should be accepted."""
        response = JobStatusResponse(
            operation_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
            status="pending",
            created_at=datetime.fromisoformat("2024-01-15T10:30:00"),
            updated_at=datetime.fromisoformat("2024-01-15T10:30:00"),
        )
        assert response.status == "pending"
        assert response.progress is None

    def test_valid_completed_status(self):
        """Valid completed status should be accepted."""
        response = JobStatusResponse(
            operation_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
            status="completed",
            progress=1.0,
            created_at=datetime.fromisoformat("2024-01-15T10:30:00"),
            updated_at=datetime.fromisoformat("2024-01-15T10:40:00"),
        )
        assert response.status == "completed"
        assert response.progress == 1.0

    def test_valid_failed_status(self):
        """Valid failed status should be accepted."""
        response = JobStatusResponse(
            operation_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
            status="failed",
            created_at=datetime.fromisoformat("2024-01-15T10:30:00"),
            updated_at=datetime.fromisoformat("2024-01-15T10:32:00"),
        )
        assert response.status == "failed"

    def test_invalid_status_fails(self):
        """Invalid status not in enum should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            JobStatusResponse(
                operation_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
                status="unknown",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        assert "status" in str(exc_info.value)

    def test_progress_at_zero(self):
        """Progress at 0.0 should be accepted."""
        response = JobStatusResponse(
            operation_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
            status="running",
            progress=0.0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert response.progress == 0.0

    def test_progress_at_one(self):
        """Progress at 1.0 should be accepted."""
        response = JobStatusResponse(
            operation_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
            status="completed",
            progress=1.0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert response.progress == 1.0

    def test_progress_below_zero_fails(self):
        """Progress below 0.0 should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            JobStatusResponse(
                operation_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
                status="running",
                progress=-0.1,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        assert "progress" in str(exc_info.value)

    def test_progress_above_one_fails(self):
        """Progress above 1.0 should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            JobStatusResponse(
                operation_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
                status="running",
                progress=1.1,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        assert "progress" in str(exc_info.value)

    def test_null_progress_passes(self):
        """Null progress should be accepted (indeterminate)."""
        response = JobStatusResponse(
            operation_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
            status="pending",
            progress=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert response.progress is None

    def test_operation_id_as_string(self):
        """Operation ID can be provided as string."""
        response = JobStatusResponse(
            operation_id="550e8400-e29b-41d4-a716-446655440000",
            status="running",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert response.operation_id == UUID("550e8400-e29b-41d4-a716-446655440000")

    def test_missing_operation_id_fails(self):
        """Missing operation_id should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            JobStatusResponse(
                status="running",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        assert "operation_id" in str(exc_info.value)

    def test_missing_status_fails(self):
        """Missing status should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            JobStatusResponse(
                operation_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        assert "status" in str(exc_info.value)

    def test_missing_created_at_fails(self):
        """Missing created_at should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            JobStatusResponse(
                operation_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
                status="running",
                updated_at=datetime.now(),
            )
        assert "created_at" in str(exc_info.value)

    def test_missing_updated_at_fails(self):
        """Missing updated_at should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            JobStatusResponse(
                operation_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
                status="running",
                created_at=datetime.now(),
            )
        assert "updated_at" in str(exc_info.value)


class TestSchemaExamples:
    """Tests that schema examples are valid and descriptions are correct."""

    def test_resolve_identity_request_examples(self):
        """ResolveIdentityRequest examples should be valid."""
        examples = ResolveIdentityRequest.model_config["json_schema_extra"]["examples"]
        for example in examples:
            request = ResolveIdentityRequest(**example)
            assert request.url == example["url"]

    def test_bulk_resolve_request_examples(self):
        """BulkResolveRequest examples should be valid."""
        examples = BulkResolveRequest.model_config["json_schema_extra"]["examples"]
        for example in examples:
            request = BulkResolveRequest(**example)
            assert request.urls == example["urls"]

    def test_import_clz_request_examples(self):
        """ImportClzRequest examples should be valid."""
        examples = ImportClzRequest.model_config["json_schema_extra"]["examples"]
        for example in examples:
            request = ImportClzRequest(**example)
            assert request.file_path == example["file_path"]
            assert request.retry_failed_only == example["retry_failed_only"]

    def test_health_response_examples(self):
        """HealthResponse examples should be valid."""
        examples = HealthResponse.model_config["json_schema_extra"]["examples"]
        for example in examples:
            response = HealthResponse(**example)
            assert response.status == example["status"]

    def test_identity_resolution_response_examples(self):
        """IdentityResolutionResponse examples should be valid."""
        examples = IdentityResolutionResponse.model_config["json_schema_extra"][
            "examples"
        ]
        for example in examples:
            response = IdentityResolutionResponse(**example)
            assert str(response.canonical_uuid) == example["canonical_uuid"]
            assert response.confidence == example["confidence"]

    def test_operation_response_examples(self):
        """OperationResponse examples should be valid."""
        examples = OperationResponse.model_config["json_schema_extra"]["examples"]
        for example in examples:
            response = OperationResponse(**example)
            assert response.name == example["name"]
            assert response.done == example["done"]

    def test_job_status_response_examples(self):
        """JobStatusResponse examples should be valid."""
        examples = JobStatusResponse.model_config["json_schema_extra"]["examples"]
        for example in examples:
            response = JobStatusResponse(**example)
            assert str(response.operation_id) == example["operation_id"]
            assert response.status == example["status"]

    def test_resolve_identity_request_description(self):
        """ResolveIdentityRequest field description should mention platforms."""
        field_info = ResolveIdentityRequest.model_fields["url"]
        assert "GCD" in field_info.description
        assert "LoCG" in field_info.description

    def test_health_response_description(self):
        """HealthResponse field description should mention valid values."""
        field_info = HealthResponse.model_fields["status"]
        assert "healthy" in field_info.description
        assert "degraded" in field_info.description

    def test_identity_resolution_confidence_bounds(self):
        """IdentityResolutionResponse confidence should have bounds defined."""
        # Validate via JSON schema generation - the bounds are enforced at runtime
        json_schema = IdentityResolutionResponse.model_json_schema()
        confidence_props = json_schema["properties"]["confidence"]
        assert confidence_props["minimum"] == 0.0
        assert confidence_props["maximum"] == 1.0

    def test_job_status_progress_bounds(self):
        """JobStatusResponse progress should have bounds defined."""
        # Validate via JSON schema generation - the bounds are enforced at runtime
        json_schema = JobStatusResponse.model_json_schema()
        progress_props = json_schema["properties"]["progress"]
        # For optional fields, bounds may be under "anyOf" or directly in properties
        if "anyOf" in progress_props:
            # Find the number type within anyOf
            for schema_part in progress_props["anyOf"]:
                if schema_part.get("type") == "number":
                    assert schema_part["minimum"] == 0.0
                    assert schema_part["maximum"] == 1.0
                    break
        else:
            assert progress_props["minimum"] == 0.0
            assert progress_props["maximum"] == 1.0

    def test_bulk_resolve_request_list_bounds(self):
        """BulkResolveRequest urls list should have bounds defined."""
        # Validate via JSON schema generation
        json_schema = BulkResolveRequest.model_json_schema()
        urls_props = json_schema["properties"]["urls"]
        assert urls_props["minItems"] == 1
        assert urls_props["maxItems"] == 1000

    def test_operation_name_pattern(self):
        """OperationResponse name should have pattern defined."""
        # Validate via JSON schema generation
        json_schema = OperationResponse.model_json_schema()
        name_props = json_schema["properties"]["name"]
        assert "operations/" in name_props["pattern"]

    def test_job_status_pattern(self):
        """JobStatusResponse status should have pattern defined."""
        # Validate via JSON schema generation
        json_schema = JobStatusResponse.model_json_schema()
        status_props = json_schema["properties"]["status"]
        assert "pending" in status_props["pattern"]
        assert "completed" in status_props["pattern"]
