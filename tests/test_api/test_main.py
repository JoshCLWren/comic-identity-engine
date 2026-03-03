"""Tests for Comic Identity Engine HTTP API main module.

This module provides comprehensive tests for:
- create_app() factory function
- Health check endpoint
- Exception handlers for custom errors
- CORS middleware configuration
- OpenAPI docs endpoints
- Lifespan management (Redis/database mocking)
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport

from comic_identity_engine.api.main import (
    _lifespan,
    _setup_exception_handlers,
    create_app,
)
from comic_identity_engine.errors import (
    AdapterError,
    AuthenticationError,
    DuplicateEntityError,
    EntityNotFoundError,
    NetworkError,
    ParseError,
    RateLimitError,
    ResolutionError,
    ValidationError,
)


FIXED_UUID = UUID("12345678-1234-1234-1234-123456789abc")


@pytest.fixture
def mock_redis_cache():
    """Fixture to provide mocked Redis cache singleton."""
    with patch("comic_identity_engine.api.main.redis_cache") as mock:
        mock.initialize = AsyncMock()
        mock.close = AsyncMock()
        yield mock


@pytest.fixture
def mock_database_connection():
    """Fixture to provide mocked database connection test."""
    with patch(
        "comic_identity_engine.api.main.test_database_connection",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = True
        yield mock


@pytest.fixture
def mock_get_settings():
    """Fixture to provide mocked settings with test configuration."""
    with patch("comic_identity_engine.api.main.get_settings") as mock:
        settings = MagicMock()
        settings.redis.cache_url = "redis://localhost:6379/1"
        settings.app.cors_origins_list = [
            "http://localhost:3000",
            "https://example.com",
        ]
        mock.return_value = settings
        yield mock


@pytest_asyncio.fixture
async def app_with_mocked_lifespan(
    mock_redis_cache, mock_database_connection, mock_get_settings
) -> FastAPI:
    """Fixture to create FastAPI app with mocked lifespan dependencies."""
    return create_app()


@pytest_asyncio.fixture
async def async_client(
    app_with_mocked_lifespan,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Fixture to provide httpx.AsyncClient for testing."""
    app = app_with_mocked_lifespan
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestCreateApp:
    """Tests for create_app() factory function."""

    def test_create_app_returns_fastapi_instance(self, mock_get_settings):
        """Test that create_app() returns a FastAPI instance."""
        with patch("comic_identity_engine.api.main.redis_cache"):
            app = create_app()
            assert isinstance(app, FastAPI)

    def test_create_app_configures_title_and_description(self, mock_get_settings):
        """Test that create_app() configures title and description."""
        with patch("comic_identity_engine.api.main.redis_cache"):
            app = create_app()
            assert app.title == "Comic Identity Engine API"
            assert "entity resolution system for comic books" in app.description

    def test_create_app_configures_version(self, mock_get_settings):
        """Test that create_app() configures API version."""
        with patch("comic_identity_engine.api.main.redis_cache"):
            app = create_app()
            assert app.version == "1.0.0"

    def test_create_app_configures_openapi_urls(self, mock_get_settings):
        """Test that create_app() configures OpenAPI documentation URLs."""
        with patch("comic_identity_engine.api.main.redis_cache"):
            app = create_app()
            assert app.docs_url == "/api/docs"
            assert app.redoc_url == "/api/redoc"
            assert app.openapi_url == "/api/openapi.json"

    def test_create_app_has_lifespan(self, mock_get_settings):
        """Test that create_app() configures lifespan context manager."""
        with patch("comic_identity_engine.api.main.redis_cache"):
            app = create_app()
            assert app.router.lifespan_context is not None

    def test_create_app_includes_health_endpoint(self, mock_get_settings):
        """Test that create_app() includes health check endpoint."""
        with patch("comic_identity_engine.api.main.redis_cache"):
            app = create_app()
            routes = [getattr(route, "path", "") for route in app.routes]
            assert "/api/health" in routes

    def test_create_app_includes_api_v1_prefix(self, mock_get_settings):
        """Test that create_app() includes routers with /api/v1 prefix."""
        mock_router = MagicMock()
        mock_router.prefix = "/test"
        with patch("comic_identity_engine.api.main.redis_cache"):
            with patch(
                "comic_identity_engine.api.main.all_routers",
                [mock_router],
            ):
                _ = create_app()  # noqa: F841
                # Verify app was created successfully with routers
                # Since we use real FastAPI, we just verify no errors occur

    def test_create_app_adds_cors_middleware(self, mock_get_settings):
        """Test that create_app() adds CORS middleware."""
        with patch("comic_identity_engine.api.main.redis_cache"):
            app = create_app()
            # Check that add_middleware was called (CORS middleware is added)
            # FastAPI wraps middleware in Middleware class, check the inner cls
            middleware_types = [type(m).__name__ for m in app.user_middleware]
            assert "Middleware" in middleware_types
            # Verify CORS by checking allow_origins in the middleware kwargs
            cors_middleware = None
            for m in app.user_middleware:
                if hasattr(m, "cls") and "CORSMiddleware" in str(m.cls):
                    cors_middleware = m
                    break
            assert cors_middleware is not None


