# Reusable Code Mapping Document

**Purpose:** Maps all reusable code from existing projects to Comic Identity Engine components.

**Generated:** 2025-01-31
**Source Projects:** comic-pile, comics_backend, comic-web-scrapers, comic_matcher, comic_pricer

---

## Directory Structure Map

```
comic-identity-engine/
├── comic_identity_engine/
│   ├── config.py              # [NEW] From comic-pile/app/config.py
│   ├── database.py            # [NEW] From comic-pile/app/database.py
│   ├── errors.py              # [NEW] From comic-web-scrapers/common/errors.py
│   ├── __init__.py            # [EXISTS] Package exports
│   ├── parsing.py             # [EXISTS] Issue number parser (54 tests)
│   ├── models.py              # [EXISTS] Candidate models
│   ├── core/                  # [NEW] Core infrastructure
│   │   ├── __init__.py
│   │   ├── cache/             # [NEW] Cache implementations
│   │   │   ├── __init__.py
│   │   │   ├── redis_singleton.py   # From comic-web-scrapers/common/redis_singleton.py
│   │   │   ├── memory_cache.py      # From comic-web-scrapers/common/cache.py
│   │   │   ├── http_cache.py        # From comic-web-scrapers/common/http_cache_decorator.py
│   │   │   └── middleware.py        # From comics_backend/app/cache.py
│   │   ├── http/              # [NEW] HTTP client infrastructure
│   │   │   ├── __init__.py
│   │   │   ├── session_manager.py   # From comic-web-scrapers/common/session_manager.py
│   │   │   └── client.py            # From comic-web-scrapers/api/client.py
│   │   ├── matching/         # [NEW] Identity resolution algorithms
│   │   │   ├── __init__.py
│   │   │   ├── fuzzy.py            # From comics_backend/app/routers/library/search_utils.py
│   │   │   └── resolver.py         # [NEW] Our implementation
│   │   └── logging/          # [NEW] Structured logging
│   │       ├── __init__.py
│   │       └── config.py          # From comic-web-scrapers/common/logging_config.py
│   ├── services/             # [NEW] Business logic services
│   │   ├── __init__.py
│   │   ├── url_parser.py        # [NEW] URL parsing for all 7 platforms
│   │   ├── identity_resolver.py  # [NEW] Core identity resolution logic
│   │   ├── url_builder.py        # [NEW] URL building for all platforms
│   │   └── operations.py         # [NEW] Operations tracking (AIP-151)
│   ├── adapters/             # [EXISTS] Platform adapters
│   │   ├── __init__.py
│   │   ├── base.py              # [EXISTS] SourceAdapter abstract class
│   │   ├── gcd.py               # [EXISTS] GCD adapter (22 tests)
│   │   ├── locg.py              # [NEW] League of Comic Geeks adapter
│   │   ├── ccl.py               # [NEW] ComicCollectorLive adapter
│   │   ├── aa.py                # [NEW] Atomic Avenue adapter
│   │   ├── cpg.py               # [NEW] Comics Price Guide adapter
│   │   ├── hip.py               # [NEW] HipComic adapter
│   │   └── clz.py               # [NEW] CLZ CSV importer adapter
│   ├── database/             # [NEW] Database layer
│   │   ├── __init__.py
│   │   ├── models.py            # [NEW] SQLAlchemy ORM models
│   │   ├── repositories.py      # [NEW] Repository pattern
│   │   └── migrations/          # [NEW] Alembic migrations
│   ├── jobs/                 # [NEW] arq job queue workers
│   │   ├── __init__.py
│   │   ├── worker.py            # [NEW] arq worker entrypoint
│   │   └── functions.py         # [NEW] Job functions
│   ├── api/                  # [NEW] FastAPI HTTP API
│   │   ├── __init__.py
│   │   ├── app.py              # From comic-pile/app/main.py (adapted)
│   │   ├── routes/             # [NEW] API routes
│   │   │   ├── __init__.py
│   │   │   ├── issues.py       # [NEW] Issue endpoints
│   │   │   ├── series.py       # [NEW] Series endpoints
│   │   │   ├── operations.py   # [NEW] Operation status endpoints
│   │   │   └── health.py       # [NEW] Health check
│   │   └── middleware/         # [NEW] Custom middleware
│   │       ├── __init__.py
│   │       ├── cache.py        # From comics_backend/app/cache.py
│   │       └── errors.py       # [NEW] Error handling middleware
│   └── cli/                  # [NEW] CLI commands
│       ├── __init__.py
│       ├── main.py             # [NEW] CLI entrypoint (click/typer)
│       └── commands/
│           ├── __init__.py
│           ├── find.py         # [NEW] cie-find command
│           ├── import_clz.py   # [NEW] cie-import-clz command
│           └── admin.py        # [NEW] cie-admin command
├── tests/
│   ├── __init__.py
│   ├── conftest.py            # From comic-pile/tests/conftest.py (adapted)
│   ├── test_parsing.py        # [EXISTS] 32 tests, all passing
│   ├── test_gcd_adapter.py    # [EXISTS] 22 tests, all passing
│   └── [NEW] Additional test files
├── docker/
│   ├── Dockerfile             # From comic-pile/Dockerfile (adapted)
│   └── docker-compose.yml     # From comic-pile/docker-compose.yml (adapted)
├── pyproject.toml             # [EXISTS] Updated with dependencies
└── IMPLEMENTATION_PLAN.md     # [EXISTS] 1,480-line implementation plan
```

