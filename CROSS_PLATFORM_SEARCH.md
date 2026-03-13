# ⚠️ CROSS-PLATFORM SEARCH - READ THIS BEFORE MODIFYING ⚠️
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


## 🚨 CRITICAL: DO NOT SKIP THIS DOCUMENT 🚨

**IF YOU ARE MODIFYING CROSS-PLATFORM SEARCH CODE, YOU MUST READ THIS ENTIRE DOCUMENT.**

**EVERY. SINGLE. WORD.**

---

## 🎯 PRIMARY STRATEGY: SERIES PAGE BULK EXTRACTION

### THE CORRECT APPROACH (DO THIS INSTEAD)

**For CSV imports and bulk operations:**

```python
# ✅ CORRECT: Find ONE issue → Get SERIES page → Extract ALL issues
for each_row in csv_import:
    issue_data = parse_row(row)

# Step 1: Search for ONE issue from the series on each platform
found_urls = await search_all_platforms(series_title, issue_number, ...)

# Step 2: For each platform where we found ONE issue, navigate to SERIES page
for platform, url in found_urls.items():
    series_page_url = extract_series_page_url(url)
    all_issue_urls = scrape_all_issues_from_series_page(series_page_url)

    # Step 3: Create mappings for ALL issues in the series
    for issue_url in all_issue_urls:
        parsed = parse_url(issue_url)
        await create_mapping(
            issue_id=canonical_issue_id,
            source=platform,
            source_issue_id=parsed.source_issue_id,
            source_url=issue_url,  # ← STORE FULL URL!
        )
```

**WHY THIS WORKS:**
1. **One search per series per platform** (not one search per issue!)
2. **Get all issues at once** from the series page
3. **Store full URLs** (not just IDs)
4. **10-100x faster** than searching each issue individually
5. **Higher success rate** - if you find issue #1, you get issues #2-#150 for free

### Platform Series Page Patterns

**Atomic Avenue (AA):**
- Issue URL: `https://atomicavenue.com/atomic/item/217255/1/x-men-negative-1`
- Series page: `https://atomicavenue.com/atomic/series/16287/1/XMen-2nd-Series`
- Pattern: Extract series ID from issue URL, construct series URL
- Result: ALL issue URLs for that series on one page

**Comics Price Guide (CPG):**
- Issue URL: `https://www.comicspriceguide.com/titles/x-men/-1/phvpiu`
- Series page: `https://www.comicspriceguide.com/titles/x-men/rluy`
- Pattern: Extract series slug from issue URL, construct series URL
- Result: ALL issue URLs for that series on one page

**Comic Collector Live (CCL):**
- Issue URL: `https://www.comiccollectorlive.com/issue/comic-books/X-Men-1991/78/dbea05f8-fde4-409d-abbe-0cdace6f8ac9`
- Series page: Extract from issue URL or navigate via series links
- Pattern: Series slug in URL path
- Result: ALL issue URLs for that series

**League of Comic Geeks (LoCG):**
- Issue URL: `https://leagueofcomicgeeks.com/comic/8917101/x-force-11`
- Series page: Navigate via series links or scrape issue listings
- Pattern: Issue pages link back to series
- Result: ALL issue URLs for that series

**Grand Comics Database (GCD):**
- Issue URL: `https://www.comics.org/issue/125295/`
- Series page: `https://www.comics.org/series/4254/`
- Pattern: Series ID in issue data, construct series URL
- Result: ALL issue URLs for that series (GCD has the best series pages!)

### When to Use Individual Issue Search

**ONLY use individual search for:**
1. Single issue lookups via CLI (`cie-find`)
2. Edge cases where series page doesn't exist or is malformed
3. Issues that can't be found via series page (specials, one-shots)
4. Testing and debugging

**DO NOT use individual search for:**
1. CSV imports (use series page extraction!)
2. Bulk operations (use series page extraction!)
3. Any operation with >5 issues from the same series

---

## THE PROBLEM (WHY WE'RE HERE)

### What Users Expect
```
User runs: cie-find "https://www.comics.org/issue/12345/"
Expected: Find THIS issue on ALL platforms, show real-time progress
User runs: cie-import-clz backup.clz
Expected: Import 1000 issues efficiently by leveraging series pages
Actual (WRONG APPROACH): Search for each of 1000 issues individually
```

