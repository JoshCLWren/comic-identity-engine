# Platform Search Granularity Analysis
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


## Executive Summary

**Finding:** "One platform search" is NOT the smallest unit of work. The actual smallest atomic operations are:

1. **Single HTTP Request** (network I/O)
2. **Single Database Query** (database I/O)
3. **HTML Parsing/JSON Parsing** (CPU-bound)
4. **Validation Step** (CPU-bound)

**Recommendation:** The ideal task granularity for maximum parallelism is **"one HTTP request"** or **"one database query"**, with the caveat that some operations have dependencies that prevent complete parallelization.

---

## Current Understanding (Incorrect)

```
CSV Import (largest)
  └── Rows (medium)
      └── One platform search (smallest?) ❌ WRONG
```

## Actual Task Hierarchy (Correct)

```
CSV Import (largest)
  └── Rows (medium)
      └── Cross-platform search operation
          └── Single platform search
              └── Search strategy execution
                  ├── HTTP request to platform ✓ (ATOMIC TASK)
                  ├── Rate limit wait ✓ (ATOMIC TASK - but blocks)
                  ├── Retry with backoff ✓ (ATOMIC TASK - but blocks)
                  ├── HTML/JSON parsing ✓ (ATOMIC TASK)
                  ├── Candidate selection ✓ (ATOMIC TASK)
                  ├── Validation ✓ (ATOMIC TASK)
                  └── Database write ✓ (ATOMIC TASK)
```

---

## Detailed Component Analysis

### 1. Platform Adapters (`comic_identity_engine/adapters/`)

#### GCD Adapter (`gcd.py`)

**`fetch_issue()` operation breakdown:**

```python
async def fetch_issue(self, source_issue_id: str, full_url: str | None = None) -> IssueCandidate:
    # Step 1: URL construction (CPU, ~1μs)
    url = f"{self.BASE_URL}/issue/{source_issue_id}/?format=json"

    # Step 2: HTTP GET request (I/O, 100ms-30s)
    response = await self.http_client.get(url)  # ← CAN BE TASK

    # Step 3: Status check (CPU, ~1μs)
    response.raise_for_status()

    # Step 4: JSON parsing (CPU, ~1ms)
    payload = response.json()  # ← CAN BE TASK

    # Step 5: Payload parsing (CPU, ~100μs)
    return self.fetch_issue_from_payload(source_issue_id, payload)  # ← CAN BE TASK
```

**`fetch_issue_from_payload()` operation breakdown:**

```python
def fetch_issue_from_payload(self, source_issue_id: str, payload: dict) -> IssueCandidate:
    # Step 1: Validation (CPU, ~10μs)
    if not payload:
        raise ValidationError("GCD issue payload is empty")

    # Step 2: Field extraction (CPU, ~50μs)
    series_name = payload.get("series_name")
    number = payload.get("number")

    # Step 3: Issue number validation (CPU, ~100μs)
    parse_result = parse_issue_candidate(number)  # ← CAN BE TASK

    # Step 4: Series name parsing (CPU, ~50μs)
    series_title, start_year = self._parse_series_name(series_name)

    # Step 5: Date parsing (CPU, ~50μs)
    cover_date = self._parse_key_date(payload.get("key_date"))

    # Step 6: Object construction (CPU, ~10μs)
    return IssueCandidate(...)
```

**Task opportunities:**
- **HTTP request** → Yes, independent I/O operation
- **JSON parsing** → Yes, CPU-bound but independent
- **Payload parsing** → Yes, CPU-bound but independent
- **Validation** → Yes, CPU-bound but independent

**Dependencies:**
- JSON parsing depends on HTTP request completion
- Payload parsing depends on JSON parsing completion
- Validation depends on payload extraction

**Conclusion:** GCD adapter can be broken into 5-6 independent tasks, but with linear dependencies.

---

### 2. Platform Searcher (`platform_searcher.py`)

#### `search_all_platforms()` Operation

**Current structure:**

```python
async def search_all_platforms(self, issue_id, series_title, issue_number, year, publisher, ...):
    # Creates 6 parallel tasks (one per platform)
    for platform in ["gcd", "locg", "aa", "ccl", "cpg", "hip"]:
        task = asyncio.create_task(
            self._run_platform_search_task(platform, ...)
        )
```

**Already parallelized:** ✓ Platform-level searches run concurrently

#### `_search_single_platform_with_strategies()` Operation

**Single platform search breakdown:**

