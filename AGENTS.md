# AGENTS.md - Agent Guidelines for Comic Identity Engine

## Project Overview

Comic Identity Engine is a domain-specific entity resolution system for comic books. Currently in initial design phase.

## Build & Test Commands

### Current Status
No build system configured yet. Project is in design phase.

### When Added
Typical commands to expect:

```bash
# Run all tests
make test
pytest

# Run single test
pytest tests/test_file.py::test_function_name -v

# Linting
make lint
ruff check .

# Type checking
make typecheck
mypy src/

# Format code
make format
black src/ tests/

# Run all checks
make check
```

## Code Style Guidelines

### Language
Primary language not yet determined. Likely Python (data processing) or Rust (performance).

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
├── src/                    # Main source code
├── tests/                  # Test files
├── examples/               # Usage examples
├── docs/                   # Documentation
└── AGENTS.md              # This file
```

## Development Workflow

1. Design before coding - this is identity infrastructure
2. Tests must pass before commit
3. Update documentation for public API changes
4. First milestone: X-Men #-1 reconciliation test

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
