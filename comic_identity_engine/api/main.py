"""FastAPI application for Comic Identity Engine HTTP API.

This module provides the main FastAPI application factory with:
- Health check endpoints
- CORS configuration
- Router registration
- Custom exception handlers
- OpenAPI documentation
- Lifespan management for startup/shutdown

The API follows AIP-151 and AIP-236 for long-running operations and custom methods.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from comic_identity_engine.api.routers import all_routers
from comic_identity_engine.api.routers.ui import router as ui_router
from comic_identity_engine.config import get_settings
from comic_identity_engine.core.cache import redis_cache
from comic_identity_engine.database.connection import test_database_connection
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

STATIC_DIR = Path(__file__).parent.parent / "static"


def _setup_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers for custom errors."""

    @app.exception_handler(EntityNotFoundError)
    async def entity_not_found_handler(
        request: Request, exc: EntityNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "ENTITY_NOT_FOUND",
                    "message": str(exc),
                    "entity_type": exc.entity_type,
                    "entity_id": exc.entity_id,
                }
            },
        )

    @app.exception_handler(DuplicateEntityError)
    async def duplicate_entity_handler(
        request: Request, exc: DuplicateEntityError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "DUPLICATE_ENTITY",
                    "message": str(exc),
                    "entity_type": exc.entity_type,
                    "existing_id": exc.existing_id,
                }
            },
        )

    @app.exception_handler(ValidationError)
    async def validation_error_handler(
        request: Request, exc: ValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": str(exc),
                }
            },
        )

    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(
        request: Request, exc: AuthenticationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": "AUTHENTICATION_ERROR",
                    "message": str(exc),
                }
            },
        )

    @app.exception_handler(RateLimitError)
    async def rate_limit_handler(request: Request, exc: RateLimitError) -> JSONResponse:
        headers = {}
        if exc.retry_after:
            headers["Retry-After"] = str(exc.retry_after)
        return JSONResponse(
            status_code=429,
            headers=headers,
            content={
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": str(exc),
                    "retry_after": exc.retry_after,
                }
            },
        )

    @app.exception_handler(NetworkError)
    async def network_error_handler(
        request: Request, exc: NetworkError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "code": "NETWORK_ERROR",
                    "message": str(exc),
                    "source": exc.source,
                }
            },
        )

    @app.exception_handler(ParseError)
    async def parse_error_handler(request: Request, exc: ParseError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "PARSE_ERROR",
                    "message": str(exc),
                }
            },
        )

    @app.exception_handler(ResolutionError)
    async def resolution_error_handler(
        request: Request, exc: ResolutionError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "RESOLUTION_ERROR",
                    "message": str(exc),
                    "confidence": exc.confidence,
                    "candidates_count": len(exc.candidates),
                }
            },
        )

    @app.exception_handler(AdapterError)
    async def adapter_error_handler(
        request: Request, exc: AdapterError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "ADAPTER_ERROR",
                    "message": str(exc),
                    "source": exc.source,
                }
            },
        )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan (startup/shutdown).

    On startup:
    - Initialize Redis connection
    - Test database connection

    On shutdown:
    - Close Redis cache connection
    - Close job queue connection
    """
    settings = get_settings()

    await redis_cache.initialize(settings.redis.cache_url)

    db_connected = await test_database_connection()
    if not db_connected:
        raise RuntimeError("Failed to connect to database")

    yield

    await redis_cache.close()

    from comic_identity_engine.api.dependencies import close_job_queue

    await close_job_queue()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        FastAPI: Configured FastAPI application instance.
    """
    settings = get_settings()

    app = FastAPI(
        title="Comic Identity Engine API",
        description=(
            "A domain-specific entity resolution system for comic books. "
            "Provides identity resolution across multiple comic platforms."
        ),
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=_lifespan,
    )

    _setup_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint.

        Returns:
            dict: Status information indicating API is operational.
        """
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    async def root():
        return RedirectResponse(url="/ui/inventory")

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    for router in all_routers:
        if router != ui_router:
            app.include_router(router, prefix="/api/v1")

    app.include_router(ui_router)

    return app