### Why Individual Issue Search Fails

**WRONG APPROACH (DO NOT DO THIS):**
```python
# ❌ BAD: Search for each issue individually
for each_issue in csv_import:
    for platform in platforms:
        result = search_comic(title, issue, year, publisher)
        if result.found:
            create_mapping(platform, result)
        else:
            status = "not_found"
```

**WHY THIS FAILS:**
1. **1000 issues × 6 platforms = 6000 searches** (insanely slow!)
2. **Network errors** on each search (timeouts, rate limits)
3. **Platform search limitations** (many platforms have terrible search)
4. **False negatives** (issue exists but search doesn't find it)
5. **Inefficient** - if you find X-Men #1, you should get #2-#150 for free

---

## THE SOLUTION (WHAT YOU MUST IMPLEMENT)

### Core Requirements (NON-NEGOTIABLE)

1. ✅ **Search ALL platforms** - gcd, locg, aa, ccl, cpg, hip (NO skipping!)
2. ✅ **Multiple strategies per platform** - exact, no_year, normalized, fuzzy, etc.
3. ✅ **Retry with exponential backoff** - 2-3 retries per strategy
4. ✅ **Real-time status updates** - user sees "searching_retry_1" while working
5. ✅ **Parallel execution** - search all platforms concurrently for speed
6. ✅ **Platform-specific configs** - different retry counts for different platforms
7. ✅ **Max 2 minutes per platform** - timeout if taking too long
8. ✅ **Max 5 minutes total operation** - fail-safe timeout
9. ✅ **Create mappings immediately** - don't wait for all platforms to finish
10. ✅ **Only mark "not_found" after ALL strategies exhausted** - not after first failure

### Search Strategies (REQUIRED - IN ORDER)

For each platform, try these strategies in sequence:

```python
STRATEGIES = [
    "exact",              # Try exact match first
    "no_year",            # Drop year (many platforms better without it)
    "normalized_title",   # Normalize: "X-Men (1991)" → "x-men"
    "fuzzy_title",        # Use jellyfish.jaro_winkler_similarity ≥0.85
    "alt_issue_format",   # Try "1" → "01", "#1" → "1"
    "simplified_tokens",  # Tokenize: "Amazing Spider-Man" → "amazing spiderman"
]
```

**For each strategy:**
- Retry 2-3 times with exponential backoff (1s, 2s, 4s)
- Update operation status after each attempt
- Only move to next strategy if all retries fail
- Only mark "not_found" after all strategies exhausted

---

## PLATFORM-SPECIFIC CONFIGURATIONS

### USE THESE EXACT CONFIGS (DO NOT MODIFY WITHOUT REASON)

```python
PLATFORM_SEARCH_CONFIG = {
    "gcd": {
        "max_retries": 2,
        "max_duration_sec": 60,
        "strategies": ["exact", "no_year", "normalized_title"],
        "retry_delay_sec": 1,
        "notes": "Excellent search, authoritative source"
    },
    "locg": {
        "max_retries": 3,
        "max_duration_sec": 90,
        "strategies": ["exact", "no_year", "normalized_title", "fuzzy_title"],
        "retry_delay_sec": 2,
        "notes": "Good search but rate limited - need backoff"
    },
    "aa": {
        "max_retries": 3,
        "max_duration_sec": 120,
        "strategies": ["exact", "no_year", "normalized_title", "fuzzy_title", "simplified_tokens"],
        "retry_delay_sec": 2,
        "notes": "Finicky HTML parsing, needs multiple strategies"
    },
    "ccl": {
        "max_retries": 3,
        "max_duration_sec": 120,
        "strategies": ["exact", "no_year", "normalized_title", "fuzzy_title", "alt_issue_format"],
        "retry_delay_sec": 2,
        "notes": "Requires session cookies, session issues common"
    },
    "cpg": {
        "max_retries": 2,
        "max_duration_sec": 60,
        "strategies": ["exact", "no_year"],
        "retry_delay_sec": 1,
        "notes": "Poor search functionality, don't waste time"
    },
    "hip": {
        "max_retries": 2,
        "max_duration_sec": 90,
        "strategies": ["exact", "no_year", "normalized_title", "fuzzy_title"],
        "retry_delay_sec": 2,
        "notes": "Occasional timeouts, needs retries"
    },
}
```

---

## REAL-TIME STATUS UPDATES

### Status Values (USE THESE EXACT VALUES)

```python
# While searching
"searching"              # Initial search
"searching_exact"        # Trying exact match
"searching_no_year"      # Trying without year
"searching_normalized"   # Trying normalized title
"searching_fuzzy"        # Trying fuzzy match
"searching_retry_1"      # First retry
"searching_retry_2"      # Second retry
"searching_retry_3"      # Third retry

# Final states
"found"                  # Successfully found
"not_found"              # All strategies exhausted (NOT after first failure!)
"failed"                 # Error after all retries
```

### How to Update Status

```python
# After EACH strategy attempt, update operation metadata
await operations_manager.update_operation(
    operation_id=operation_id,
    status="running",  # Still running!
    result={
        "platform_status": {
            "gcd": "found",
            "locg": "searching_fuzzy",
            "aa": "searching_retry_2",
            "ccl": "searching_normalized",
            "cpg": "not_found",  # Only after exhausting strategies!
            "hip": "searching",
        }
    }
)
```

---

## IMPLEMENTATION PATTERNS (USE THESE)

### Pattern 1: Parallel Search with asyncio.gather()

```python
async def search_all_platforms(self, ...):
    """Search all platforms in parallel."""
    all_platforms = ["gcd", "locg", "aa", "ccl", "cpg", "hip"]

    # Create tasks for all platforms
    tasks = {}
    for platform in all_platforms:
        task = self._search_single_platform_with_strategies(platform, ...)
        tasks[platform] = task

    # Execute in parallel (NOT sequential!)
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    # Process results
    for platform, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            platform_status[platform] = "failed"
        elif result:
            platform_status[platform] = "found"
        else:
            platform_status[platform] = "not_found"
```

### Pattern 2: Single Platform with Strategies

```python
async def _search_single_platform_with_strategies(self, platform, ...):
    """Search one platform with multiple strategies and retries."""
    config = PLATFORM_SEARCH_CONFIG[platform]

    # Try each strategy in order
    for strategy in config["strategies"]:
        # Update status
        await self._update_platform_status(operation_id, platform, f"searching_{strategy}")

        # Retry with exponential backoff
        for attempt in range(config["max_retries"]):
            try:
                result = await self._execute_strategy(scraper, strategy, ...)

                if result and result.has_results:
                    # FOUND! Create mapping immediately
                    url = await self._create_mapping(platform, issue_id, result)
                    return url

                # No results - retry if not last attempt
                if attempt < config["max_retries"] - 1:
                    await self._update_platform_status(operation_id, platform, f"searching_retry_{attempt + 1}")
                    await asyncio.sleep(config["retry_delay_sec"] * (2 ** attempt))

            except NetworkError:
                if attempt < config["max_retries"] - 1:
                    await asyncio.sleep(config["retry_delay_sec"] * (2 ** attempt))
                else:
                    raise

    # All strategies exhausted
    return None
```

### Pattern 3: Strategy Execution

```python
async def _execute_strategy(self, scraper, strategy, title, issue, year, publisher):
    """Execute a single search strategy."""

    if strategy == "exact":
        return await scraper.search_comic(title, issue, year, publisher)

    elif strategy == "no_year":
        return await scraper.search_comic(title, issue, None, publisher)

    elif strategy == "normalized_title":
        normalized = self._normalize_series_name(title)
        return await scraper.search_comic(normalized, issue, year, publisher)

    elif strategy == "fuzzy_title":
        # Use jellyfish.jaro_winkler_similarity with 0.85 threshold
        return await self._fuzzy_search(scraper, title, issue, year, publisher)

    elif strategy == "alt_issue_format":
        # Try "1" → "01", "#1" → "1"
        alt_formats = self._get_alternate_issue_formats(issue)
        for alt_issue in alt_formats:
            result = await scraper.search_comic(title, alt_issue, year, publisher)
            if result and result.has_results:
                return result
        return None

    elif strategy == "simplified_tokens":
        # Use tokenize() from comics_backend/search_utils.py
        tokens = tokenize(title)
        simplified = " ".join(tokens)
        return await scraper.search_comic(simplified, issue, year, publisher)
```

---

## HELPER FUNCTIONS TO REUSE

### From IMPLEMENTATION_PLAN.md (lines 576-594)

```python
def _normalize_series_name(self, name: str) -> str:
    """Normalize series name for fuzzy matching."""
    import re

    name = name.lower().strip()
    name = re.sub(r'\s+', ' ', name)  # Normalize whitespace
    name = re.sub(r'\(.*?\)', '', name)  # Remove parentheticals
    name = re.sub(r'vol\.?\s*\d+', '', name)  # Remove volume numbers
    name = name.strip()

    return name
```

### From comics_backend/app/routers/library/search_utils.py

```python
def tokenize(text: str) -> list[str]:
    """Break a string into lowercase alphanumeric tokens."""
    import re
    _TOKEN_RE = re.compile(r"[0-9a-zA-Z]+")
    return [token for token in _TOKEN_RE.findall(text.lower()) if token]
```

### Jellyfish Fuzzy Matching

```python
import jellyfish

async def _fuzzy_search(self, scraper, title, issue, year, publisher):
    """Fuzzy search using Jaro-Winkler similarity."""

    # Get broad results
    broad_result = await scraper.search_comic(title, None, year, publisher)

    if not broad_result or not broad_result.has_results:
        return None

    # Find best match
    best_match = None
    best_score = 0.0
    normalized_issue = self._normalize_issue(issue)

    for listing in broad_result.listings:
        listing_issue = self._normalize_issue(listing.issue)
        score = jellyfish.jaro_winkler_similarity(normalized_issue, listing_issue)

        if score > best_score and score >= 0.85:
            best_match = listing
            best_score = score

    if best_match:
        return SearchResult(has_results=True, listings=[best_match])
    return None
```

---

## ISSUE NUMBER COMPLEXITY (WHY STRATEGIES NEEDED)

### Issue Numbers Found in Wild

```
Simple (LOW complexity):
- "1", "2", "100"

Medium (MEDIUM complexity):
- "1A", "1B", "1*"
- "1/2", "1/3"
- "#1", "#2"

High (HIGH complexity):
- "-1", "-2" (negative issues)
- "0.5", "0.3" (decimals)
- "1,000,000" (with commas)

Very High (VERY HIGH complexity):
- "1α", "1β" (Greek letters)
- "1/DP", "1/RC" (variant codes)
- "1/Director's Cut" (suffixes)
- "1†" (special symbols)
```

### Why This Matters

```python
# These should match but won't without normalization:
search_comic(title="X-Men", issue="1")
    vs
search_comic(title="X-Men", issue="#1")
    vs
search_comic(title="X-Men", issue="01")
    vs
search_comic(title="X-Men", issue="1A")
```

**Solution:** Try multiple issue formats in `alt_issue_format` strategy.

---

## COMMON MISTAKES (DO NOT DO THESE)

### ❌ MISTAKE 1: Searching Once Per Platform

```python
# WRONG
result = await search_comic(title, issue, year, publisher)
if not result:
    status = "not_found"  # WRONG! Too soon!
```

**CORRECT:**
```python
# RIGHT
for strategy in strategies:
    for retry in range(max_retries):
        result = await search_with_strategy(strategy, ...)
        if result:
            return "found"
        await asyncio.sleep(backoff)
return "not_found"  # Only after all strategies exhausted
```

---

### ❌ MISTAKE 2: Sequential Instead of Parallel

```python
# WRONG - Slow!
for platform in platforms:
    result = await search_platform(platform)  # Blocks on each platform
```

**CORRECT:**
```python
# RIGHT - Fast!
tasks = [search_platform(p) for p in platforms]
results = await asyncio.gather(*tasks)  # All in parallel
```

---

### ❌ MISTAKE 3: Not Updating Status

```python
# WRONG - User sees nothing until done
result = await search_with_all_strategies(...)
return result
```

**CORRECT:**
```python
# RIGHT - User sees progress
for strategy in strategies:
    await update_status(operation_id, platform, f"searching_{strategy}")
    result = await search_with_strategy(strategy, ...)
    if result:
        return result
```

---

### ❌ MISTAKE 4: Skipping Platforms

```python
# WRONG - Skipping source platform
if platform == source_platform:
    continue  # DON'T SKIP!
```

**CORRECT:**
```python
# RIGHT - Mark source as found
platform_status[source_platform] = "found"
```

---

### ❌ MISTAKE 5: Creating Mappings Too Late

```python
# WRONG - Wait until all platforms done
results = await search_all_platforms()
for platform, url in results.items():
    await create_mapping(platform, url)
```

**CORRECT:**
```python
# RIGHT - Create immediately when found
async def search_platform():
    url = await search_with_strategies(...)
    if url:
        await create_mapping(platform, url)  # Create now!
        return url
```

---

### ❌ MISTAKE 6: Not Handling Network Errors

```python
# WRONG - Network error = not_found
try:
    result = await search_comic(...)
except NetworkError:
    return None  # WRONG! Should retry
```

**CORRECT:**
```python
# RIGHT - Retry with backoff
for attempt in range(max_retries):
    try:
        result = await search_comic(...)
        if result:
            return result
    except NetworkError:
        if attempt < max_retries - 1:
            await asyncio.sleep(backoff_time)
        else:
            raise
```

---

### ❌ MISTAKE 7: Using Wrong Issue Number Format

```python
# WRONG - Searching with wrong format
await search_comic(title="X-Men", issue="1A")
    # Platform has "X-Men #1" without variant
    # No match!
```

**CORRECT:**
```python
# RIGHT - Try multiple formats
formats = ["1", "01", "#1", "1A"]
for fmt in formats:
    result = await search_comic(title="X-Men", issue=fmt)
    if result:
        return result
```

---

## TESTING CHECKLIST

Before marking as done, verify:

- [ ] All 6 platforms searched (gcd, locg, aa, ccl, cpg, hip)
- [ ] Multiple strategies attempted per platform
- [ ] Retries with exponential backoff working
- [ ] Real-time status updates visible in CLI
- [ ] Parallel execution (not sequential)
- [ ] Platform-specific configs used
- [ ] Source platform marked as "found" immediately
- [ ] "not_found" only after all strategies exhausted
- [ ] Mappings created immediately when found
- [ ] Timeout after 2 min per platform
- [ ] Timeout after 5 min total operation
- [ ] Network errors trigger retries
- [ ] Fuzzy matching with 0.85 threshold
- [ ] Title normalization working
- [ ] Issue format variants tried

---

## FILES TO MODIFY

### NEW FILES
- `comic_identity_engine/services/platform_searcher.py` (500 lines)
- `tests/test_platform_searcher.py` (300 lines)

### MODIFY FILES
- `comic_identity_engine/jobs/tasks.py` - Replace search_cross_platform() call
- `comic_identity_engine/cli/main.py` - Show intermediate statuses

### DO NOT MODIFY
- `comic_identity_engine/services/identity_resolver.py` - Keep resolve_issue() as-is
- Scrapers in comic-search-lib - They're fine

---

## REFERENCES (READ THESE)

**Must Read:**
1. `IMPLEMENTATION_PLAN.md` lines 363-595 - Identity resolution algorithm
2. `examples/research/issue-suffix-research.md` - Issue number complexity
3. `examples/COMPARISON.md` - Cross-platform differences
4. `/mnt/extra/josh/code/comics_backend/app/routers/library/search_utils.py` - Fuzzy matching utilities

**Optional Reading:**
5. `/mnt/extra/josh/code/comic_matcher/` - Specialized entity resolution library
6. `examples/research/research-issue-zero-handling.md` - Issue #0 handling

---

## FINAL WARNING

**IF YOU IMPLEMENT CROSS-PLATFORM SEARCH WITHOUT READING THIS DOCUMENT:**

1. Users WILL complain that platforms are "not_found" when they actually exist
2. The search WILL be slow (sequential instead of parallel)
3. Network errors WILL cause false negatives
4. You WILL have to rewrite it
5. You WILL waste the user's money on AI credits

**READ THE DOCUMENT. FOLLOW THE PATTERNS. USE THE CONFIGS.**

**END OF DOCUMENT**
