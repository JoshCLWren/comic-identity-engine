# SERIES PAGE STRATEGY - Bulk Cross-Platform Mapping

> **Note:** See AGENTS.md for agent ownership policy and development guidelines.

---

## 🎯 THE CORE STRATEGY

### The Problem with Individual Issue Search

**Wrong Approach (What NOT to do):**
```python
# ❌ Terrible performance!
for issue in csv_import:  # 1000 issues
    for platform in platforms:  # 6 platforms
        result = search_comic(title, issue, year, publisher)  # 6000 searches!
```

**Why This Sucks:**
- **6000 HTTP requests** for 1000 issues
- **6000 seconds** = 1.7 hours (best case)
- **High failure rate** - platform search is often broken
- **Wastes bandwidth** - downloading same series data 1000 times
- **Rate limited** - platforms will block you

### The Solution: Series Page Bulk Extraction

**Correct Approach (What to do):**
```python
# ✅ 10-100x faster!
for series in unique_series:  # ~50 series for 1000 issues
    for platform in platforms:  # 6 platforms
        # Step 1: Find ONE issue from this series
        result = search_comic(title, first_issue, ...)

        if result.found:
            # Step 2: Get series page URL
            series_url = extract_series_url(result.issue_url)

            # Step 3: Scrape ALL issues from series page
            all_issues = scrape_series_page(series_url)  # Returns 20-150 issues!

            # Step 4: Create mappings for ALL issues at once
            for issue in all_issues:
                create_mapping(issue, platform, issue.url)  # Store full URL!
```

**Why This Works:**
- **300 HTTP requests** for 1000 issues (50 series × 6 platforms)
- **300 seconds** = 5 minutes (vs 1.7 hours!)
- **Higher success rate** - if you find one issue, you get the whole series
- **Less bandwidth** - download series page once, get 20-150 issues
- **Platform-friendly** - fewer requests, less likely to be rate limited

---

## PLATFORM-SPECIFIC IMPLEMENTATIONS

### Atomic Avenue (AA)

**Issue URL Pattern:**
```
https://atomicavenue.com/atomic/item/217255/1/x-men-negative-1
                                  ↑      ↑
                                  |      └─ variant/sequence
                                  └─ item ID
```

**Series Page Pattern:**
```
https://atomicavenue.com/atomic/series/16287/1/XMen-2nd-Series
                                    ↑     ↑
                                    |     └─ volume number
                                    └─ series ID
```

**Algorithm:**
```python
def extract_aa_series_url(issue_url: str) -> str:
    """
    Extract series URL from AA issue URL.

    Strategy:
    1. Fetch the issue page
    2. Parse HTML for "Series" link
    3. Extract series ID and construct series URL

    Example:
    Input:  https://atomicavenue.com/atomic/item/217255/1/x-men-negative-1
    Output: https://atomicavenue.com/atomic/series/16287/1/XMen-2nd-Series
    """
    response = http.get(issue_url)
    html = response.text

    # AA always links to series page from issue page
    series_link = parse_html(html).select_one('a[href*="/atomic/series/"]')
    series_id = extract_id(series_link['href'])

    return f"https://atomicavenue.com/atomic/series/{series_id}"

def scrape_aa_series_page(series_url: str) -> list[str]:
    """
    Scrape all issue URLs from AA series page.

    Returns:
        List of full issue URLs for this series
    """
    response = http.get(series_url)
    html = response.text

    # AA series page has all issues in a table/grid
    issue_links = parse_html(html).select('a[href*="/atomic/item/"]')

    return [link['href'] for link in issue_links]
```

---

### Comics Price Guide (CPG)

**Issue URL Pattern:**
```
https://www.comicspriceguide.com/titles/x-men/-1/phvpiu
                                          ↑    ↑
                                          |    └─ issue ID
                                          └─ issue number
```

**Series Page Pattern:**
```
https://www.comicspriceguide.com/titles/x-men/rluy
                                         ↑
                                         └─ series slug
```