```python
async def _search_single_platform_with_strategies(self, platform, ...):
    # For each strategy (sequential, not parallel)
    for strategy in ["exact", "no_year", "normalized_title", "fuzzy_title"]:
        # Update DB status (I/O, ~10ms)
        await self._update_platform_status(...)  # ← CAN BE TASK

        # Retry loop with exponential backoff
        for attempt in range(max_retries):
            # Execute search strategy (mixed I/O + CPU)
            result = await self._execute_strategy(...)  # ← CAN BE TASK

            # Select best candidate (CPU, ~1ms)
            candidate_url = self._select_candidate_url(...)  # ← CAN BE TASK

            if candidate_url:
                # Create mapping in DB (I/O, ~10ms)
                await self._create_mapping_from_search_result(...)  # ← CAN BE TASK
                return result
```

**Task opportunities:**
- **Status update** → Yes, independent DB write
- **Strategy execution** → Yes, independent HTTP request
- **Candidate selection** → Yes, CPU-bound comparison
- **Mapping creation** → Yes, independent DB write

**Dependencies:**
- Strategies are sequential (intentional - fallback behavior)
- Candidate selection depends on strategy result
- Mapping creation depends on candidate selection

**Conclusion:** Single platform search is inherently sequential due to fallback strategies, but each strategy execution can be a task.

---

#### `_execute_strategy()` Operation

**Single strategy breakdown:**

```python
async def _execute_strategy(self, scraper, strategy, series_title, issue_number, year, publisher):
    # Normalize search params (CPU, ~100μs)
    search_title = series_title
    search_issue = issue_number

    if strategy == "no_year":
        search_year = None
    elif strategy == "normalized_title":
        search_title = self._normalize_series_name(series_title)
    elif strategy == "fuzzy_title":
        # Two-phase search: broad then filter (I/O + CPU)
        return await self._fuzzy_search(...)  # ← MULTIPLE TASKS

    # Call scraper (I/O, 100ms-30s)
    return await self._call_scraper(scraper, search_title, search_issue, search_year, search_publisher)  # ← CAN BE TASK
```

**Task opportunities:**
- **Title normalization** → Yes, CPU-bound string operations
- **Scraper call** → Yes, independent HTTP request

---

#### `_fuzzy_search()` Operation

**Fuzzy search breakdown:**

```python
async def _fuzzy_search(self, scraper, title, issue, year, publisher):
    # Phase 1: Broad search (I/O, 100ms-30s)
    broad_result = await self._call_scraper(scraper, title, "", year, publisher)  # ← CAN BE TASK

    if not broad_result or not broad_result.listings:
        return None

    # Phase 2: Similarity scoring (CPU, ~10ms)
    for listing in broad_result.listings:  # ← CAN BE PARALLELIZED
        score = jellyfish.jaro_winkler_similarity(title_normalized, listing_title_normalized)
        if score >= 0.85:
            best_match = listing

    # Phase 3: Return best match
    return SearchResult(comic=comic, listings=[best_match], prices=[])
```

**Task opportunities:**
- **Broad search** → Yes, independent HTTP request
- **Similarity calculation** → Yes, CPU-bound and **embarrassingly parallel**

**Dependencies:**
- Similarity scoring depends on broad search completion

**Conclusion:** Fuzzy search has one I/O task followed by parallelizable CPU tasks.

---

### 3. Identity Resolver (`identity_resolver.py`)

#### `resolve_issue()` Operation

**Resolution algorithm breakdown:**

```python
async def resolve_issue(self, parsed_url, upc, series_title, series_start_year, issue_number, cover_date):
    # Phase 1: Check existing mapping (I/O, ~10ms)
    existing = await self.mapping_repo.find_by_source(parsed_url.platform, parsed_url.source_issue_id)  # ← CAN BE TASK
    if existing:
        return ResolutionResult(...)

    candidates = []

    # Phase 2: UPC match (I/O, ~10ms)
    if upc:
        upc_match = await self._match_by_upc(upc)  # ← CAN BE TASK
        if upc_match:
            candidates.append(upc_match)

    # Phase 3: Series + issue + year match (I/O, ~10ms)
    if series_title and issue_number and series_start_year:
        exact_match = await self._match_by_series_issue_year(series_title, issue_number, series_start_year)  # ← CAN BE TASK
        if exact_match:
            candidates.append(exact_match)

    # Phase 4: Series + issue match (I/O, ~10ms)
    if series_title and issue_number and not series_start_year:
        series_match = await self._match_by_series_issue(series_title, issue_number)  # ← CAN BE TASK
        if series_match:
            candidates.append(series_match)

    # Phase 5: Fuzzy title match (I/O + CPU, ~50ms)
    if series_title and not candidates:
        fuzzy_matches = await self._match_by_fuzzy_title(series_title, issue_number)  # ← CAN BE TASK
        candidates.extend(fuzzy_matches)

    # Phase 6: Select best match (CPU, ~1ms)
    if candidates:
        best = max(candidates, key=lambda c: c.overall_confidence)  # ← CAN BE TASK
        return ResolutionResult(issue_id=best.issue_id, ...)

    # Phase 7: Create new issue (I/O, ~20ms)
    created = await self._create_new_issue(series_title, series_start_year, issue_number, cover_date, upc)  # ← CAN BE TASK
    return ResolutionResult(issue_id=created.id, created_new=True, ...)
```

