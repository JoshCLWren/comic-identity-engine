"""API package for Comic Identity Engine HTTP API.

This module provides the main entry point for the HTTP API with:
- create_app: FastAPI application factory
- dependencies: FastAPI dependency injection functions
- schemas: Pydantic request/response schemas
- routers: API route handlers

USAGE:
    from comic_identity_engine.api import create_app, dependencies, schemas

    app = create_app()
    app.include_router(routers.identity_router, prefix="/api/v1")
"""

from comic_identity_engine.api.main import create_app
from comic_identity_engine.api import dependencies, schemas
from comic_identity_engine.api import routers

__all__ = [
    "create_app",
    "dependencies",
    "schemas",
    "routers",
]