**Algorithm:**
```python
def extract_cpg_series_url(issue_url: str) -> str:
    """
    Extract series URL from CPG issue URL.

    Strategy:
    1. Parse URL to get series slug
    2. Remove issue number and issue ID
    3. Construct series URL

    Example:
    Input:  https://www.comicspriceguide.com/titles/x-men/-1/phvpiu
    Output: https://www.comicspriceguide.com/titles/x-men/rluy
    """
    parsed = urlparse(issue_url)
    path_parts = parsed.path.split('/')

    # Path: /titles/x-men/-1/phvpiu
    #         0     1      2  3
    series_slug = path_parts[2]  # "x-men"
    series_id = path_parts[3] if len(path_parts) > 3 else "rluy"

    return f"https://www.comicspriceguide.com/titles/{series_slug}/{series_id}"

def scrape_cpg_series_page(series_url: str) -> list[str]:
    """
    Scrape all issue URLs from CPG series page.

    Returns:
        List of full issue URLs for this series
    """
    response = http.get(series_url)
    html = response.text

    # CPG series page lists all issues with links
    issue_links = parse_html(html).select('a[href*="/titles/"]')

    # Filter out non-issue links (like "view all" buttons)
    issue_urls = [
        link['href']
        for link in issue_links
        if len(link['href'].split('/')) > 4  # Has issue number
    ]

    return issue_urls
```

---

### Comic Collector Live (CCL)

**Issue URL Pattern:**
```
https://www.comiccollectorlive.com/issue/comic-books/X-Men-1991/78/dbea05f8-fde4-409d-abbe-0cdace6f8ac9
                                                           ↑  ↑
                                                           |  └─ GUID (issue ID)
                                                           └─ issue number
```

**Series Page Pattern:**
```
https://www.comiccollectorlive.com/issue/comic-books/X-Men-1991
                                                ↑
                                                └─ series slug
```

**Algorithm:**
```python
def extract_ccl_series_url(issue_url: str) -> str:
    """
    Extract series URL from CCL issue URL.

    Strategy:
    1. Remove issue number and GUID from URL
    2. Keep series slug and path

    Example:
    Input:  https://www.comiccollectorlive.com/issue/comic-books/X-Men-1991/78/dbea05f8...
    Output: https://www.comiccollectorlive.com/issue/comic-books/X-Men-1991
    """
    parsed = urlparse(issue_url)
    path_parts = parsed.path.split('/')

    # Path: /issue/comic-books/X-Men-1991/78/GUID
    #         0     1           2           3  4
    # Keep only up to series slug
    series_path = '/'.join(path_parts[:3])

    return f"{parsed.scheme}://{parsed.netloc}{series_path}"

def scrape_ccl_series_page(series_url: str) -> list[str]:
    """
    Scrape all issue URLs from CCL series page.

    Returns:
        List of full issue URLs for this series

    Note:
        CCL may paginate large series. Need to handle pagination.
    """
    all_issues = []
    page = 1

    while True:
        # CCL uses query params for pagination
        paginated_url = f"{series_url}?page={page}"
        response = http.get(paginated_url)
        html = response.text

        # Parse issue links
        issue_links = parse_html(html).select('a[href*="/issue/comic-books/"]')

        if not issue_links:
            break  # No more issues

        all_issues.extend([link['href'] for link in issue_links])
        page += 1

    return all_issues
```

---

### League of Comic Geeks (LoCG)

**Issue URL Pattern:**
```
https://leagueofcomicgeeks.com/comic/8917101/x-force-11
                                  ↑         ↑
                                  |         └─ issue slug
                                  └─ issue ID
```

**Series Page Pattern:**
```
https://leagueofcomicgeeks.com/comic/111275/x-men-1991
                                  ↑         ↑
                                  |         └─ series slug
                                  └─ series ID
```

**Algorithm:**
```python
def extract_locg_series_url(issue_url: str) -> str:
    """
    Extract series URL from LoCG issue URL.

    Strategy:
    1. Fetch issue page
    2. Parse for series link
    3. Extract series ID and construct series URL

    Example:
    Input:  https://leagueofcomicgeeks.com/comic/8917101/x-force-11
    Output: https://leagueofcomicgeeks.com/comic/111275/x-force-1991
    """
    response = http.get(issue_url)
    html = response.text

    # LoCG issue pages link to series
    series_link = parse_html(html).select_one('a[href*="/comic/"]')
    series_id = extract_id(series_link['href'])

    # Extract series slug from URL
    series_slug = series_link['href'].split('/')[-1]

    return f"https://leagueofcomicgeeks.com/comic/{series_id}/{series_slug}"

def scrape_locg_series_page(series_url: str) -> list[str]:
    """
    Scrape all issue URLs from LoCG series page.

    Returns:
        List of full issue URLs for this series

    Note:
        LoCG series pages may load issues via JavaScript.
        May need to use API endpoints instead of scraping.
    """
    response = http.get(series_url)
    html = response.text

    # LoCG series page has issue listings
    issue_links = parse_html(html).select('a[href*="/comic/"]')

    # Filter out the series link itself
    issue_urls = [
        link['href']
        for link in issue_links
        if not link['href'].rstrip('/').endswith(series_url.rstrip('/').split('/')[-1])
    ]

    return issue_urls
```