**Task opportunities:**
- **Existing mapping check** → Yes, independent DB query
- **UPC match** → Yes, independent DB query
- **Series + issue + year match** → Yes, 2 sequential DB queries (series → issue)
- **Series + issue match** → Yes, 2 sequential DB queries (series → issue)
- **Fuzzy title match** → Yes, 1 DB query + N similarity calculations (parallelizable)
- **Best match selection** → Yes, CPU-bound comparison
- **Create new issue** → Yes, 2 sequential DB writes (series → issue)

**Dependencies:**
- Resolution algorithm is **intentionally sequential** (fallback priority)
- Fuzzy match only runs if exact matches fail
- Create new issue only runs if all matches fail

**Conclusion:** Identity resolution is inherently sequential due to confidence priority, but individual match operations can be tasks.

---

#### `_match_by_fuzzy_title()` Operation

**Fuzzy matching breakdown:**

```python
async def _match_by_fuzzy_title(self, series_title, issue_number):
    # Phase 1: Fetch all series (I/O, ~10ms)
    stmt = select(SeriesRun).limit(100)
    result = await self.session.execute(stmt)  # ← CAN BE TASK
    all_series = result.scalars().all()

    # Phase 2: Calculate similarity for each series (CPU, ~10ms total, EMBARRASSINGLY PARALLEL)
    matches = []
    for series in all_series:  # ← CAN BE PARALLELIZED
        similarity = jellyfish.jaro_winkler_similarity(series_title.lower(), series.title.lower())
        if similarity >= 0.85:
            if issue_number:
                issue = await self.issue_repo.find_by_number(series.id, issue_number)
                if issue:
                    matches.append(MatchCandidate(...))

    return sorted(matches, key=lambda m: m.issue_confidence, reverse=True)[:5]
```

**Task opportunities:**
- **Fetch all series** → Yes, independent DB query
- **Similarity calculation** → Yes, **embarrassingly parallel** (each series is independent)

**Parallelization potential:** 100 series can be similarity-scored in parallel.

---

### 4. HTTP Client (`http_client.py`)

#### `get()` Operation

**HTTP request breakdown:**

```python
async def get(self, url, params=None, headers=None, **kwargs):
    # Phase 1: Rate limit wait (I/O blocking, 0-1000ms)
    await self._rate_limiter.acquire()  # ← CAN BE TASK (but blocks)

    # Phase 2: HTTP request with retries (I/O, 100ms-30s)
    return await self._request_with_retry("GET", url, params=params, headers=headers, **kwargs)  # ← CAN BE TASK
```

**`_request_with_retry()` breakdown:**

```python
async def _request_with_retry(self, method, url, **kwargs):
    # Retry loop with exponential backoff
    for attempt in range(max_attempts):
        try:
            # Single HTTP request (I/O, 100ms-30s)
            return await self._make_request(method, url, **kwargs)  # ← CAN BE TASK
        except HttpClientError as e:
            if attempt < max_attempts - 1:
                # Exponential backoff wait (I/O blocking, 1s-10s)
                await asyncio.sleep(retry_delay)  # ← CAN BE TASK (but blocks)
```

**`_make_request()` breakdown:**

```python
async def _make_request(self, method, url, **kwargs):
    # Phase 1: DNS resolution (I/O, ~10ms)
    # Phase 2: TCP connection (I/O, ~50ms)
    # Phase 3: TLS handshake (I/O, ~100ms)
    # Phase 4: Request send (I/O, ~1ms)
    # Phase 5: Response wait (I/O, 100ms-30s)
    # Phase 6: Response receive (I/O, ~10ms)
    response = await self._client.request(method, url, **kwargs)  # ← ATOMIC LEAF TASK

    # Phase 7: Status check (CPU, ~1μs)
    response.raise_for_status()

    return response
```