---

## Component Mapping

### 1. Configuration Management

**Source:** `/mnt/extra/josh/code/comic-pile/app/config.py` (268 lines)

**Destination:** `comic_identity_engine/config.py`

**Usage:**
- Database configuration (PostgreSQL connection URLs)
- API configuration (CORS, debug routes, etc.)
- Redis configuration (job queue DB 0, cache DB 1)
- Application environment (dev/test/prod)

**Changes Needed:**
- Remove: AuthSettings, SessionSettings, RatingSettings (comic-pile specific)
- Add: RedisSettings (for job queue and cache)
- Add: ArqSettings (for job queue configuration)
- Keep: DatabaseSettings (perfect fit), AppSettings (with modifications)

**Related Files:**
- Used by: `database.py`, `api/app.py`, `jobs/worker.py`
- Environment: `.env`, `.env.example`

---

### 2. Database Connection Management

**Source:** `/mnt/extra/josh/code/comic-pile/app/database.py` (81 lines)

**Destination:** `comic_identity_engine/database.py`

**Usage:**
- SQLAlchemy async engine setup
- Connection pooling configuration
- Async session factory
- Dependency injection for FastAPI
- Base class for ORM models
- Connection testing

**Changes Needed:**
- Update imports: `from comic_identity_engine.config import get_database_settings`
- None otherwise (perfect fit)

**Related Files:**
- Used by: All database operations, API endpoints, tests
- Migrations: `alembic/env.py`

---

### 3. Error Handling Hierarchy

**Source:** `/mnt/extra/josh/code/comic-web-scrapers/comic_scrapers/common/errors.py` (103 lines)

**Destination:** `comic_identity_engine/errors.py`

**Usage:**
- Platform adapter error handling
- Network error handling for HTTP requests
- Parse error handling for HTML/JSON responses
- Validation errors for user input
- Rate limiting errors

**Changes Needed:**
- Rename: `ScraperError` → `AdapterError` (already exists in our `adapters/base.py`)
- Keep: All specialized error types
- Add: `ResolutionError` for identity resolution failures

**Related Files:**
- Used by: All platform adapters, identity resolver, API error handlers

---

### 4. Redis Singleton (Connection Pool)

**Source:** `/mnt/extra/josh/code/comic-web-scrapers/comic_scrapers/common/redis_singleton.py` (198 lines)

**Destination:** `comic_identity_engine/core/cache/redis_singleton.py`

**Usage:**
- Job queue (arq uses Redis internally)
- Application cache (DB 1)
- HTTP response cache (for FastAPI)
- Progress tracking for long-running jobs

**Changes Needed:**
- Support multiple databases (DB 0 for arq, DB 1 for cache)
- Add connection pool sizing options
- Keep: JSON/pickle serialization

**Related Files:**
- Used by: `api/middleware/cache.py`, `services/operations.py`, `jobs/worker.py`

---

### 5. HTTP Session Management

**Source:** `/mnt/extra/josh/code/comic-web-scrapers/comic_scrapers/common/session_manager.py` (342 lines)

**Destination:** `comic_identity_engine/core/http/session_manager.py`