---

### Grand Comics Database (GCD)

**Issue URL Pattern:**
```
https://www.comics.org/issue/125295/
                              ↑
                              └─ issue ID
```

**Series Page Pattern:**
```
https://www.comics.org/series/4254/
                             ↑
                             └─ series ID
```

**Algorithm:**
```python
def extract_gcd_series_url(issue_url: str) -> str:
    """
    Extract series URL from GCD issue URL.

    Strategy:
    1. Fetch issue page (JSON API)
    2. Parse series ID from response
    3. Construct series URL

    Example:
    Input:  https://www.comics.org/issue/125295/
    Output: https://www.comics.org/series/4254/
    """
    # GCD has JSON API!
    api_url = f"{issue_url}?format=json"
    response = http.get(api_url)
    data = response.json()

    series_id = data['issue']['series']['id']
    return f"https://www.comics.org/series/{series_id}/"

def scrape_gcd_series_page(series_url: str) -> list[str]:
    """
    Scrape all issue URLs from GCD series page.

    Returns:
        List of full issue URLs for this series

    Note:
        GCD has the BEST series pages with full issue listings.
        Use JSON API for faster parsing.
    """
    # Use JSON API
    api_url = f"{series_url}?format=json"
    response = http.get(api_url)
    data = response.json()

    # Parse all issues from series data
    issue_urls = []
    for issue in data['series']['issues']:
        issue_id = issue['id']
        issue_urls.append(f"https://www.comics.org/issue/{issue_id}/")

    return issue_urls
```

---

## IMPLEMENTATION CHECKLIST

### For Each Platform

- [ ] **URL Parser**: Parse issue URLs correctly
- [ ] **Series URL Extractor**: Extract series URL from issue URL
- [ ] **Series Page Scraper**: Scrape all issues from series page
- [ ] **Pagination Handler**: Handle paginated series pages (if applicable)
- [ ] **API vs HTML**: Use API if available (GCD), fallback to HTML scraping
- [ ] **Error Handling**: Handle 404s, redirects, malformed pages
- [ ] **Rate Limiting**: Respect platform rate limits
- [ ] **Full URL Storage**: Store complete URLs in `external_mappings.source_url`

### For CSV Import Workflow

1. [ ] **Group by Series**: Group CSV rows by series title + year
2. [ ] **First Issue Search**: Search for first issue from each series on all platforms
3. [ ] **Series Page Extraction**: For each found issue, extract series page URL
4. [ ] **Bulk Scraping**: Scrape all issues from each series page
5. [ ] **Bulk Mapping**: Create mappings for all scraped issues
6. [ ] **Progress Tracking**: Update operation status after each series page
7. [ ] **Error Recovery**: Handle failures gracefully, log issues

### For Database Schema

- [ ] **source_url Column**: Already exists in `external_mappings` table
- [ ] **Populate source_url**: Ensure ALL new mappings populate this column
- [ ] **Full URL Required**: Make `source_url` required (NOT NULL) in future migration
- [ ] **Index source_url**: Add index for faster lookups (if needed)

---

## TESTING STRATEGY

### Unit Tests

```python
def test_extract_aa_series_url():
    issue_url = "https://atomicavenue.com/atomic/item/217255/1/x-men-negative-1"
    expected = "https://atomicavenue.com/atomic/series/16287/1/XMen-2nd-Series"
    assert extract_aa_series_url(issue_url) == expected

def test_scrape_gcd_series_page():
    series_url = "https://www.comics.org/series/4254/"
    issues = scrape_gcd_series_page(series_url)
    assert len(issues) > 100  # X-Men (1991) has 100+ issues
    assert "https://www.comics.org/issue/125295/" in issues  # X-Men #-1
```

### Integration Tests

```python
async def test_series_page_workflow():
    # Import small CSV (10 issues from 2 series)
    result = await import_clz_csv("test_10_issues.csv")

    # Should have made ~12 searches (2 series × 6 platforms)
    # NOT 60 searches (10 issues × 6 platforms)
    assert search_call_count == 12

    # All issues should have mappings
    assert len(result.mappings_created) == 10

    # All mappings should have source_url populated
    assert all(m.source_url for m in result.mappings_created)
```

### Performance Tests