**Task opportunities:**
- **Rate limit wait** → Yes, but blocks execution
- **Single HTTP request** → Yes, **atomic leaf task**
- **Retry with backoff** → Yes, but blocks execution

**Conclusion:** HTTP request is the true atomic leaf task for network I/O.

---

### 5. Database Repositories (`repositories.py`)

#### Repository Method Breakdown

**`find_by_source()` (ExternalMappingRepository):**

```python
async def find_by_source(self, source, source_issue_id):
    # Phase 1: Build query (CPU, ~1μs)
    stmt = select(ExternalMapping).where(
        ExternalMapping.source == source,
        ExternalMapping.source_issue_id == source_issue_id
    )

    # Phase 2: Execute query (I/O, ~1-10ms)
    result = await self.session.execute(stmt)  # ← CAN BE TASK

    # Phase 3: Extract result (CPU, ~1μs)
    return result.scalar_one_or_none()
```

**`create_mapping()` (ExternalMappingRepository):**

```python
async def create_mapping(self, issue_id, source, source_issue_id, source_series_id):
    # Phase 1: Check for duplicate (I/O, ~10ms)
    existing = await self.find_by_source(source, source_issue_id)  # ← CAN BE TASK
    if existing:
        raise DuplicateEntityError(...)

    # Phase 2: Create object (CPU, ~1μs)
    mapping = ExternalMapping(...)

    # Phase 3: Insert into DB (I/O, ~10ms)
    self.session.add(mapping)
    await self.session.flush()  # ← CAN BE TASK

    # Phase 4: Refresh to get defaults (I/O, ~5ms)
    await self.session.refresh(mapping)  # ← CAN BE TASK

    return mapping
```

**Task opportunities:**
- **Single DB query** → Yes, **atomic leaf task**
- **Single DB write** → Yes, **atomic leaf task**

**Dependencies:**
- Create operations depend on duplicate check (business logic)
- Refresh depends on flush completion

**Conclusion:** Database queries/writes are the true atomic leaf tasks for database I/O.

---

## Scrapers (`comic-search-lib/comic_search_lib/scrapers/`)

### GCD Scraper (`gcd.py`)

**`search_comic()` operation breakdown:**

```python
async def search_comic(self, title, issue, year, publisher):
    # Phase 1: Build Comic object (CPU, ~1μs)
    comic = Comic(id=f"search-{time.time()}", title=title, issue=issue, year=year, publisher=publisher)

    # Phase 2: Create HTTP client (CPU, ~1ms)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        # Phase 3: Execute search (mixed I/O + CPU, 100ms-5s)
        return await self._search_with_client(comic, client)  # ← MULTIPLE TASKS
```

**`_search_with_client()` breakdown:**

```python
async def _search_with_client(self, comic, client):
    # Phase 1: Search for series (I/O, 100ms-2s)
    search_url = f"{self.BASE_URL}/search/advanced/"
    params = {"query_type": "series", "keywords": comic.title, "method": "icontains"}
    response = await client.get(search_url, params=params, timeout=self.timeout)  # ← CAN BE TASK

    # Phase 2: Parse HTML to find series (CPU, ~10ms)
    series_list = self._parse_series_results(response.text)  # ← CAN BE TASK

    if not series_list:
        return SearchResult(comic=comic, listings=[], prices=[])

    # Phase 3: For each series, fetch issues (sequential I/O, 100ms-2s each)
    for series in series_list[:3]:  # ← CAN BE PARALLELIZED
        series_response = await client.get(series["url"], timeout=self.timeout)  # ← CAN BE TASK
        issues = self._parse_issues_from_series(series_response.text, str(comic.issue))  # ← CAN BE TASK
        for issue in issues:
            result.listings.append(...)
```

**Task opportunities:**
- **Series search HTTP request** → Yes, independent I/O
- **HTML parsing for series** → Yes, CPU-bound
- **Series page HTTP requests** → Yes, **independent and parallelizable**
- **Issue parsing** → Yes, CPU-bound

**Parallelization potential:** Top 3 series can be fetched in parallel.

**Conclusion:** GCD scraper has 1 initial HTTP request followed by 3 parallelizable HTTP requests.

---

### Atomic Avenue Scraper (`atomic_avenue.py`)

**`search_comic()` operation breakdown:**

