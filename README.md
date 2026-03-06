# Comic Identity Engine

Domain-specific entity resolution system for comic books.

## Current Status

**Phase**: Production-Ready MVP

### Completed Components

1. **Issue Number Parsing** ✅
   - Location: `comic_identity_engine/parsing.py`
   - Function: `parse_issue_candidate(raw: str) -> ParseResult`
   - Test coverage: 32 tests, all passing
   - Supports: negative numbers, decimals, fractions, variants, leading zeros
   - Error handling: EMPTY_INPUT, ONLY_SEPARATOR, INVALID_FORMAT, MULTI_ISSUE_RANGE

2. **Database Layer** ✅
   - Location: `comic_identity_engine/database/`
   - ORM: SQLAlchemy 2.0 with asyncpg
   - Models: `SeriesRun`, `Issue`, `Variant`, `ExternalMapping`, `Operation`
   - Repositories: Full CRUD for all entities
   - Migrations: Alembic with 3 migrations (schema, seed data, constraints)
   - Test coverage: 37 tests for models and repositories

3. **Platform Adapters** ✅ (7 platforms)
   - Location: `comic_identity_engine/adapters/`
   - Base: `SourceAdapter` abstract class
   - Implemented: GCD, LoCG, CCL, AA, CPG, HIP, CLZ
   - Exceptions: `AdapterError`, `NotFoundError`, `ValidationError`, `SourceError`

4. **Identity Resolution Service** ✅
   - Location: `comic_identity_engine/services/identity_resolver.py`
   - Cross-platform issue search by UPC, issue number, or URL
   - Confidence scoring with explainable matches
   - Test coverage: 200+ tests for cross-platform search

5. **REST API** ✅
   - Location: `comic_identity_engine/api/`
   - Framework: FastAPI with uvicorn
   - Routers: `/identity`, `/jobs`
   - Documentation: Auto-generated OpenAPI docs
   - Test coverage: 20+ tests for API endpoints

6. **CLI** ✅
   - Location: `comic_identity_engine/cli/`
   - Commands: `cie-find`, `cie-import-clz`, `cie-admin`, `cie-worker`
   - Features: Interactive search, bulk import, job management

7. **Job Queue** ✅
   - Location: `comic_identity_engine/jobs/`
   - Backend: arq with Redis
   - Features: Async operations, retry logic, progress tracking
   - AIP-151 compliant operation tracking

8. **Cache Layer** ✅
   - Location: `comic_identity_engine/core/cache/`
   - Implementations: Memory cache, Redis singleton, Tiered cache
   - Features: HTTP caching decorator, TTL support

### Test Coverage

- **Total tests**: 1,191 tests collected
- **Coverage**: 98.83% (exceeds 98% requirement)
- **Test frameworks**: pytest, pytest-asyncio, pytest-cov

### Research Data

Platform research for X-Men #-1 across 7 platforms:
- Grand Comics Database (GCD)
- League of Comic Geeks (LoCG)
- Comic Collector Live (CCL)
- Atomic Avenue (AA)
- Comics Price Guide (CPG)
- HIP Comic
- CLZ (Collectorz.com)

See `examples/` for raw data and cross-platform comparison.

### Architecture Decisions

- **Issue numbers stored as strings** - never cast to int
- **UUID-based internal IDs** - global uniqueness without coordination
- **Canonical issue number** - normalized, separate from display format
- **Variant suffixes** - extracted and stored separately
- **External IDs mapping** - platform-specific IDs (GCD, LoCG, CCL, etc.)
- **Repository pattern** - abstracts database access from business logic
- **Async-first** - all I/O operations are async for performance

## Project Structure

```
comic-identity-engine/
├── comic_identity_engine/
│   ├── __init__.py
│   ├── parsing.py          # Issue number parsing logic
│   ├── models.py           # Candidate data models
│   ├── config.py           # Configuration management
│   ├── errors.py           # Custom exceptions
│   ├── adapters/           # Platform adapters
│   │   ├── base.py         # Abstract base class
│   │   ├── gcd.py          # Grand Comics Database
│   │   ├── locg.py         # League of Comic Geeks
│   │   ├── ccl.py          # Comic Collector Live
│   │   ├── aa.py           # Atomic Avenue
│   │   ├── cpg.py          # Comics Price Guide
│   │   ├── hip.py          # HIP Comic
│   │   └── clz.py          # CLZ Comics
│   ├── api/                # REST API
│   │   ├── main.py         # FastAPI app factory
│   │   ├── schemas.py      # Pydantic models
│   │   ├── dependencies.py # Dependency injection
│   │   └── routers/        # API route handlers
│   ├── cli/                # Command-line interface
│   │   ├── main.py         # CLI entry point
│   │   └── commands/       # CLI commands
│   ├── services/           # Business logic
│   │   ├── identity_resolver.py  # Cross-platform search
│   │   ├── operations.py         # Job tracking
│   │   ├── url_builder.py        # URL construction
│   │   └── url_parser.py         # URL parsing
│   ├── database/           # Database layer
│   │   ├── models.py       # SQLAlchemy ORM models
│   │   ├── repositories.py # Repository classes
│   │   ├── connection.py   # DB connection management
│   │   └── migrations/     # Alembic migrations
│   ├── jobs/               # Async job queue
│   │   ├── worker.py       # arq worker
│   │   ├── queue.py        # Queue configuration
│   │   └── tasks.py        # Job tasks
│   └── core/               # Core utilities
│       ├── cache/          # Caching layer
│       ├── http_client.py  # HTTP client wrapper
│       └── interfaces.py   # Core interfaces
├── tests/                  # Test suite (1,191 tests)
│   ├── test_parsing.py
│   ├── test_gcd_adapter.py
│   ├── test_adapters/      # Adapter tests
│   ├── test_api/           # API tests
│   ├── test_cli/           # CLI tests
│   ├── test_jobs/          # Job queue tests
│   ├── test_services/      # Service tests
│   └── test_database.py    # Database tests
├── examples/               # Usage examples and research
│   ├── edge-cases/         # Edge case research
│   ├── gcd/                # GCD data samples
│   ├── locg/               # LoCG data samples
│   ├── ccl/                # CCL data samples
│   ├── aa/                 # AA data samples
│   ├── cpg/                # CPG data samples
│   ├── hipcomic/           # HIP data samples
│   ├── clz/                # CLZ data samples
│   └── COMPARISON.md       # Cross-platform analysis
├── AGENTS.md               # Agent guidelines
└── README.md               # Project overview
```

