# CRITICAL BUGS - Cross-Platform Mapping Failures

**Status**: UNFIXED - These bugs are currently breaking cross-platform URL discovery and persistence

---

## Bug 1: Cross-Platform Mappings Not Persisted to Database

**Severity**: CRITICAL - Cross-platform URLs are found but lost after request completes

**Location**: `comic_identity_engine/jobs/tasks.py:124-152`

**Problem**: 
The `_handle_existing_mapping()` function creates external mappings via `_ensure_source_mapping()` but **never commits the transaction**. The mappings exist only in the uncommitted transaction and are lost when the request ends.

**Code**:
```python
# Lines 124-152 in tasks.py
for platform, found_url in cross_platform_urls.items():
    if found_url and platform != parsed_url.platform:
        try:
            parsed_found = parse_url(found_url)
            await _ensure_source_mapping(
                mapping_repo=mapping_repo,
                issue_id=existing.issue_id,
                source=platform,
                source_issue_id=parsed_found.source_issue_id,
                source_series_id=parsed_found.source_series_id,
            )
            logger.info("Created external mapping for found platform", ...)
        except Exception as e:
            logger.warning("Failed to create external mapping for platform", ...)
# MISSING: await session.commit() <-- THIS IS THE BUG!
```

**Fix Required**: 
Add `await session.commit()` after line 152, after the external mappings loop completes.

**Expected Behavior**: 
Cross-platform URLs discovered during search should be saved to the `external_mappings` table and persist across requests.

**Actual Behavior**: 
Mappings are created in-memory but rolled back when the transaction ends without a commit.

---

## Bug 2: Duplicate Code Block in LoCG URL Parser

**Severity**: HIGH - Code smell, potential for divergence bugs

**Location**: `comic_identity_engine/services/url_parser.py:217-243`

**Problem**:
The variant query parameter handling code is duplicated verbatim. Lines 217-228 and 232-243 are identical blocks. If one is fixed and the other isn't, bugs will occur.

**Code**:
```python
# Lines 217-228 - FIRST BLOCK
variant_match = re.search(r"variant=(\d+)", url)
if variant_match:
    variant_id = variant_match.group(1)
    series_match = re.search(r"/comic/(\d+)", url)
    if series_match:
        series_id = series_match.group(1)
        return ParsedUrl(
            platform="locg",
            source_issue_id=variant_id,
            source_series_id=series_id,
        )

# Lines 230-243 - DUPLICATE BLOCK (should be deleted)
# Check for variant query parameter (variant IDs)
# These URLs include ?variant=VARIANT_ID in the query string
variant_match = re.search(r"variant=(\d+)", url)  # <-- DUPLICATE!
if variant_match:
    variant_id = variant_match.group(1)
    # For variant URLs, extract series ID from path
    series_match = re.search(r"/comic/(\d+)", url)
    if series_match:
        series_id = series_match.group(1)
        return ParsedUrl(
            platform="locg",
            source_issue_id=variant_id,
            source_series_id=series_id,
        )
```

**Fix Required**: 
Delete lines 230-243 (the duplicate block). Keep only lines 217-228.

---

## Bug 3: Unsafe Dictionary Access - Potential Crashes

**Severity**: HIGH - Causes KeyError crashes when scraper returns unexpected data

**Location**: `comic_identity_engine/services/platform_searcher.py:296, 300`

**Problem**:
After safely checking `if result.get("url"):`, the code unsafely accesses `result["url"]` which will crash if:
- `result` is None
- `result` is not a dict
- The "url" key is deleted between the check and access (unlikely but possible)

**Code**:
```python
# Lines 295-302 in platform_searcher.py
else:
    if result.get("url"):  # <-- SAFE CHECK
        found_urls[platform] = result["url"]  # <-- LINE 296: UNSAFE ACCESS!
        logger.info(
            "DEBUG: Added URL to found_urls",
            platform=platform,
            url=result["url"],  # <-- LINE 300: UNSAFE ACCESS!
            total_found=len(found_urls),
        )
```

**Fix Required**:
Change lines 296 and 300 to use safe access:
```python
found_urls[platform] = result.get("url")  # Safe
url=result.get("url")  # Safe
```

Or extract to a variable:
```python
url = result.get("url")
if url:
    found_urls[platform] = url
    logger.info(..., url=url, ...)
```

---

## Bug 4: LoCG URL Parser Extracts Wrong Issue ID

**Severity**: CRITICAL - Parses series ID as issue ID for double-ID URLs

**Location**: `comic_identity_engine/services/url_parser.py:273`

**Problem**:
The single-ID pattern `r"/comic/(\d+)"` matches the FIRST number in URLs with two IDs. For URLs like `/comic/111275/1169529`, it returns `111275` (series ID) instead of `1169529` (issue ID).

**Evidence**:
```python
# URL: https://leagueofcomicgeeks.com/comic/111275/1169529
# Expected: source_issue_id = "1169529"
# Actual: source_issue_id = "111275" (WRONG - this is the series ID!)
```