```python
async def search_comic(self, title, issue, year, publisher):
    # Phase 1: Build search URL (CPU, ~1μs)
    title_encoded = quote(comic.title, safe="")
    issue_encoded = quote(str(comic.issue), safe="")
    search_url = f"{self.SEARCH_URL}?XT=1&M=1&T={title_encoded}&I={issue_encoded}&PN=1"

    # Phase 2: HTTP GET request (I/O, 100ms-5s)
    response = await client.get(search_url, timeout=self.timeout)  # ← CAN BE TASK

    # Phase 3: Parse HTML (CPU, ~10ms)
    parser = LexborHTMLParser(response.text)

    # Phase 4: Check for redirect to item page (CPU, ~1μs)
    if "/item/" in final_url:
        result.url = final_url
        listings = self._parse_series_listings(parser, str(comic.issue))  # ← CAN BE TASK
        return result

    # Phase 5: Parse search results (CPU, ~10ms)
    return self._parse_search_results(parser, comic)  # ← CAN BE TASK
```

**Task opportunities:**
- **Search HTTP request** → Yes, independent I/O
- **HTML parsing** → Yes, CPU-bound
- **Listing extraction** → Yes, CPU-bound

**Conclusion:** AA scraper has 1 HTTP request followed by CPU-bound parsing.

---

## Atomic Task Inventory

### True Leaf Node Operations (Cannot be broken down further)

| Operation | Type | Duration | Parallelizable | Notes |
|-----------|------|----------|----------------|-------|
| **Single HTTP GET request** | Network I/O | 100ms-30s | ✓ Yes | Rate limited per platform |
| **Single HTTP POST request** | Network I/O | 100ms-30s | ✓ Yes | Rate limited per platform |
| **Rate limit wait** | Blocking I/O | 0-1000ms | ✗ No | Blocks execution |
| **Exponential backoff wait** | Blocking I/O | 1s-10s | ✗ No | Blocks execution |
| **Single DB SELECT query** | Database I/O | 1-10ms | ✓ Yes | Connection pooled |
| **Single DB INSERT query** | Database I/O | 5-20ms | ✓ Yes | Connection pooled |
| **JSON parsing** | CPU | ~1ms | ✓ Yes | Independent |
| **HTML parsing** | CPU | ~10ms | ✓ Yes | Independent |
| **String similarity calculation** | CPU | ~100μs | ✓ Yes | **Embarrassingly parallel** |
| **Issue number validation** | CPU | ~100μs | ✓ Yes | Independent |
| **Candidate selection** | CPU | ~1ms | ✓ Yes | Independent |

### Composite Operations (Can be broken into atomic tasks)

| Operation | Atomic Tasks | Dependencies |
|-----------|--------------|--------------|
| **`fetch_issue()`** | HTTP request → JSON parse → Validation → Parse | Sequential (linear) |
| **`_execute_strategy()`** | Normalize → Scraper call → Parse | Sequential |
| **`_fuzzy_search()`** | Broad search → N × similarity calculations | Sequential I/O, parallel CPU |
| **`_search_with_client()` (GCD)** | Series search → Parse → 3 × series fetches → Parse | 3 parallel fetches |
| **`_match_by_fuzzy_title()`** | Fetch series → N × similarity + issue lookup | Parallel similarity, sequential lookups |
| **`create_mapping()`** | Duplicate check → Insert → Refresh | Sequential |

---

## Dependency Graph

### Cross-Platform Search

```
search_all_platforms()
  ├─→ gcd_search (parallel)
  │   └─→ strategy1 → strategy2 → strategy3 → ... (sequential)
  │       └─→ HTTP request → Parse → Validate (sequential)
  ├─→ locg_search (parallel)
  │   └─→ [same structure]
  ├─→ aa_search (parallel)
  │   └─→ [same structure]
  ├─→ ccl_search (parallel)
  │   └─→ [same structure]
  ├─→ cpg_search (parallel)
  │   └─→ [same structure]
  └─→ hip_search (parallel)
      └─→ [same structure]
```

### Identity Resolution

```
resolve_issue()
  ├─→ check_existing_mapping (task 1)
  │   └─→ DB query
  ├─→ upc_match (task 2, runs if task 1 fails)
  │   └─→ DB query
  ├─→ exact_match (task 3, runs if task 2 fails)
  │   ├─→ DB query (series)
  │   └─→ DB query (issue)
  ├─→ series_match (task 4, runs if task 3 fails)
  │   ├─→ DB query (series)
  │   └─→ DB query (issue)
  ├─→ fuzzy_match (task 5, runs if task 4 fails)
  │   ├─→ DB query (all series)
  │   └─→ N × similarity calculations (parallel)
  └─→ create_new (task 6, runs if task 5 fails)
      ├─→ DB query (series)
      ├─→ DB insert (series, if needed)
      └─→ DB insert (issue)
```

---

## Ideal Task Granularity

