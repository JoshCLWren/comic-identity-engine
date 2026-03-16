# AGENTS.md

Guidelines for AI agents working in this codebase.

## Agent Ownership Policy

All AI agents working in this codebase are **high-ownership agents**.

**Key Principle**: If you find a bug (pre-existing or new), it is your responsibility to fix it. You are not a lazy AI that ignores problems and pushes them to human reviewers.

## CORE PRINCIPLE: NEVER SKIP TESTS

**⚠️ TESTS MUST NEVER BE SKIPPED - EVER.**

If a test is failing:
- ✅ FIX THE TEST
- ✅ FIX THE CODE THAT BREAKS THE TEST
- ✅ INVESTIGATE ROOT CAUSE
- ❌ **NEVER SKIP THE TEST**

**This applies to:**
- All automated tests (unit, integration)
- All developers (human and AI)
- All situations (no exceptions)

**Rationale:**
- Skipped tests hide broken functionality
- They create technical debt immediately
- They undermine confidence in the test suite
- They are lazy and unacceptable

**If you're tempted to skip a test, DON'T. Fix it instead.**

**Requirements:**
- **Never use `--no-verify` or bypass hooks** to avoid fixing issues
- **Never say "this is pre-existing" and walk away** - fix it anyway
- **Fix all test failures** before committing, even if the failure appears to be pre-existing
- **Write regression tests** for bugs you find and fix
- **Update documentation** when you find gaps or outdated information

**If a test fails**:
1. Investigate why it fails
2. Fix the root cause (even if "pre-existing")
3. Verify the fix works
4. Add a regression test if applicable

**If you find documentation gaps**:
1. Update the relevant documentation
2. Add examples if helpful

---

## ⚠️ CRITICAL: READ THESE DOCS FIRST ⚠️

**BEFORE modifying cross-platform search or import code, you MUST read:**

1. **SERIES_PAGE_STRATEGY.md** - The PRIMARY strategy for bulk imports
   - Explains why series page extraction is 10-100x faster
   - Shows platform-specific URL patterns (GCD, AA, CPG, CCL, LoCG)
   - Provides code examples for each platform
   - **This is what you should implement for CSV imports!**

2. **CROSS_PLATFORM_SEARCH.md** - Individual issue search strategy
   - For single issue lookups (CLI: cie-find)
   - For edge cases and testing
   - NOT for bulk imports!

3. **FIX_PLAN.md** - Active fix plan for known issues
   - Current test failures and how to fix them
   - Incomplete consolidation migration work
   - Production bugs that need fixing

**If you don't read these, you will implement the wrong thing and frustrate the user.**

---

## Project Overview

Comic Identity Engine is a domain-specific entity resolution system for comic books supporting 7 platforms (GCD, LoCG, CCL, AA, HipComic, CPG, CLZ).

**Tech Stack:**
- **Backend**: Python 3.13, FastAPI, SQLAlchemy, PostgreSQL, Redis
- **Worker**: arq job queue with Playwright browser automation
- **Package managers**: `uv` (Python), Docker (infrastructure)
- **Shared packages**: `longbox-commons`, `scrapekit`, `longbox-scrapers`, `longbox-matcher`

---

## Build/Lint/Test Commands

### Environment Setup
```bash
# Initial setup
uv sync

# After cd-ing into the project, direnv automatically loads .envrc
# If direnv is not installed, manually activate:
source .venv/bin/activate
```

### Linting
```bash
make lint                    # Run all linters
bash scripts/lint.sh         # Same as above
bash scripts/lint.sh --staged # Check only staged files
ruff check .                 # Python linting only
ruff format .                # Format code
```

### Testing
```bash
uv run pytest                           # All tests
uv run pytest tests/test_adapters/ -v   # Specific directory
uv run pytest tests/test_adapters/test_gcd.py::test_gcd_issue_parser -v  # Single test
uv run pytest -k "resolve_identity" -v  # Pattern matching
uv run pytest --cov=comic_identity_engine  # With coverage
```

### Docker/Infrastructure
```bash
# Start infrastructure only (recommended for development)
docker compose up -d postgres-app redis

# Run the app locally
uv run cie-api
uv run cie-worker

# Run everything in Docker (CI mode)
docker compose build ci
docker compose run --rm ci
```

---

## Common Patterns

### Async/Await: Avoid MissingGreenlet Errors