**Usage:**
- Platform adapter HTTP requests (CCL, AA, CPG, HIP, LoCG)
- Connection pooling for performance
- Proper cleanup on shutdown
- Resource exhaustion handling

**Changes Needed:**
- Update imports: `from comic_identity_engine.errors import NetworkError, ResourceExhaustedError`
- Consider switching to httpx (we decided to use httpx only, not aiohttp)

**Related Files:**
- Used by: All platform adapters (except GCD which uses their API client)

---

### 6. In-Memory Cache with LRU

**Source:** `/mnt/extra/josh/code/comic-web-scrapers/comic_scrapers/common/cache.py` (263 lines)

**Destination:** `comic_identity_engine/core/cache/memory_cache.py`

**Usage:**
- Local caching within adapter instances
- Reducing redundant HTTP requests
- Per-key locks for concurrency

**Changes Needed:**
- None (perfect fit)

**Related Files:**
- Used by: Platform adapters, identity resolver

---

### 7. HTTP Cache Decorator

**Source:** `/mnt/extra/josh/code/comic-web-scrapers/comic_scrapers/common/http_cache_decorator.py` (104 lines)

**Destination:** `comic_identity_engine/core/cache/http_cache.py`

**Usage:**
- Caching HTTP responses from platform APIs
- Reducing rate limit hits
- Configurable TTL per request

**Changes Needed:**
- Update imports to use our Redis singleton

**Related Files:**
- Used by: Platform adapters

---

### 8. Redis Cache Middleware (Advanced)

**Source:** `/mnt/extra/josh/code/comics_backend/app/cache.py` (432 lines)

**Destination:** `comic_identity_engine/api/middleware/cache.py`

**Usage:**
- FastAPI response caching
- Tag-based invalidation
- Cache versioning
- Related resource invalidation

**Changes Needed:**
- Update imports for our models and routes
- Customize tag derivation for our domain (series, issues, operations)

**Related Files:**
- Used by: `api/app.py`

---

### 9. Fuzzy Matching / Entity Resolution

**Source:** `/mnt/extra/josh/code/comics_backend/app/routers/library/search_utils.py` (91 lines)

**Destination:** `comic_identity_engine/core/matching/fuzzy.py`

**Usage:**
- Cross-platform series name matching
- Title normalization and tokenization
- Confidence scoring for matches

**Changes Needed:**
- Consider using jellyfish for Jaro-Winkler (already in dependencies)
- Keep token-based matching as fallback

**Related Files:**
- Used by: `services/identity_resolver.py`

---

### 10. API Client Pattern

**Source:** `/mnt/extra/josh/code/comic-web-scrapers/comic_scrapers/api/client.py` (195 lines)

**Destination:** `comic_identity_engine/core/http/client.py`

**Usage:**
- Pattern for building platform-specific API clients
- Batch operations support
- Error handling

**Changes Needed:**
- Convert to httpx (currently uses httpx actually, so may be fine)
- Update for our domain model

**Related Files:**
- Used by: As reference for GCD adapter and other API clients

---

### 11. Progress Tracking

**Source:** `/mnt/extra/josh/code/comic-web-scrapers/comic_scrapers/common/redis_progress.py` (262 lines)

**Destination:** `comic_identity_engine/core/progress.py` (or similar)

**Usage:**
- Long-running job progress (CLZ import, bulk operations)
- Real-time progress updates
- Stale job detection

**Changes Needed:**
- Update imports for our Redis singleton
- Integrate with arq job context

**Related Files:**
- Used by: `jobs/functions.py`, `cli/commands/import_clz.py`

---

### 12. FastAPI Application Factory

**Source:** `/mnt/extra/josh/code/comic-pile/app/main.py` (609 lines)

**Destination:** `comic_identity_engine/api/app.py`

**Usage:**
- FastAPI app initialization
- Middleware setup
- Exception handlers
- CORS configuration
- Security headers
- Graceful shutdown

**Changes Needed:**
- Remove: Authentication middleware (no auth)
- Remove: Rating-specific routes
- Add: Our API routes (issues, series, operations)
- Keep: Error handling patterns, CORS, health checks

**Related Files:**
- Entry point: `cie-api` CLI command

---

### 13. Pytest Configuration & Fixtures

**Source:** `/mnt/extra/josh/code/comic-pile/tests/conftest.py` (460 lines)

**Destination:** `tests/conftest.py`