### Recommendation: **HTTP Request + Parse = One Task**

**Rationale:**

1. **Network I/O is the bottleneck** (100ms-30s vs ~1ms for CPU)
2. **Parsing depends on response** (can't parse what you don't have)
3. **Natural boundary** (HTTP request/response is a complete unit)
4. **Easy to reason about** (one task = one round-trip)
5. **Error handling is clean** (network errors stay in the task)

**Task definition:**

```python
@dataclass
class HttpTask:
    """Atomic HTTP task."""
    url: str
    method: str = "GET"
    params: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    parse_fn: Callable[[httpx.Response], Any] | None = None

@dataclass
class HttpTaskResult:
    """Result of HTTP task execution."""
    success: bool
    data: Any | None = None
    error: Exception | None = None
    duration_ms: float = 0.0
```

**Example:**

```python
# Task 1: GCD series search
task1 = HttpTask(
    url="https://www.comics.org/search/advanced/",
    params={"query_type": "series", "keywords": "X-Men", "method": "icontains"},
    parse_fn=lambda r: parse_series_html(r.text)
)

# Task 2: GCD series page fetch (depends on task 1)
task2 = HttpTask(
    url=f"https://www.comics.org{series_path}",
    parse_fn=lambda r: parse_issues_html(r.text)
)

# Execute tasks with dependencies
result1 = await execute_task(task1)
result2 = await execute_task(task2)
```

---

## Alternative Granularity Options

### Option 1: **Coarse-Grained** (Current Approach)
- **Task:** One platform search
- **Pros:** Simple, few tasks, easy to reason about
- **Cons:** Low parallelism, poor observability, long-running tasks
- **Duration:** 500ms-30s per task

### Option 2: **Medium-Grained** (Recommended)
- **Task:** HTTP request + parse
- **Pros:** Good parallelism, natural boundaries, clear error handling
- **Cons:** More tasks to manage
- **Duration:** 100ms-5s per task

### Option 3: **Fine-Grained** (Maximum Parallelism)
- **Task:** HTTP request, parse, validate (separate tasks)
- **Pros:** Maximum parallelism, best observability
- **Cons:** Too many tasks, complex dependencies, overhead
- **Duration:** 100ms-30s (HTTP), ~1ms (parse), ~100μs (validate)

### Option 4: **Ultra-Fine-Grained** (Not Recommended)
- **Task:** Individual DB query, similarity calculation, etc.
- **Pros:** Theoretical maximum parallelism
- **Cons:** **Massive** task overhead, complex dependencies, not worth it
- **Duration:** 1-10ms (DB), ~100μs (similarity)

---

## Dependency Constraints

### What CANNOT be Parallelized?

1. **Sequential retry logic** (intentional fallback)
   - Strategies must run in order (exact → no_year → fuzzy)
   - Retries must run in order (attempt 1 → attempt 2 → attempt 3)

2. **Sequential resolution logic** (confidence priority)
   - UPC match → Exact match → Series match → Fuzzy match
   - Each step only runs if previous steps fail

3. **Rate limiting** (platform restriction)
   - Requests to same platform must be serialized
   - Wait times block execution

4. **Business logic dependencies**
   - Duplicate check before insert
   - Series lookup before issue lookup
   - Issue lookup before variant lookup

### What CAN be Parallelized?

1. **Cross-platform searches** ✓
   - All 6 platforms can search simultaneously

2. **Multiple series page fetches** ✓
   - GCD scraper can fetch top 3 series in parallel

3. **Similarity calculations** ✓
   - Fuzzy matching can score 100 series in parallel

4. **Independent HTTP requests** ✓
   - Any requests to different platforms
   - Any requests that don't depend on each other

5. **Independent DB queries** ✓
   - Any queries that don't depend on each other

---

## Task Size Comparison

| Granularity | Tasks per Row | Tasks per CSV (1000 rows) | Avg Task Duration | Total Parallelism Potential |
|-------------|---------------|---------------------------|-------------------|----------------------------|
| **Coarse** (platform search) | ~6 | 6,000 | 500ms-30s | 6× (one per platform) |
| **Medium** (HTTP + parse) | ~30 | 30,000 | 100ms-5s | 30× (strategies × platforms) |
| **Fine** (HTTP, parse, validate) | ~90 | 90,000 | 100μs-5s | 90× (strategies × platforms × steps) |
| **Ultra-fine** (every operation) | ~500 | 500,000 | 100μs-10ms | 500× (but massive overhead) |

**Recommendation:** Medium granularity (HTTP + parse) provides the best balance.

---

