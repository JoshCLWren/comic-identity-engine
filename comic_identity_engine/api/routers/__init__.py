"""Router package for Comic Identity Engine HTTP API.

This module provides FastAPI routers for the HTTP API:
- identity_router: Identity resolution endpoints
- jobs_router: Job management endpoints
- import_router: Import endpoints for CSV files
- corrections_router: Mapping correction endpoints
- all_routers: List of all available routers for bulk registration

USAGE:
    from comic_identity_engine.api.routers import all_routers

    app = create_app()
    for router in all_routers:
        app.include_router(router)
"""

from comic_identity_engine.api.routers.identity import router as identity_router
from comic_identity_engine.api.routers.jobs import router as jobs_router
from comic_identity_engine.api.routers.import_router import router as import_router
from comic_identity_engine.api.routers.inventory import router as inventory_router
from comic_identity_engine.api.routers.corrections import router as corrections_router
from comic_identity_engine.api.routers.ui import router as ui_router

all_routers = [
    identity_router,
    jobs_router,
    import_router,
    inventory_router,
    corrections_router,
    ui_router,
]

__all__ = [
    "identity_router",
    "jobs_router",
    "import_router",
    "inventory_router",
    "corrections_router",
    "ui_router",
    "all_routers",
]
