# Contributing to Comic Identity Engine

Thanks for contributing to Comic Identity Engine. This project values correct entity resolution, comprehensive testing, and clean architecture. Please follow the guidelines below for any code change.

## Pre-commit hook

A pre-commit hook is installed in `.git/hooks/pre-commit` that automatically runs:
- Check for type/linter ignores in staged files
- Run the shared lint script (`scripts/lint.sh`)

The lint script runs:
- Python compilation check
- Ruff linting
- Any type usage check (ruff ANN401 rule)
- Type checking with ty

The hook will block commits containing `# type: ignore`, `# noqa`, `# ruff: ignore`, or `# pylint: ignore`.

To test the hook manually: `bash scripts/lint.sh --staged`

## 🚫 CORE PRINCIPLE: NEVER SKIP TESTS

**⚠️ THIS IS THE MOST IMPORTANT RULE IN THIS PROJECT.**

**TESTS MUST NEVER BE SKIPPED - EVER.**

When a test fails:
1. ✅ Fix the test
2. ✅ Fix the code that breaks the test
3. ✅ Investigate root cause
4. ❌ **NEVER skip the test**

**This applies to:**
- All automated tests (unit, integration)
- All contributors (human and AI)
- All situations (no exceptions)

**Consequences of skipping tests:**
- Broken code gets merged
- Technical debt accumulates
- Confidence in the test suite is lost
- Other developers waste time debugging

**If you're tempted to use `--no-verify`, skip a test, or disable a check, DON'T.**

Fix the problem instead.

---

## Development workflow

### Getting Started

1. Install dependencies:
   ```bash
   uv sync
   source .venv/bin/activate  # Or let direnv auto-load .envrc
   ```

2. Start infrastructure:
   ```bash
   docker compose up -d postgres-app redis
   ```

3. Run the development server:
   ```bash
   uv run cie-api  # API server
   uv run cie-worker  # Background worker
   ```

4. View the app:
   - App: http://localhost:8000
   - API docs: http://localhost:8000/docs

### API Development

- REST endpoints are defined in `comic_identity_engine/api/`
- Request/response schemas in `comic_identity_engine/api/schemas/` using Pydantic
- Database models in `comic_identity_engine/database/models/` using SQLAlchemy
- Test endpoints with httpx.AsyncClient
- Use FastAPI's automatic OpenAPI docs at `/docs`

### Platform Adapters

- Platform adapters live in `comic_identity_engine/adapters/`
- All inherit from `SourceAdapter` in `longbox-scrapers`
- See `SERIES_PAGE_STRATEGY.md` for bulk import patterns
- See `CROSS_PLATFORM_SEARCH.md` for individual lookup patterns

### Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Run migrations
alembic upgrade head
```

---

## Code quality standards

- Run linting after each change:
  - `bash scripts/lint.sh` (all files)
  - `bash scripts/lint.sh --staged` (staged files only)
- Use specific types instead of `Any` in type annotations (ruff ANN401 rule)
- Run tests when you touch logic or input handling:
  - `uv run pytest`
  - `uv run pytest tests/test_adapters/test_gcd.py -v`
- Always write a regression test when fixing a bug
- If you break something while fixing it, fix both in the same PR
- Do not use in-line comments to disable linting or type checks
- Do not narrate your code with comments; prefer clear code and commit messages

---

## Testing guidelines

- Automated tests live in `tests/` and run with `pytest`
- Use descriptive test names: `test_xmen_issue_1_matches_canonical_record()`
- Test both success and error paths for all operations
- Test business logic (identity resolution, reconciliation) independently
- Maintain 98% coverage threshold
- Use proper fixtures with database cleanup
- Never skip a failing test

### Test Organization

```
tests/
├── conftest.py              # Shared fixtures
├── test_adapters/           # Platform adapter tests
├── test_api/                # API endpoint tests
├── test_cli/                # CLI command tests
├── test_integration/        # Integration tests
├── test_jobs/               # Background job tests
└── test_services/           # Service layer tests
```

---

## Style guidelines

- Keep helpers explicit and descriptive (snake_case)
- Annotate public functions with precise types
- Use Pydantic schemas for API validation
- Use SQLAlchemy models for database operations
- Follow PEP 8 spacing (4 spaces, 100-character soft wrap)
- Use structlog for logging (not stdlib logging)

---

## Architecture principles

### Canonical First
- Internal identity (Issue UUID) is authoritative
- External systems are adapters
- Store external IDs, never infer repeatedly

### Deterministic Before ML
- Clear parsing rules before ML
- Every match produces confidence score + explanation
- Test with deterministic data

### Explainable Matching
- issue_confidence, variant_confidence, overall_confidence
- Explanation field for all matches
- Audit trail for debugging

---

## Branch workflow

- Create a feature branch from `main` before making changes:
  - `git checkout main && git checkout -b fix/resolve-identity-task-mocks`
- Use descriptive branch names
- Ensure all tests pass before pushing
- Include test coverage in PR description

---

## Pull request guidelines

- Use imperative, component-scoped commit messages (e.g., "Fix resolve_identity_task mock structure")
- Bundle related changes per commit
- PR summary should describe:
  - What changed and why
  - Testing performed
  - Any breaking changes
- Ensure all tests pass and coverage is maintained
- Run linting before pushing: `bash scripts/lint.sh`

---

## Questions?

- See `AGENTS.md` for detailed agent guidelines
- See `FIX_PLAN.md` for active bug tracking
- See `SERIES_PAGE_STRATEGY.md` for bulk import patterns
- See `CROSS_PLATFORM_SEARCH.md` for search patterns

This project prioritizes correct identity over convenience. When in doubt, be explicit and deterministic.