## Practical Example: CLZ Import Row

### Current Understanding (Coarse-Grained)

```
Row 1: "X-Men #1"
  └─→ Cross-platform search (1 task, 5-30s)
      ├─→ GCD search (subtask)
      ├─→ LoCG search (subtask)
      ├─→ AA search (subtask)
      ├─→ CCL search (subtask)
      ├─→ CPG search (subtask)
      └─→ HIP search (subtask)
```

### Recommended Understanding (Medium-Grained)

```
Row 1: "X-Men #1"
  └─→ Cross-platform search (orchestrator, not a task)
      ├─→ Task 1: GCD exact strategy (100ms-2s)
      ├─→ Task 2: GCD no_year strategy (100ms-2s, if Task 1 fails)
      ├─→ Task 3: GCD fuzzy strategy (100ms-2s, if Task 2 fails)
      ├─→ Task 4: LoCG exact strategy (100ms-2s, parallel)
      ├─→ Task 5: LoCG no_year strategy (100ms-2s, if Task 4 fails)
      ├─→ Task 6: LoCG fuzzy strategy (100ms-2s, if Task 5 fails)
      ├─→ Task 7-18: AA, CCL, CPG, HIP strategies (parallel)
      ├─→ Task 19: DB status update (10ms)
      ├─→ Task 20: DB mapping insert (10ms)
      └─→ Task 21: Identity resolution (10ms, DB queries)
```

**Total tasks:** ~21 per row (but only ~6 run in parallel at a time due to sequential strategies)

**Parallelism:** 6 platforms × 3 strategies = 18 potential concurrent tasks

**Actual parallelism:** 6 concurrent tasks (one per platform, due to sequential strategies within each platform)

---

## Task Queue Design Implications

### Queue Structure

```
task_queue
  ├─→ priority (high/medium/low)
  ├─→ task_type (http_request, db_query, parse, validate)
  ├─→ platform (gcd, locg, aa, ccl, cpg, hip)
  ├─→ row_id (for grouping)
  ├─→ operation_id (for progress tracking)
  └─→ dependencies (list of task_ids that must complete first)
```

### Worker Pools

```
http_workers (6 workers, one per platform)
  ├─→ gcd_worker (rate limited: 1 req/s)
  ├─→ locg_worker (rate limited: 1 req/s)
  ├─→ aa_worker (rate limited: 1 req/s)
  ├─→ ccl_worker (rate limited: 1 req/s)
  ├─→ cpg_worker (rate limited: 1 req/s)
  └─→ hip_worker (rate limited: 1 req/s)

db_workers (4 workers, connection pool)
  ├─→ db_worker_1
  ├─→ db_worker_2
  ├─→ db_worker_3
  └─→ db_worker_4

cpu_workers (8 workers, CPU-bound tasks)
  ├─→ cpu_worker_1
  ├─→ cpu_worker_2
  ├─→ ...
  └─→ cpu_worker_8
```

### Task Scheduling

1. **HTTP tasks** go to platform-specific worker (rate limiting enforced)
2. **DB tasks** go to any DB worker (connection pooling)
3. **CPU tasks** go to any CPU worker (true parallelism)
4. **Dependencies** are tracked, tasks wait for prerequisites

---

## Conclusions

### What is the ACTUAL smallest unit of work?

**Answer:** The atomic leaf node operations are:

1. **Single HTTP request** (network I/O, 100ms-30s)
2. **Single DB query** (database I/O, 1-10ms)
3. **Single DB write** (database I/O, 5-20ms)
4. **HTML/JSON parsing** (CPU, ~1-10ms)
5. **Similarity calculation** (CPU, ~100μs)
6. **Validation** (CPU, ~100μs)

### Is it "one HTTP request"? "One DB query"? "One validation step"?

**Answer:** Yes, all of the above. The true atomic operations are:

- **I/O-bound:** HTTP request, DB query, DB write
- **CPU-bound:** Parsing, similarity calculation, validation

### Are there dependencies that prevent certain operations from being parallelized?

**Answer:** Yes, significant dependencies:

1. **Sequential resolution strategies** (confidence priority)
2. **Sequential search strategies** (fallback behavior)
3. **Rate limiting** (platform restrictions)
4. **Business logic** (duplicate check before insert, series before issue)

### What's the ideal task granularity for this architecture?

**Answer:** **Medium granularity** (HTTP request + parse = one task)

**Reasons:**

1. **Network I/O dominates** (100ms-30s vs ~1ms for CPU)
2. **Natural boundaries** (HTTP request/response is a complete unit)
3. **Manageable task count** (~21 tasks per row vs ~500 for ultra-fine)
4. **Good observability** (one task = one meaningful operation)
5. **Clear error handling** (network errors stay in the task)