**Code**:
```python
# Lines 260-268: CORRECT double-ID pattern
double_id_match = re.search(r"/comic/(\d+)/(\d+)(?:/|$)", url)
if double_id_match:
    series_id = double_id_match.group(1)  # 111275
    issue_id = double_id_match.group(2)   # 1169529
    return ParsedUrl(
        platform="locg",
        source_issue_id=issue_id,
        source_series_id=series_id,
    )

# Lines 273-279: BROKEN single-ID pattern
issue_match = re.search(r"/comic/(\d+)", url)  # Matches FIRST number!
if issue_match:
    issue_id = issue_match.group(1)  # For /comic/111275/1169529, returns 111275 (WRONG!)
    return ParsedUrl(
        platform="locg",
        source_issue_id=issue_id,
    )
```

**Fix Required**:
The single-ID pattern should only match URLs with ONE ID (like `/comic/9092122/x-force-47`), not URLs with two IDs. 

The double-ID pattern at line 260 already handles `/comic/111275/1169529` correctly, but the code continues to the single-ID pattern which matches AGAIN and returns the wrong ID.

**Solution**: The single-ID pattern should be more specific to avoid matching double-ID URLs:
```python
# Match ONLY single-ID URLs (issue ID only, no second ID)
issue_match = re.search(r"^/comic/(\d+)(?:/[^/]+)?$", url_path)
```

Or add a guard clause to return early after the double-ID match (line 268 already returns, so this should work... unless the regex at line 273 is matching when it shouldn't).

**Root Cause**: The regex `r"/comic/(\d+)"` will match `/comic/111275/` from the URL `/comic/111275/1169529`, extracting the series ID instead of the issue ID.

---

## Bug 5: GCD Scraper Returns Login Page (Cloudflare 403)

**Severity**: HIGH - GCD scraping completely broken

**Location**: `comic-search-lib/comic_search_lib/scrapers/gcd.py:141-142`

**Problem**:
GCD (Grand Comics Database) returns a login page instead of search results due to Cloudflare protection. The scraper detects this (line 141) but continues trying to parse HTML instead of switching to GCD's JSON API.

**Code**:
```python
# Lines 141-142 in gcd.py
elif "login" in html.lower() or "sign in" in html.lower():
    print(f"   ⚠️  GCD returned login page")
# BUG: Code continues parsing HTML instead of using JSON API!
```

**Evidence**:
- GCD has a JSON API at `https://www.comics.org/api/`
- Current scraper uses HTML scraping which is blocked by Cloudflare
- 403 Forbidden errors occur due to anti-bot protection

**Fix Required**:
Rewrite GCD scraper to use their JSON API instead of HTML scraping:

1. Use GCD's API endpoints:
   - Series search: `/api/series/`
   - Issue lookup: `/api/issue/{id}/`
   
2. Remove HTML parsing code that fails on Cloudflare

3. Add proper API authentication/headers if required

---

## Summary

All 5 bugs prevent cross-platform URL mappings from working correctly:

1. **Bug 1** (CRITICAL): Mappings found but not saved - no `commit()` after creating mappings
2. **Bug 2** (HIGH): Duplicate code creates maintenance burden
3. **Bug 3** (HIGH): Crashes when scraper returns unexpected data structure
4. **Bug 4** (CRITICAL): Wrong IDs extracted from LoCG URLs, creating bad mappings
5. **Bug 5** (HIGH): GCD scraper broken by Cloudflare, needs JSON API rewrite

**Priority Order for Fixing**:
1. Bug 1 - Blocks all cross-platform mapping persistence
2. Bug 4 - Creates incorrect mappings that pollute the database
3. Bug 3 - Causes crashes during search
4. Bug 5 - Breaks GCD integration entirely
5. Bug 2 - Code quality issue, lower priority

---

## Testing Checklist

After fixing these bugs, verify:

- [ ] Cross-platform search creates mappings that persist after request completes
- [ ] Database queries show new `external_mappings` rows with correct `source_issue_id`
- [ ] LoCG URLs with two IDs (`/comic/SERIES_ID/ISSUE_ID`) extract correct issue ID
- [ ] LoCG variant URLs (`?variant=ID`) extract correct variant ID
- [ ] No KeyError crashes when scrapers return None or non-dict results
- [ ] GCD scraper uses JSON API and returns valid results
- [ ] Integration tests pass with real platform data

---

## Files Requiring Changes

1. `comic_identity_engine/jobs/tasks.py` - Add `commit()` after line 152
2. `comic_identity_engine/services/url_parser.py` - Fix LoCG parser (lines 217-243, 273)
3. `comic_identity_engine/services/platform_searcher.py` - Fix unsafe dict access (lines 296, 300)
4. `comic-search-lib/comic_search_lib/scrapers/gcd.py` - Rewrite to use JSON API
