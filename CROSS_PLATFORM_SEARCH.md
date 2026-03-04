# Cross-Platform Search Implementation

## Summary

Successfully integrated cross-platform search functionality into the Comic Identity Engine. When a user provides **ONE URL** from any platform, the system now **automatically searches for the same comic on other platforms** and returns URLs for ALL platforms where found.

## What Was Implemented

### 1. Dependencies Added (`pyproject.toml`)
- Added `comic-web-scrapers` as a local dependency
- Enabled direct references for local package development
- Added required packages: `beautifulsoup4`, `aiohttp` (via scrapers)

### 2. Core Search Method (`IdentityResolver`)

**New Method: `search_cross_platform()`** (lines 527-591 in `identity_resolver.py`)

```python
async def search_cross_platform(
    self,
    issue_id: uuid.UUID,
    series_title: str,
    issue_number: str,
    year: Optional[int] = None,
    publisher: Optional[str] = None,
    skip_platform: Optional[str] = None,
) -> Dict[str, str]
```

**Features:**
- Searches AA, CCL, and HIP platforms (skips source platform)
- Creates external mappings for found comics
- Returns dictionary of platform URLs
- Gracefully handles search failures per platform

### 3. Platform-Specific Search (`_search_single_platform()`)

**Helper Method** (lines 593-652 in `identity_resolver.py`)

**Flow:**
1. Gets scraper instance for platform
2. Initializes scraper
3. Creates search dict with: title, issue, year, publisher
4. Calls `scraper.search_comic(comic_dict)`
5. Selects best listing from results
6. Extracts `source_issue_id` and `source_series_id` from URL
7. Creates external mapping in database
8. Returns platform URL

### 4. URL ID Extraction (`_extract_ids_from_url()`)

**Regex-based ID extraction** (lines 688-732 in `identity_resolver.py`)

**Platform URL Patterns:**
- **Atomic Avenue**: `/item/{source_issue_id}/1/details`
- **CCL**: `/issue/{source_series_id}/{source_issue_id}`
- **HIP**: `/comic/{source_series_id}/{source_issue_id}/`

### 5. Task Integration (`tasks.py`)

**Modified `resolve_identity_task()`** to call cross-platform search:

**After line 209** (new mapping created):
```python
# Cross-platform search: find this issue on other platforms
cross_platform_urls = await resolver.search_cross_platform(
    issue_id=result.issue_id,
    series_title=candidate.series_title,
    issue_number=candidate.issue_number,
    year=candidate.cover_date.year if candidate.cover_date else None,
    publisher=None,
    skip_platform=parsed_url.platform,
)
```

**For existing mappings** (around line 150):
- Also performs cross-platform search
- Uses series title and issue number from database
- Ensures even previously resolved issues get cross-platform updates

## How It Works

### Example Flow: User provides CCL URL

```
1. User submits: https://www.comiccollectorlive.com/issue/xxx/123

2. System parses URL → platform="ccl", source_issue_id="123"

3. Fetches issue from CCL → gets metadata:
   - series_title: "X-Men"
   - issue_number: "1"
   - cover_date: 1963-09-01
   - publisher: "Marvel"

4. Resolves to canonical issue_id (existing or new)

5. Creates external mapping for CCL

6. 🔥 NEW: Cross-platform search:
   - Search AA with: {title: "X-Men", issue: "1", year: 1963}
   - Search HIP with: {title: "X-Men", issue: "1", year: 1963}
   - Skip CCL (source platform)

7. For each found platform:
   - Extract source_issue_id from listing URL
   - Create external mapping
   - Add to results dict

8. Build URLs for ALL platforms (from database)

9. Return complete dict:
   {
     "ccl": "https://www.comiccollectorlive.com/issue/xxx/123",
     "aa": "https://atomicavenue.com/atomic/item/456/1/details",
     "hip": "https://www.hipcomic.com/price-guide/us/marvel/comic/789/012/",
     "gcd": "",  # Not found yet
     "locg": "",  # Not searched (no scraper)
     "cpg": ""   # Not searched (no scraper)
   }
```

## Scraper Integration

All three scrapers share the **same interface**:

```python
result = await scraper.search_comic({
    "title": "X-Men",
    "issue": "1",
    "year": 1963,
    "publisher": "Marvel",
})
```

**Returns `SearchResult` with:**
- `listings`: List of found listings
- Each listing has `url` to the comic
- URLs are parsed to extract `source_issue_id`

## Search Method Details

### Atomic Avenue Scraper
- **Search URL**: `/atomic/SearchIssues.aspx?XT=1&M=1&T={title}&I={issue}`
- **Listing extraction**: Parses search results and issue pages
- **Year filtering**: Uses year to select best series match

### CCL HTTP Scraper
- **Search**: Two-phase (title search → series navigation)
- **Authentication**: Requires cookies (empty dict for search)
- **Series matching**: Selects series by year match

### HIP Scraper
- **Search URL**: `/category/comic-books/100/?keywords={title} {issue} {year}`
- **Pagination**: Handles multiple pages
- **Validation**: Filters by year and issue number

## GCD Integration

**Status**: API available but not yet integrated

**GCD API** (https://www.comics.org/api/):
- `/api/series/` - Series list with name, year_began, year_ended
- `/api/issue/{id}/` - Issue details
- Can search by series name, then find issue by number

**Future Enhancement**: Add GCD search to cross-platform search

## Testing

Created `tests/test_cross_platform_search.py` with:

1. **`test_cross_platform_search_with_mock_scrapers()`**
   - Tests full flow with mocked scrapers
   - Verifies external mapping creation
   - Validates URL extraction

2. **`test_extract_ids_from_url()`**
   - Tests URL parsing for AA, CCL, HIP
   - Validates regex extraction
   - Tests invalid URLs

3. **`test_select_best_listing()`**
   - Tests listing selection logic
   - Handles empty results
   - Tests URL prioritization

## Error Handling

**Graceful degradation:**
- If scraper fails to import → log warning, continue
- If search fails → log warning, try next platform
- If ID extraction fails → log warning, don't create mapping
- If create_mapping fails → log error, continue

**No exceptions propagated** from cross-platform search:
- Original resolution continues even if search fails
- Results include whatever platforms were found
- Errors logged with appropriate level

## Configuration

**Local Development:**
```toml
"comic-web-scrapers @ file:///mnt/extra/josh/code/comic-web-scrapers"
```

**Production:**
```toml
"comic-web-scrapers @ git+https://github.com/anomalyco/comic-web-scrapers.git"
```

## Success Criteria ✓

✅ **User gives ONE URL** (e.g., CCL)
✅ **System searches other platforms** (AA, HIP)
✅ **Returns URLs for ALL platforms** where found
✅ **Creates external mappings** for future lookups
✅ **Not just "found existing mapping"** but actually searches

## Next Steps

1. **Add GCD search**: Use GCD API for series/issue lookup
2. **Add LoCG/CPG scrapers**: Implement search methods
3. **Performance optimization**: Parallel platform searches
4. **Confidence scoring**: Rank results by match quality
5. **Caching**: Cache search results to avoid duplicate searches