**❌ WRONG - Causes MissingGreenlet:**
```python
# Accessing data after session commit
await db.commit()
return IssueResponse(title=issue.title)  # Session expired!
```

**✅ CORRECT - Extract before commit:**
```python
# Extract all data BEFORE committing
issue_title = issue.title
issue_number = issue.issue_number
series_id = issue.series_id

await db.commit()

return IssueResponse(
    title=issue_title,
    number=issue_number,
    series_id=series_id
)
```

**Why this matters:**
- SQLAlchemy async sessions expire after commit
- Accessing attributes post-commit raises `MissingGreenlet` errors
- Always extract data before committing

### Database Sessions in Tests

**❌ WRONG - Synchronous engine:**
```python
from sqlalchemy import create_engine  # Sync!
engine = create_engine(database_url)
```

**✅ CORRECT - Async engine:**
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from comic_identity_engine.database.connection import get_async_session

engine = create_async_engine(database_url)
async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)
```

### Error Handling

**❌ WRONG - Bare except:**
```python
try:
    await risky_operation()
except:
    pass  # Silent failure - terrible!
```

**✅ CORRECT - Specific exceptions:**
```python
from structlog import get_logger

logger = get_logger(__name__)

try:
    await risky_operation()
except TimeoutError as e:
    logger.error("Timeout", operation="risky", error=str(e))
    raise
except Exception as e:
    logger.error("Unexpected error", operation="risky", error=str(e))
    raise
```

### HTTP Clients

**❌ WRONG - Direct httpx (no retry):**
```python
import httpx

async def fetch():
    async with httpx.AsyncClient() as client:
        response = await client.get(url)  # No retry, no rate limiting
        return response.json()
```

**✅ CORRECT - Use scrapekit:**
```python
from scrapekit import HttpClient

http = HttpClient(name="gcd", timeout=30.0)

async def fetch():
    response = await http.get(url)  # With retry, rate limiting, caching
    return response.json()
```

---

## Platform-Specific Patterns

### Browser Automation (Playwright)

**Important Notes:**
- Browser-backed scrapers behave differently in Docker
- Anti-bot systems fingerprint containerized browsers
- **Test locally before Docker deployment**

**✅ CORRECT - Local development:**
```bash
# Start only infrastructure in Docker
docker compose up -d postgres-app redis

# Run the app locally
uv run cie-api
uv run cie-worker
```

**⚠️ Docker testing only:**
```bash
# Use this for CI/verification, not primary development
docker compose build ci
docker compose run --rm ci
```

### CLZ CSV Import

**CLZ imports require special handling:**
- Series page extraction is 10-100x faster than individual issue lookups
- See `SERIES_PAGE_STRATEGY.md` for platform-specific URL patterns
- Use `platform_searcher.search_series_page()` for bulk imports
- Fall back to individual lookups only for edge cases

### Cross-Platform Search

**For individual issue lookups:**
```python
from comic_identity_engine.services.platform_searcher import PlatformSearcher

searcher = PlatformSearcher()
results = await searcher.search_comic(
    title="X-Men",
    issue="1",
    year=1963,
    publisher="Marvel"
)
```

**For bulk imports (CSV):**
```python
# Use series page extraction (much faster)
results = await searcher.search_series_page(url)
```

---

## Troubleshooting

### MissingGreenlet Errors

**Symptom:**
```
greenlet.GreenletExit: Greenlet exit
sqlalchemy.exc.PendingRollbackError: This Session's transaction has been rolled back
```

**Root Cause:** Accessing SQLAlchemy object attributes after `await db.commit()`

**Fix:** Extract all needed data before committing (see "Async/Await" pattern above)

### Tests Failing with "duplicate key value violates unique constraint"

**Symptom:**
```
sqlalchemy.exc.IntegrityError: duplicate key value violates unique constraint "uq_series_runs_title_start_year"
```

**Root Cause:** Tests not cleaning up database between runs

**Fix:**
- Use proper pytest fixtures with cleanup
- Use unique test data per test
- Check `tests/conftest.py` for examples

### Playwright "Executable doesn't exist" in CI

**Symptom:**
```
Executable doesn't exist at /github/home/.cache/ms-playwright/...
```

**Fix:** Add to CI workflow:
```yaml
- name: Install Playwright browsers
  run: playwright install --with-deps chromium