## Quick Setup

### Environment Setup

This project uses [`uv`](https://github.com/astral-sh/uv) for dependency management and [`direnv`](https://direnv.net/) for environment variables:

```bash
# One-time setup
uv sync
direnv allow  # Loads .envrc automatically

# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=comic_identity_engine
```

### Docker-Based CI (Recommended)

```bash
# Build and run all tests locally using Docker
docker compose build ci
docker compose run --rm ci
```

### Shell Aliases (Optional)

For convenience, add shell aliases to run commands without `uv run`:

**Zsh** - Add to `~/.zshrc`:
```bash
source /path/to/comic-identity-engine/.zshrc.local
```

**Bash** - Add to `~/.bashrc`:
```bash
source /path/to/comic-identity-engine/.bashrc.local
```

See [SHELL.md](SHELL.md) for details.

## Usage

### Command-Line Interface

```bash
# Find an issue by UPC (cross-platform search)
cie-find 75960601772099911

# Find an issue by URL (auto-detects platform)
cie-find https://www.comiccollectorlive.com/...
cie-find https://leagueofcomicgeeks.com/...

# Import CLZ backup file
cie-import-clz backup.clz

# Run the job worker
cie-worker

# Admin commands
cie-admin db migrate
cie-admin db seed
```

### Python API

#### Parse Issue Numbers

```python
from comic_identity_engine.parsing import parse_issue_candidate

result = parse_issue_candidate("-1A")

if result.success:
    print(f"Canonical: {result.canonical_issue_number}")  # "-1"
    print(f"Variant: {result.variant_suffix}")            # "A"
else:
    print(f"Error: {result.error_code} - {result.error_message}")
```

#### Cross-Platform Identity Resolution

```python
from comic_identity_engine.database import get_db
from comic_identity_engine.services.identity_resolver import IdentityResolver

async def find_issue():
    async for db in get_db():
        resolver = IdentityResolver(db)
        
        # Find by UPC (searches all platforms)
        result = await resolver.find_by_upc("75960601772099911")
        
        if result.matches:
            for match in result.matches:
                print(f"Found: {match.series_title} #{match.issue_number}")
                print(f"Confidence: {match.overall_confidence}")
                print(f"Explanation: {match.explanation}")
```

#### Database Operations

```python
from comic_identity_engine.database import (
    SeriesRunRepository,
    IssueRepository,
    ExternalMappingRepository,
    get_db,
)

async def example_usage():
    async for db in get_db():
        # Create series
        series_repo = SeriesRunRepository(db)
        series = await series_repo.create(
            title="X-Men",
            start_year=1991,
            publisher="Marvel Comics",
        )

        # Create issue
        issue_repo = IssueRepository(db)
        issue = await issue_repo.create(
            series_run_id=series.id,
            issue_number="-1",
            upc="75960601772099911",
        )

        # Create external mapping
        mapping_repo = ExternalMappingRepository(db)
        await mapping_repo.create_mapping(
            issue_id=issue.id,
            source="gcd",
            source_issue_id="125295",
            source_series_id="4254",
        )
```

### REST API

```bash
# Start the API server
uv run uvicorn comic_identity_engine.api.main:create_app --reload

# Find an issue by UPC
curl http://localhost:8000/api/v1/identity/find?upc=75960601772099911

# Find an issue by URL
curl "http://localhost:8000/api/v1/identity/find?url=https://..."

# Check job status
curl http://localhost:8000/api/v1/jobs/{operation_id}
```

The API includes auto-generated OpenAPI documentation at `http://localhost:8000/docs`.

## Development Guidelines

See `AGENTS.md` for detailed:
- Code style guidelines
- Testing requirements
- Architecture patterns
- Platform adapter guidelines

## License

[To be determined]
