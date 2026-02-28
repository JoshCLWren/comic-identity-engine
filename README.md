# Comic Identity Engine

Domain-specific entity resolution system for comic books.

## Current Status

**Phase**: Initial Implementation

### Completed Components

1. **Issue Number Parsing** ✅
   - Location: `comic_identity_engine/parsing.py`
   - Function: `parse_issue_candidate(raw: str) -> ParseResult`
   - Test coverage: 32 tests, all passing
   - Supports: negative numbers, decimals, fractions, variants, leading zeros
   - Error handling: EMPTY_INPUT, ONLY_SEPARATOR, INVALID_FORMAT, MULTI_ISSUE_RANGE

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

## Project Structure

```
comic-identity-engine/
├── comic_identity_engine/
│   ├── __init__.py
│   └── parsing.py          # Issue number parsing logic
├── tests/
│   ├── __init__.py
│   └── test_parsing.py     # Parsing test suite (32 tests)
├── examples/
│   ├── edge-cases/         # Edge case research and test cases
│   ├── gcd/                # Grand Comics Database data
│   ├── locg/               # League of Comic Geeks data
│   ├── ccl/                # Comic Collector Live data
│   ├── aa/                 # Atomic Avenue data
│   ├── cpg/                # Comics Price Guide data
│   ├── hipcomic/           # HIP Comic data
│   ├── clz/                # CLZ data
│   └── COMPARISON.md       # Cross-platform analysis
├── AGENTS.md               # This file
└── README.md               # Project overview
```

## Usage

### Parse Issue Numbers

```python
from comic_identity_engine.parsing import parse_issue_candidate

# Parse a candidate issue number
result = parse_issue_candidate("-1A")

if result.success:
    print(f"Canonical: {result.canonical_issue_number}")  # "-1"
    print(f"Variant: {result.variant_suffix}")            # "A"
else:
    print(f"Error: {result.error_code} - {result.error_message}")
```

### Run Tests

```bash
python3 -c "
import sys
sys.path.insert(0, '.')
from comic_identity_engine.parsing import parse_issue_candidate

# Quick validation
assert parse_issue_candidate('-1').canonical_issue_number == '-1'
assert parse_issue_candidate('0.5').canonical_issue_number == '0.5'
assert parse_issue_candidate('1000.DE').variant_suffix == 'DE'
print('All checks passed!')
"
```

## Development Guidelines

See `AGENTS.md` for detailed:
- Code style guidelines
- Testing requirements
- Architecture patterns
- Platform adapter guidelines

## License

[To be determined]
