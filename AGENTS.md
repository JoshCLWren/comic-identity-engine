# AGENTS.md - Agent Guidelines for Comic Identity Engine

## ⚠️ MANDATORY: Fix Broken Code

**ALL AI AGENTS MUST READ THIS:**

When you encounter broken code, tests, or functionality in this codebase, **you are REQUIRED to fix it**. Do NOT ignore broken code. Do NOT work around it. Do NOT leave it for "later".

**If you find it, you fix it.**

This includes but is not limited to:
- Failing tests
- Syntax errors
- Import errors
- Type errors
- Logic bugs
- LSP warnings that indicate real problems
- Inconsistent behavior

**No exceptions. No excuses.**

---

## Project Overview

Comic Identity Engine is a domain-specific entity resolution system for comic books. Currently in initial design phase.

## Build & Test Commands

### Current Status
Test suite functional with pytest.

### Environment Setup

This project uses **uv** for dependency management and **direnv** for automatic environment loading.

```bash
# Initial setup (one-time)
uv sync

# After cd-ing into the project, direnv automatically loads .envrc
# If direnv is not installed, manually activate:
source .venv/bin/activate
```

### Local Development (Recommended)

Use local `uv` processes for normal development, scraper debugging, and dogfooding. Browser-backed scrapers can behave differently in Docker because anti-bot systems fingerprint the containerized browser differently.

```bash
# Start only infrastructure in Docker
docker compose up -d postgres-app redis

# Run the app locally
uv run cie-api
uv run cie-worker

# Exercise the CLI
uv run cie-find "https://www.comics.org/issue/125295/" --verbose --force
```

### Docker-Based CI / Full Stack

The project includes a Docker-based CI environment that works identically locally and in GitHub Actions.

```bash
# Build and run all tests locally using Docker
docker compose build ci
docker compose run --rm ci

# Run individual commands in Docker
docker compose run --rm ci bash scripts/test.sh
docker compose run --rm ci bash scripts/lint.sh
```

### Running Python and Tests

**IMPORTANT**: Always use `uv run` to execute Python and pytest. This ensures dependencies are properly managed.

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_parsing.py -v

# Run with coverage
uv run pytest --cov=comic_identity_engine

# Run a Python script
uv run python script.py

# Start a Python REPL with project dependencies available
uv run python
```

**For AI Agents:**
- Use `uv run pytest` instead of `python -m pytest`
- Use `uv run python` instead of `python`
- The virtual environment is automatically managed by uv
- Do not manually activate `.venv/bin/activate` - direnv handles this

### When Added
Future commands to configure:
- `make test` / `pytest` - Run all tests
- `make lint` / `ruff check .` - Linting
- `make typecheck` / `mypy src/` - Type checking
- `make format` / `black src/ tests/` - Format code

## Code Style Guidelines

### Language
Primary language: **Python 3.13+** with type hints throughout.

### General Principles

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
   - Log errors at appropriate levels

4. **Documentation**
   - Docstrings for all public functions and classes
   - Follow Google style or NumPy style consistently
   - Include type information in docstrings if not using type hints

5. **Testing**
   - Unit tests for all business logic
   - Integration tests for external platform adapters
   - Tests must be deterministic (no randomness without seeded RNG)
   - Use descriptive test names: `test_xmen_negative_one_matches_canonical_issue()`

### Domain-Specific Conventions

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

## Project Structure

```
comic-identity-engine/
├── comic_identity_engine/  # Main source code
├── tests/                  # Test files
├── examples/               # Usage examples
├── docs/                   # Documentation
└── AGENTS.md              # This file
```

## Development Workflow

1. Design before coding - this is identity infrastructure
2. Tests must pass before commit
3. Update documentation for public API changes
4. Current milestone: Source adapter implementation (GCD complete, other platforms pending)

## External Platform Adapters

When adding new platform support:

1. Create adapter in `src/adapters/{platform}/`
2. Implement mapping to canonical model
3. Add reconciliation scoring rules
4. Include test cases with real data samples
5. Document edge cases and limitations

## Matching Strategy Implementation

1. **Candidate Generation**
   - Trigram similarity for series names
   - Tokenized search
   - Numeric filters on issue number/year

2. **Scoring** (deterministic)
   - Exact issue number match required
   - Series alias similarity
   - Publisher match boosting
   - Year proximity boosting

3. **Confidence Output**
   - Three confidence levels
   - Human-readable explanation
   - Audit trail for debugging

## Questions?

This project prioritizes correct identity over convenience. When in doubt, be explicit and deterministic.