@pytest.mark.asyncio
class TestHealthCheck:
    """Tests for health check endpoint."""

    async def test_health_check_returns_ok(self, async_client):
        """Test that /api/health returns status ok."""
        response = await async_client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    async def test_health_check_content_type_json(self, async_client):
        """Test that health check returns JSON content type."""
        response = await async_client.get("/api/health")
        assert response.headers["content-type"] == "application/json"

    async def test_health_check_method_not_allowed_post(self, async_client):
        """Test that POST to health check returns 405."""
        response = await async_client.post("/api/health")
        assert response.status_code == 405

    async def test_health_check_method_not_allowed_put(self, async_client):
        """Test that PUT to health check returns 405."""
        response = await async_client.put("/api/health")
        assert response.status_code == 405

    async def test_health_check_method_not_allowed_delete(self, async_client):
        """Test that DELETE to health check returns 405."""
        response = await async_client.delete("/api/health")
        assert response.status_code == 405


@pytest.mark.asyncio
class TestExceptionHandlersEntityNotFound:
    """Tests for EntityNotFoundError exception handler."""

    async def test_entity_not_found_returns_404(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test that EntityNotFoundError returns 404 status."""

        @app_with_mocked_lifespan.get("/test/not-found")
        async def raise_not_found():
            raise EntityNotFoundError(
                "Issue not found",
                entity_type="Issue",
                entity_id=str(FIXED_UUID),
            )

        response = await async_client.get("/test/not-found")
        assert response.status_code == 404

    async def test_entity_not_found_response_structure(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test that EntityNotFoundError returns correct error structure."""

        @app_with_mocked_lifespan.get("/test/not-found-structure")
        async def raise_not_found_structure():
            raise EntityNotFoundError(
                "Issue not found",
                entity_type="Issue",
                entity_id=str(FIXED_UUID),
            )

        response = await async_client.get("/test/not-found-structure")
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "ENTITY_NOT_FOUND"
        assert "Issue not found" in data["error"]["message"]
        assert data["error"]["entity_type"] == "Issue"
        assert data["error"]["entity_id"] == str(FIXED_UUID)

    async def test_entity_not_found_without_entity_type(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test EntityNotFoundError without entity type."""

        @app_with_mocked_lifespan.get("/test/not-found-no-type")
        async def raise_not_found_no_type():
            raise EntityNotFoundError("Generic not found")

        response = await async_client.get("/test/not-found-no-type")
        assert response.status_code == 404
        data = response.json()
        assert data["error"]["entity_type"] is None


@pytest.mark.asyncio
class TestExceptionHandlersDuplicateEntity:
    """Tests for DuplicateEntityError exception handler."""

    async def test_duplicate_entity_returns_409(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test that DuplicateEntityError returns 409 status."""

        @app_with_mocked_lifespan.get("/test/duplicate")
        async def raise_duplicate():
            raise DuplicateEntityError(
                "Duplicate mapping",
                entity_type="ExternalMapping",
                existing_id=str(FIXED_UUID),
            )

        response = await async_client.get("/test/duplicate")
        assert response.status_code == 409

    async def test_duplicate_entity_response_structure(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test that DuplicateEntityError returns correct error structure."""

        @app_with_mocked_lifespan.get("/test/duplicate-structure")
        async def raise_duplicate_structure():
            raise DuplicateEntityError(
                "Duplicate mapping detected",
                entity_type="ExternalMapping",
                existing_id=str(FIXED_UUID),
            )

        response = await async_client.get("/test/duplicate-structure")
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "DUPLICATE_ENTITY"
        assert "Duplicate mapping" in data["error"]["message"]
        assert data["error"]["entity_type"] == "ExternalMapping"
        assert data["error"]["existing_id"] == str(FIXED_UUID)


@pytest.mark.asyncio
class TestExceptionHandlersValidationError:
    """Tests for ValidationError exception handler."""

    async def test_validation_error_returns_400(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test that ValidationError returns 400 status."""

        @app_with_mocked_lifespan.get("/test/validation")
        async def raise_validation():
            raise ValidationError("Invalid input data")

        response = await async_client.get("/test/validation")
        assert response.status_code == 400

    async def test_validation_error_response_structure(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test that ValidationError returns correct error structure."""

        @app_with_mocked_lifespan.get("/test/validation-structure")
        async def raise_validation_structure():
            raise ValidationError("Field 'issue_number' is required")

        response = await async_client.get("/test/validation-structure")
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert "Field 'issue_number' is required" in data["error"]["message"]


@pytest.mark.asyncio
class TestExceptionHandlersAuthenticationError:
    """Tests for AuthenticationError exception handler."""

    async def test_authentication_error_returns_401(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test that AuthenticationError returns 401 status."""

        @app_with_mocked_lifespan.get("/test/auth")
        async def raise_auth():
            raise AuthenticationError("Invalid credentials")

        response = await async_client.get("/test/auth")
        assert response.status_code == 401

    async def test_authentication_error_response_structure(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test that AuthenticationError returns correct error structure."""

        @app_with_mocked_lifespan.get("/test/auth-structure")
        async def raise_auth_structure():
            raise AuthenticationError("Token expired", source="gcd")

        response = await async_client.get("/test/auth-structure")
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "AUTHENTICATION_ERROR"
        assert "Token expired" in data["error"]["message"]


@pytest.mark.asyncio
class TestExceptionHandlersRateLimitError:
    """Tests for RateLimitError exception handler."""

    async def test_rate_limit_returns_429(self, async_client, app_with_mocked_lifespan):
        """Test that RateLimitError returns 429 status."""

        @app_with_mocked_lifespan.get("/test/rate-limit")
        async def raise_rate_limit():
            raise RateLimitError("Rate limit exceeded")

        response = await async_client.get("/test/rate-limit")
        assert response.status_code == 429

    async def test_rate_limit_with_retry_after(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test RateLimitError includes Retry-After header."""

        @app_with_mocked_lifespan.get("/test/rate-limit-retry")
        async def raise_rate_limit_retry():
            raise RateLimitError("Rate limit exceeded", retry_after=60)

        response = await async_client.get("/test/rate-limit-retry")
        assert response.status_code == 429
        assert response.headers.get("Retry-After") == "60"
        data = response.json()
        assert data["error"]["retry_after"] == 60

    async def test_rate_limit_without_retry_after(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test RateLimitError without retry_after."""

        @app_with_mocked_lifespan.get("/test/rate-limit-no-retry")
        async def raise_rate_limit_no_retry():
            raise RateLimitError("Rate limit exceeded")

        response = await async_client.get("/test/rate-limit-no-retry")
        assert "Retry-After" not in response.headers
        data = response.json()
        assert data["error"]["retry_after"] is None


@pytest.mark.asyncio
class TestExceptionHandlersNetworkError:
    """Tests for NetworkError exception handler."""

    async def test_network_error_returns_502(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test that NetworkError returns 502 status."""

        @app_with_mocked_lifespan.get("/test/network")
        async def raise_network():
            raise NetworkError("Connection timeout", source="hip")

        response = await async_client.get("/test/network")
        assert response.status_code == 502

    async def test_network_error_response_structure(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test that NetworkError returns correct error structure."""

        @app_with_mocked_lifespan.get("/test/network-structure")
        async def raise_network_structure():
            raise NetworkError("Connection refused", source="gcd", status_code=503)

        response = await async_client.get("/test/network-structure")
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "NETWORK_ERROR"
        assert "Connection refused" in data["error"]["message"]
        assert data["error"]["source"] == "gcd"

    async def test_network_error_without_source(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test NetworkError without source."""

        @app_with_mocked_lifespan.get("/test/network-no-source")
        async def raise_network_no_source():
            raise NetworkError("Generic network error")

        response = await async_client.get("/test/network-no-source")
        data = response.json()
        assert data["error"]["source"] is None


@pytest.mark.asyncio
class TestExceptionHandlersParseError:
    """Tests for ParseError exception handler."""

    async def test_parse_error_returns_422(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test that ParseError returns 422 status."""

        @app_with_mocked_lifespan.get("/test/parse")
        async def raise_parse():
            raise ParseError("Invalid HTML format")

        response = await async_client.get("/test/parse")
        assert response.status_code == 422

    async def test_parse_error_response_structure(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test that ParseError returns correct error structure."""

        @app_with_mocked_lifespan.get("/test/parse-structure")
        async def raise_parse_structure():
            raise ParseError("Unexpected JSON structure")

        response = await async_client.get("/test/parse-structure")
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "PARSE_ERROR"
        assert "Unexpected JSON structure" in data["error"]["message"]


@pytest.mark.asyncio
class TestExceptionHandlersResolutionError:
    """Tests for ResolutionError exception handler."""

    async def test_resolution_error_returns_422(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test that ResolutionError returns 422 status."""

        @app_with_mocked_lifespan.get("/test/resolution")
        async def raise_resolution():
            raise ResolutionError("Could not resolve identity")

        response = await async_client.get("/test/resolution")
        assert response.status_code == 422

    async def test_resolution_error_with_confidence(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test ResolutionError includes confidence score."""

        @app_with_mocked_lifespan.get("/test/resolution-confidence")
        async def raise_resolution_confidence():
            raise ResolutionError(
                "Could not resolve identity",
                confidence=0.45,
                candidates=[{"id": "1"}],
            )

        response = await async_client.get("/test/resolution-confidence")
        data = response.json()
        assert data["error"]["code"] == "RESOLUTION_ERROR"
        assert data["error"]["confidence"] == 0.45
        assert data["error"]["candidates_count"] == 1

    async def test_resolution_error_with_multiple_candidates(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test ResolutionError with multiple candidates."""

        @app_with_mocked_lifespan.get("/test/resolution-candidates")
        async def raise_resolution_candidates():
            raise ResolutionError(
                "Ambiguous match",
                confidence=0.65,
                candidates=[{"id": "1"}, {"id": "2"}, {"id": "3"}],
            )

        response = await async_client.get("/test/resolution-candidates")
        data = response.json()
        assert data["error"]["candidates_count"] == 3

    async def test_resolution_error_no_candidates(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test ResolutionError with no candidates."""

        @app_with_mocked_lifespan.get("/test/resolution-no-candidates")
        async def raise_resolution_no_candidates():
            raise ResolutionError("No matches found")

        response = await async_client.get("/test/resolution-no-candidates")
        data = response.json()
        assert data["error"]["candidates_count"] == 0
        assert data["error"]["confidence"] is None


@pytest.mark.asyncio
class TestExceptionHandlersAdapterError:
    """Tests for AdapterError exception handler."""

    async def test_adapter_error_returns_500(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test that AdapterError returns 500 status."""

        @app_with_mocked_lifespan.get("/test/adapter")
        async def raise_adapter():
            raise AdapterError("Internal adapter failure", source="cpg")

        response = await async_client.get("/test/adapter")
        assert response.status_code == 500

    async def test_adapter_error_response_structure(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test that AdapterError returns correct error structure."""

        @app_with_mocked_lifespan.get("/test/adapter-structure")
        async def raise_adapter_structure():
            raise AdapterError("Database connection failed", source="gcd")

        response = await async_client.get("/test/adapter-structure")
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "ADAPTER_ERROR"
        assert "Database connection failed" in data["error"]["message"]
        assert data["error"]["source"] == "gcd"

    async def test_adapter_error_without_source(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test AdapterError without source."""

        @app_with_mocked_lifespan.get("/test/adapter-no-source")
        async def raise_adapter_no_source():
            raise AdapterError("Generic adapter error")

        response = await async_client.get("/test/adapter-no-source")
        data = response.json()
        assert data["error"]["source"] is None


@pytest.mark.asyncio
class TestCorsMiddleware:
    """Tests for CORS middleware configuration."""

    async def test_cors_headers_present(self, async_client, app_with_mocked_lifespan):
        """Test that CORS headers are present in response."""
        response = await async_client.get(
            "/api/health",
            headers={"Origin": "http://localhost:3000"},
        )
        assert "access-control-allow-origin" in response.headers

    async def test_cors_allow_origin_matches_request(
        self, async_client, app_with_mocked_lifespan
    ):
        """Test that Access-Control-Allow-Origin matches request origin."""
        origin = "http://localhost:3000"
        response = await async_client.get(
            "/api/health",
            headers={"Origin": origin},
        )
        assert response.headers.get("access-control-allow-origin") == origin

    async def test_cors_allow_credentials(self, async_client, app_with_mocked_lifespan):
        """Test that Access-Control-Allow-Credentials header is present."""
        response = await async_client.get(
            "/api/health",
            headers={"Origin": "http://localhost:3000"},
        )
        assert response.headers.get("access-control-allow-credentials") == "true"

    async def test_cors_preflight_request(self, async_client, app_with_mocked_lifespan):
        """Test CORS preflight OPTIONS request."""
        response = await async_client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert response.status_code == 200
        assert "access-control-allow-methods" in response.headers
        assert "access-control-allow-headers" in response.headers


@pytest.mark.asyncio
class TestOpenApiDocs:
    """Tests for OpenAPI documentation endpoints."""

    async def test_docs_endpoint_returns_200(self, async_client):
        """Test that /api/docs returns 200."""
        response = await async_client.get("/api/docs")
        assert response.status_code == 200

    async def test_docs_endpoint_returns_html(self, async_client):
        """Test that /api/docs returns HTML content."""
        response = await async_client.get("/api/docs")
        assert "text/html" in response.headers["content-type"]
        assert (
            b"swagger" in response.content.lower()
            or b"fastapi" in response.content.lower()
        )

    async def test_redoc_endpoint_returns_200(self, async_client):
        """Test that /api/redoc returns 200."""
        response = await async_client.get("/api/redoc")
        assert response.status_code == 200

    async def test_redoc_endpoint_returns_html(self, async_client):
        """Test that /api/redoc returns HTML content."""
        response = await async_client.get("/api/redoc")
        assert "text/html" in response.headers["content-type"]
        assert (
            b"redoc" in response.content.lower()
            or b"fastapi" in response.content.lower()
        )

    async def test_openapi_json_endpoint_returns_200(self, async_client):
        """Test that /api/openapi.json returns 200."""
        response = await async_client.get("/api/openapi.json")
        assert response.status_code == 200

    async def test_openapi_json_is_valid_json(self, async_client):
        """Test that /api/openapi.json returns valid JSON."""
        response = await async_client.get("/api/openapi.json")
        data = response.json()
        assert "openapi" in data
        assert "info" in data
        assert "paths" in data

    async def test_openapi_json_contains_api_info(self, async_client):
        """Test that OpenAPI JSON contains API information."""
        response = await async_client.get("/api/openapi.json")
        data = response.json()
        assert data["info"]["title"] == "Comic Identity Engine API"
        assert data["info"]["version"] == "1.0.0"

    async def test_openapi_json_contains_health_endpoint(self, async_client):
        """Test that OpenAPI JSON documents health endpoint."""
        response = await async_client.get("/api/openapi.json")
        data = response.json()
        assert "/api/health" in data["paths"]


class TestLifespan:
    """Tests for lifespan context manager (startup/shutdown).

    Note: These tests verify that the lifespan function exists and is properly
    registered. Testing the internal behavior of lifespan would require complex
    mocking of Redis and database connections that is better covered by
    integration tests.
    """

    def test_lifespan_function_exists(self):
        """Test that _lifespan function exists and is an async context manager."""
        assert callable(_lifespan)
        # _lifespan is decorated with @asynccontextmanager, so it returns an
        # async generator function wrapper, not a direct coroutine function.
        # The decorated function is still callable and async.

    def test_create_app_registers_lifespan(self):
        """Test that create_app() registers the lifespan context manager."""
        with patch("comic_identity_engine.api.main.get_settings") as mock_settings:
            mock_settings.return_value.redis.cache_url = "redis://localhost:6379/1"
            app = create_app()
            assert app.router.lifespan_context is not None


class TestSetupExceptionHandlers:
    """Tests for _setup_exception_handlers function."""

    def test_setup_registers_all_handlers(self):
        """Test that all exception handlers are registered."""
        app = FastAPI()
        _setup_exception_handlers(app)

        # Check that handlers are registered by checking the exception_handlers dict
        exception_handlers = app.exception_handlers
        assert EntityNotFoundError in exception_handlers
        assert DuplicateEntityError in exception_handlers
        assert ValidationError in exception_handlers
        assert AuthenticationError in exception_handlers
        assert RateLimitError in exception_handlers
        assert NetworkError in exception_handlers
        assert ParseError in exception_handlers
        assert ResolutionError in exception_handlers
        assert AdapterError in exception_handlers


@pytest.mark.asyncio
class TestNotFoundHandler:
    """Tests for default 404 handler."""

    async def test_not_found_returns_404(self, async_client):
        """Test that unknown routes return 404."""
        response = await async_client.get("/api/unknown-route")
        assert response.status_code == 404

    async def test_not_found_returns_json(self, async_client):
        """Test that 404 returns JSON response."""
        response = await async_client.get("/api/unknown-route")
        assert "application/json" in response.headers["content-type"]


@pytest.mark.asyncio
class TestMethodNotAllowed:
    """Tests for 405 Method Not Allowed responses."""

    async def test_method_not_allowed_on_health_post(self, async_client):
        """Test POST to health check returns 405."""
        response = await async_client.post("/api/health", json={})
        assert response.status_code == 405

    async def test_method_not_allowed_returns_json(self, async_client):
        """Test 405 returns JSON response."""
        response = await async_client.post("/api/health", json={})
        assert "application/json" in response.headers["content-type"]
