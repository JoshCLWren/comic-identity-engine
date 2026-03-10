# comic-search-lib
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


A simplified comic book search library extracted from comic-web-scrapers.

## Features

- **Atomic Avenue** - Search and find comic series/issues
- **HipComic** - Search marketplace listings
- **Comic Collector Live** - Search with browser automation (Playwright)
- **Unified Client** - Search all platforms concurrently

## Installation

```bash
pip install comic-search-lib
```

## Quick Start

```python
import asyncio
from comic_search_lib import ComicSearchClient
from comic_search_lib.models.comic import Comic

async def search_comics():
    async with ComicSearchClient() as client:
        comic = Comic(
            id="search-1",
            title="Amazing Spider-Man",
            issue="300",
            year=1988,
            publisher="Marvel"
        )
        
        # Search all platforms
        results = await client.search_all(comic)
        
        # Access results by platform
        aa_result = results["atomic_avenue"]
        hip_result = results["hip"]
        ccl_result = results["ccl"]
        
        # Get listings
        for listing in hip_result.listings:
            print(f"{listing.store}: {listing.price} - {listing.url}")

asyncio.run(search_comics())
```

## API Reference

### ComicSearchClient

```python
client = ComicSearchClient(timeout=30)

# Search all platforms
results = await client.search_all(comic)

# Search individual platforms
aa_result = await client.search_atomic_avenue(comic)
hip_result = await client.search_hip(comic)
ccl_result = await client.search_ccl(comic)

# Get summary
summary = client.get_summary(results)
```

### Comic Model

```python
from comic_search_lib.models.comic import Comic

comic = Comic(
    id="unique-id",              # Required
    title="Amazing Spider-Man",   # Required
    issue="300",                 # Required
    year=1988,                   # Optional
    publisher="Marvel",          # Optional
    series_start_year=1963,      # Optional
    series_end_year=2024         # Optional
)
```

### SearchResult

```python
result = SearchResult(
    comic=comic,
    listings=[...],    # List of ComicListing
    prices=[...],      # List of ComicPrice
    metadata={...},    # Search metadata
    url="...",         # Direct URL (for AA)
    source_issue_id="..."  # Extracted ID
)

# Check if results exist
if result.has_results:
    for listing in result.listings:
        print(f"{listing.store}: {listing.price}")
```

## Platform-Specific Notes

### Atomic Avenue
- Returns series URL (not individual listings)
- Uses httpx for HTTP requests
- Fast (~1 second)

### HipComic
- Returns individual marketplace listings
- Uses httpx for HTTP requests
- Moderate speed (~2-3 seconds)
- Filters by year and issue number

### Comic Collector Live
- Returns individual listings with grades
- Uses Playwright for browser automation
- Slower (~8-10 seconds) but handles JavaScript-heavy site
- Requires Playwright browser installation

## Dependencies

- httpx - HTTP client
- selectolax - HTML parsing
- playwright - Browser automation (CCL only)
- jellyfish - String matching

## Running Tests

```bash
# All tests
pytest

# Scraper tests only
pytest tests/scrapers/

# Client tests only
pytest tests/test_client.py
```

## License

Extracted from comic-web-scrapers project.