**Usage:**
- Async database fixtures
- Test client fixtures
- Authentication fixtures (can remove)
- Sample data generation

**Changes Needed:**
- Remove: Auth fixtures
- Update: Model imports for our domain
- Add: Platform adapter fixtures

**Related Files:**
- Used by: All test files

---

### 14. CLI Implementation

**Source:** `/mnt/extra/josh/code/comic_matcher/comic_matcher/cli.py` (176 lines)

**Destination:** `comic_identity_engine/cli/main.py` and `cli/commands/*.py`

**Usage:**
- Command structure
- Argument parsing
- Logging configuration

**Changes Needed:**
- Convert to Click or Typer (comic-pile uses FastAPI, not CLI)
- Add our commands: cie-find, cie-import-clz, cie-admin

**Related Files:**
- Entry points: `cie-find`, `cie-import-clz`, `cie-admin`

---

### 15. Dockerfile (Multi-stage)

**Source:** `/mnt/extra/josh/code/comic-pile/Dockerfile` (93 lines)

**Destination:** `docker/Dockerfile`

**Usage:**
- Container image for deployment
- Multi-stage build for smaller image

**Changes Needed:**
- Remove: Frontend build stage (we're API-only)
- Keep: Python builder stage
- Keep: Non-root user setup

**Related Files:**
- docker-compose.yml, deployment

---

### 16. Docker Compose

**Source:** `/mnt/extra/josh/code/comic-pile/docker-compose.yml` (59 lines)

**Destination:** `docker/docker-compose.yml`

**Usage:**
- Local development environment
- PostgreSQL service
- Redis service

**Changes Needed:**
- Add: Redis service (currently only has PostgreSQL)
- Remove: pgAdmin (not needed for development)
- Add: Application service

**Related Files:**
- Local development, .env configuration

---

## Dependency Map

### Already in pyproject.toml ✅

- `pydantic>=2.9` - Configuration, models
- `pydantic-settings>=2.6` - Settings management
- `asyncpg>=0.30` - PostgreSQL async driver
- `alembic>=1.14` - Database migrations
- `sqlalchemy>=2.0` - ORM
- `redis>=5.2` - Redis client
- `arq>=0.26` - Job queue
- `httpx>=0.28` - HTTP client
- `tenacity>=9.0` - Retry logic
- `jellyfish>=1.1` - Fuzzy matching
- `fastapi>=0.115` - API framework
- `uvicorn[standard]>=0.32` - ASGI server
- `click>=8.1` - CLI framework
- `python-dotenv>=1.0` - Environment loading
- `structlog>=25.1` - Structured logging

### Need to Consider Adding

- `slowapi` - Rate limiting (from comic-pile) - **OPTIONAL**
- `selectolax>=0.3` - HTML parsing (already listed)

---

## Implementation Order

### Phase 1: Core Infrastructure (Current)

1. ✅ Copy `config.py` (with modifications for our domain)
2. ✅ Copy `database.py` (update imports)
3. ✅ Copy `errors.py` (rename ScraperError, add ResolutionError)
4. ✅ Copy `redis_singleton.py` to `core/cache/`
5. ✅ Copy `session_manager.py` to `core/http/` (or convert to httpx)
6. ✅ Copy `memory_cache.py` to `core/cache/`

### Phase 2: API & Testing Foundation

7. ✅ Copy `cache.py` (middleware) to `api/middleware/`
8. ✅ Copy `fuzzy.py` to `core/matching/`
9. ✅ Copy `main.py` (FastAPI app factory) to `api/app.py`
10. ✅ Copy `conftest.py` to `tests/`

### Phase 3: DevOps

11. ✅ Copy `Dockerfile` to `docker/`
12. ✅ Copy `docker-compose.yml` to `docker/`

---

## Notes

- **aiohttp vs httpx**: We decided to use httpx only, but the session_manager.py uses aiohttp. We'll need to either:
  a) Convert the session manager to httpx, or
  b) Use httpx for API clients (GCD) and aiohttp for web scraping (CCL, AA, CPG, HIP, LoCG)
  
- **Database isolation**: Use DB 0 for arq job queue, DB 1 for application cache

- **Testing**: All tests use `uv run pytest` due to uv dependency management

---

**Next Steps:**
1. Begin copying Priority 1 components with annotations
2. Set up the infrastructure layer
3. Test database and Redis connectivity
4. Begin implementing platform adapters