```python
def test_series_page_performance():
    # Import 1000 issues from 50 series
    start = time.time()
    result = await import_clz_csv("1000_issues.csv")
    duration = time.time() - start

    # Should complete in <10 minutes
    assert duration < 600

    # Should have made ~300 searches (50 series × 6 platforms)
    assert search_call_count < 400

    # Success rate should be >80%
    assert len(result.mappings_created) > 800
```

---

## COMMON MISTAKES (DO NOT DO THESE)

### ❌ Mistake 1: Searching Each Issue Individually

```python
# WRONG - Insanely slow!
for issue in issues:
    for platform in platforms:
        result = search_comic(issue.title, issue.number, ...)
```

**CORRECT:**
```python
# RIGHT - Fast!
for series in unique_series:
    for platform in platforms:
        result = search_comic(series.title, first_issue, ...)
        if result:
            all_issues = scrape_series_page(result.series_url)
```

---

### ❌ Mistake 2: Not Storing Full URLs

```python
# WRONG - Only storing IDs
await create_mapping(
    issue_id=uuid,
    source="gcd",
    source_issue_id="125295",
    source_url=None,  # ← WRONG!
)
```

**CORRECT:**
```python
# RIGHT - Store full URL
await create_mapping(
    issue_id=uuid,
    source="gcd",
    source_issue_id="125295",
    source_url="https://www.comics.org/issue/125295/",  # ← RIGHT!
)
```

---

### ❌ Mistake 3: Not Handling Pagination

```python
# WRONG - Only gets first page
issues = scrape_series_page(series_url)
```

**CORRECT:**
```python
# RIGHT - Handle pagination
all_issues = []
page = 1
while True:
    issues = scrape_series_page(f"{series_url}?page={page}")
    if not issues:
        break
    all_issues.extend(issues)
    page += 1
```

---

### ❌ Mistake 4: Using HTML When API Available

```python
# WRONG - Scraping GCD HTML
response = http.get(f"https://www.comics.org/issue/{id}/")
html = response.text
data = parse_html(html)  # Slow and fragile!
```

**CORRECT:**
```python
# RIGHT - Use GCD JSON API
response = http.get(f"https://www.comics.org/issue/{id}/?format=json")
data = response.json()  # Fast and reliable!
```

---

## EXPECTED PERFORMANCE IMPROVEMENTS

### Before (Individual Issue Search)

| Metric | Value |
|--------|-------|
| Issues to import | 1,000 |
| Platforms | 6 |
| Total searches | 6,000 |
| Time per search | 1 second |
| Total time | **100 minutes** |
| Success rate | 20-30% |

### After (Series Page Extraction)

| Metric | Value |
|--------|-------|
| Issues to import | 1,000 |
| Unique series | ~50 |
| Platforms | 6 |
| Total searches | **300** (50 × 6) |
| Time per search | 1 second |
| Series page scrape | 5 seconds each |
| Total time | **8 minutes** |
| Success rate | **80-90%** |

**Improvement: 12.5x faster, 3x higher success rate**

---

## FILES TO MODIFY

### New Files

- `comic_identity_engine/services/series_page_extractor.py` - Series page extraction logic
- `tests/test_series_page_extractor.py` - Tests for series page extraction

### Modified Files

- `comic_identity_engine/jobs/tasks.py` - Update CLZ import to use series pages
- `comic_identity_engine/services/platform_searcher.py` - Add series page support
- `comic_identity_engine/database/repositories.py` - Ensure `source_url` is populated

---

## REFERENCES

**Must Read:**
1. `CROSS_PLATFORM_SEARCH.md` - Overall cross-platform search strategy
2. Platform research in `examples/` directory for each platform's URL patterns

**Platform Examples:**
- `examples/gcd/` - GCD URL patterns and API examples
- `examples/atomicavenue/` - AA URL patterns
- `examples/cpg/` - CPG URL patterns
- `examples/comiccollectorlive/` - CCL URL patterns
- `examples/leagueofcomicgeeks/` - LoCG URL patterns

---

## FINAL WARNING

**IF YOU IMPLEMENT CROSS-PLATFORM SEARCH WITHOUT USING SERIES PAGES:**

1. Users WILL complain that imports are too slow
2. The success rate WILL be terrible (20-30%)
3. You WILL be wasting massive amounts of time
4. You WILL have to rewrite it
5. The user WILL be frustrated (again!)

**USE SERIES PAGES. STORE FULL URLs. BULK EXTRACT.**

**END OF DOCUMENT**