**Not recommended:** Ultra-fine granularity (individual DB queries, similarity calculations) adds too much overhead for marginal gains.

---

## Recommendations

### For CLZ Import Redesign

1. **Task granularity:** One HTTP request + parse = one task
2. **Task types:**
   - `http_request_task` (fetch data from platform)
   - `db_query_task` (lookup existing data)
   - `db_write_task` (insert new data)
   - `parse_task` (HTML/JSON parsing, can be merged with http_request_task)
   - `validate_task` (data validation, can be merged with parse_task)

3. **Worker pools:**
   - 6 HTTP workers (one per platform, rate-limited)
   - 4 DB workers (connection pool)
   - 8 CPU workers (for parsing and validation)

4. **Queue design:**
   - Tasks have dependencies (expressed as prerequisite task IDs)
   - Scheduler waits for dependencies before scheduling dependent tasks
   - Progress tracking updates DB after each task completes

5. **Parallelism strategy:**
   - Cross-platform searches: 6 concurrent tasks (one per platform)
   - Within-platform strategies: Sequential (fallback behavior)
   - Fuzzy matching: Parallel similarity calculations
   - DB operations: Parallel queries/writes

### Expected Performance Improvement

**Current approach (coarse-grained):**
- 1 row = 1 task (cross-platform search)
- Duration: 5-30 seconds per row
- Parallelism: Limited by number of workers processing entire rows

**Recommended approach (medium-grained):**
- 1 row = ~21 tasks (HTTP requests + DB operations)
- Duration: Same 5-30 seconds per row, but **better observability**
- Parallelism: 6 concurrent HTTP tasks + 4 concurrent DB tasks
- **Key benefit:** Progress can be tracked at HTTP-request granularity, not platform-search granularity

**Ultra-fine approach (not recommended):**
- 1 row = ~500 tasks (every operation)
- Duration: Same 5-30 seconds per row, with **massive overhead**
- Parallelism: Theoretical maximum, but task scheduling overhead dominates
- **Not worth it:** Overhead of managing 500 tasks outweighs parallelism benefits

---

## Appendix: Task Flow Example

### Row: "X-Men #1, 1963"

```
Task 1 (http_request): GCD exact search
  ├─→ URL: https://www.comics.org/search/advanced/?keywords=X-Men&year=1963
  ├─→ Duration: 1.2s
  └─→ Result: Found series ID 4254

Task 2 (http_request): GCD series page fetch (depends on Task 1)
  ├─→ URL: https://www.comics.org/series/4254/
  ├─→ Duration: 0.8s
  └─→ Result: Found issue ID 125295

Task 3 (db_query): Check existing mapping for gcd:125295
  ├─→ Query: SELECT * FROM external_mappings WHERE source='gcd' AND source_issue_id='125295'
  ├─→ Duration: 8ms
  └─→ Result: Not found

Task 4 (db_write): Insert mapping gcd:125295 → canonical_issue_id
  ├─→ Insert: INSERT INTO external_mappings (issue_id, source, source_issue_id) VALUES (...)
  ├─→ Duration: 12ms
  └─→ Result: Created

Task 5 (http_request): LoCG exact search (parallel with Task 1)
  ├─→ URL: https://leagueofcomicgeeks.com/comic/x-men/1963/1
  ├─→ Duration: 2.1s
  └─→ Result: Found

... (similar tasks for AA, CCL, CPG, HIP)
```

**Total:** 21 tasks
**Parallel execution:** Tasks 1, 5, 7, 9, 11, 13 run concurrently (6 platforms)
**Sequential execution:** Task 2 depends on Task 1, Task 3 depends on Task 2, etc.

**Timeline:**
```
Time:  0s    1s    2s    3s    4s    5s
       |-----|-----|-----|-----|-----|
Task1: [====]                          (GCD search, 1.2s)
Task5: [=========]                    (LoCG search, 2.1s)
Task7: [===]                          (AA search, 0.5s)
Task9: [=======]                     (CCL search, 1.8s)
Task11:[====]                        (CPG search, 1.1s)
Task13:[=======]                     (HIP search, 1.9s)
Task2:       [==]                     (GCD series, 0.8s, depends on Task1)
Task14:      [==]                     (LoCG issues, 0.7s, depends on Task5)
...
```

**Key insight:** Even though we have 21 tasks, only 6 run concurrently at a time due to platform rate limiting and sequential strategy dependencies.