```

### Import Errors After Consolidation

**Symptom:**
```
ModuleNotFoundError: No module named 'comic_search_lib'
```

**Root Cause:** Consolidation moved scrapers to `longbox-scrapers`

**Fix:** Update imports:
```python
# Old
from comic_search_lib.scrapers.gcd import GCDScraper

# New
from longbox_scrapers import GCDAdapter
```

---

## Code Style Guidelines

1. **Explicit over Implicit**
   - Always use explicit imports
   - Avoid wildcard imports
   - Type hints required for all function signatures

2. **Naming Conventions**
   - `snake_case` for functions and variables
   - `PascalCase` for classes
   - `SCREAMING_SNAKE_CASE` for constants
   - Descriptive names over abbreviations

3. **Error Handling**
   - Use specific exception types
   - Never catch bare `Exception`
   - Always include context in error messages
   - Log errors at appropriate levels with structlog

4. **Documentation**
   - Docstrings for all public functions and classes
   - Follow Google style or NumPy style consistently
   - Include type information in docstrings if not using type hints

5. **Testing**
   - Unit tests for all business logic
   - Integration tests for external platform adapters
   - Tests must be deterministic (no randomness without seeded RNG)
   - Use descriptive test names: `test_xmen_negative_one_matches_canonical_issue()`

---

## Domain-Specific Conventions

1. **Issue Numbers**
   - Store as VARCHAR/string to support `-1`, `1/2`, `0`, `600.1`
   - Never cast to int without validation
   - Use normalized comparison for matching

2. **UUID Generation**
   - Internal Issue UUIDs are authoritative
   - Use UUID v4 for new entities
   - Never infer UUIDs from external IDs

3. **External Mappings**
   - Store external IDs, never infer repeatedly
   - Version platform adapters independently
   - Log all reconciliation attempts with confidence scores

---

## Architecture Patterns

### Core Model Hierarchy
```
SeriesRun
  └── Issue
        └── Variant (optional)
```

### Key Principles

1. **Canonical First**
   - Internal identity is authoritative
   - External systems are adapters

2. **Deterministic Before ML**
   - Clear parsing rules before ML
   - Every match produces confidence score + explanation

3. **Explainable Matching**
   - issue_confidence, variant_confidence, overall_confidence
   - Explanation field for all matches

### Service Layer

- **`identity_resolver`**: Database-backed entity resolution (stays in CIE)
- **`platform_searcher`**: Cross-platform search (uses `longbox-scrapers`)
- **`url_parser`**: URL parsing for all platforms
- **`operations`**: Import operation management

### Adapters

All adapters inherit from `SourceAdapter` (in `longbox-scrapers`):
- `AAAdapter` (Atomic Avenue)
- `CCLAdapter` (Comic Collector Live)
- `CPGAdapter` (Comics Price Guide)
- `GCDAdapter` (Grand Comics Database)
- `HIPAdapter` (HipComic)
- `LoCGAdapter` (League of Comic Geeks)
- `CLZAdapter` (Collectorz - CSV import only)

---

## Pre-commit Hooks

The pre-commit hook automatically blocks commits containing:
- Type ignores (`# type: ignore`)
- Linter ignores (`# noqa`, `# ruff: ignore`, `# pylint: ignore`)
- `Any` types (ruff ANN401 rule)
- Linting errors
- Type checking errors

**To test manually:**
```bash
bash scripts/lint.sh --staged
```

**To bypass (NOT RECOMMENDED):**
```bash
git commit --no-verify  # Only if absolutely necessary
```

---

## CI/CD

**Tests run in GitHub Actions:**
- All tests must pass before merge
- Coverage threshold enforced (98%)
- Linting errors block commits
- Type checking errors block commits

**Local testing before pushing:**
```bash
# Run full test suite
uv run pytest

# Run with coverage
uv run pytest --cov=comic_identity_engine

# Run linting
bash scripts/lint.sh
```

---

## Questions?

This project prioritizes correct identity over convenience. When in doubt, be explicit and deterministic.

**Documentation Files:**
- `README.md` - Project overview
- `CONTRIBUTING.md` - Development workflow
- `FIX_PLAN.md` - Active bug tracking and fixes
- `SERIES_PAGE_STRATEGY.md` - Bulk import strategy (CRITICAL for CSV imports)
- `CROSS_PLATFORM_SEARCH.md` - Individual issue search
- `AGENTS.md` - This file
