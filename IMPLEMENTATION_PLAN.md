# Comic Identity Engine - Implementation Plan

## Executive Summary

Build a production-ready **cross-platform comic URL lookup service** with:
- **CLI tool + HTTP API** sharing the same async service layer
- **Temporal** for long-running workflow orchestration with retries
- **PostgreSQL** for canonical storage, **Redis** for caching
- **7 platform adapters** (4 reused from comic-web-scrapers, 3 new)
- **AIP 151** compliant async operations with polling
- **AIP 236** compliant batch operations
- **Always async** (no synchronous blocking calls)
- **Structured logging** only (no print statements)

---

## Complete Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Entry Points (Async)                           │
├───────────────────────────────┬─────────────────────────────────────────┤
│          CLI (cie-find)        │      HTTP API (FastAPI + AIP 151)      │
│   Always async with polling    │    Async endpoints + Operations API    │
└───────────────┬───────────────┴─────────────────┬───────────────────────┘
                │                                 │
                └─────────────┬───────────────────┘
                              │
                ┌─────────────▼───────────────────────────────────────┐
                │         Temporal Workflow Orchestrator               │
                ├───────────────────────────────────────────────────────┤
                │ • IssueLookupWorkflow (with retry policies)          │
                │ • BatchLookupWorkflow (parallel processing)          │
                │ • CLZImportWorkflow (CSV parsing + import)           │
                └─────────────┬───────────────────────────────────────┘
                              │
                ┌─────────────▼───────────────────────────────────────┐
                │           Shared Service Layer (All Async)            │
                ├───────────────────────────────────────────────────────┤
                │ • URL Parser (7 platforms)                            │
                │ • Identity Resolver (UPC, series+issue+year matching) │
                │ • URL Builder (generate all platform URLs)           │
                │ • Operations Manager (AIP 151 lifecycle)              │
                └─────────────┬───────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────▼─────────┐  ┌────────▼────────┐  ┌────────▼──────────┐
│   Data Layer    │  │  Cache Layer    │  │ Platform Layer     │
├─────────────────┤  ├─────────────────┤  ├────────────────────┤
│ PostgreSQL      │  │ Redis           │  │ 7 Platform Adapters│
│ • series        │  │ • Web request   │  │ • GCD (extend)     │
│ • issues        │  │ • DB read       │  │ • LoCG (new)       │
│ • mappings      │  │ • Computed      │  │ • CCL (reused)     │
│ • operations    │  │ • TTL + bust    │  │ • AA (reused)      │
│ (asyncpg)       │  │ (aioredis)      │  │ • CPG (reused)     │
└─────────────────┘  └─────────────────┘  │ • HIP (reused)     │
                                          │ • CLZ CSV (new)    │
                                          └────────────────────┘
```

---

## Temporal Workflow Design

### Issue Lookup Workflow

```python
# comic_identity_engine/temporal/workflows/issue_lookup.py

from datetime import timedelta
from temporalio import workflow

@workflow.defn
class IssueLookupWorkflow:
    """Workflow for looking up a comic issue by URL"""

    @workflow.run
    async def run(self, url: str) -> LookupResult:
        """
        Execute lookup workflow with retry policies

        1. Parse URL to extract platform + ID
        2. Check cache (Redis + PostgreSQL)
        3. If not cached, fetch from platform
        4. Resolve to canonical issue
        5. Store mappings
        6. Generate all platform URLs
        7. Return result
        """

        # Step 1: Parse URL
        parsed_url = await workflow.execute_activity(
            parse_url_activity,
            url,
            start_to_close_timeout=timedelta(seconds=5)
        )

        # Step 2: Check cache
        cached_result = await workflow.execute_activity(
            check_cache_activity,
            parsed_url.platform,
            parsed_url.issue_id,
            start_to_close_timeout=timedelta(seconds=2)
        )

        if cached_result:
            workflow.logger.info("cache_hit",
                               platform=parsed_url.platform,
                               issue_id=parsed_url.issue_id)
            return cached_result

        # Step 3: Fetch from platform (with retries)
        issue_candidate = await workflow.execute_activity(
            fetch_from_platform_activity,
            parsed_url.platform,
            parsed_url.issue_id,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=3
            )
        )

        # Step 4: Resolve identity
        resolution = await workflow.execute_activity(
            resolve_identity_activity,
            issue_candidate,
            parsed_url.platform,
            start_to_close_timeout=timedelta(seconds=5)
        )

        # Step 5: Store mappings
        await workflow.execute_activity(
            store_mappings_activity,
            resolution.issue_id,
            parsed_url.platform,
            parsed_url.issue_id,
            start_to_close_timeout=timedelta(seconds=5)
        )

        # Step 6: Generate all URLs
        all_urls = await workflow.execute_activity(
            generate_urls_activity,
            resolution.issue_id,
            start_to_close_timeout=timedelta(seconds=5)
        )

        workflow.logger.info("lookup_complete",
                            issue_id=str(resolution.issue_id),
                            urls_found=len(all_urls))

        return LookupResult(
            issue_id=resolution.issue_id,
            urls=all_urls,
            confidence=resolution.confidence,
            match_method=resolution.match_method
        )
```

### Batch Lookup Workflow

```python
@workflow.defn
class BatchLookupWorkflow:
    """Workflow for batch issue lookups (AIP 236)"""

    @workflow.run
    async def run(self, urls: List[str]) -> BatchLookupResult:
        """
        Execute batch lookup with parallel processing

        Processes URLs in parallel (up to 10 concurrent)
        """

        # Process in parallel
        futures = []
        for url in urls:
            future = await workflow.start_child_workflow(
                IssueLookupWorkflow,
                url,
                id=f"lookup-{hash(url)}",
            )
            futures.append(future)

        # Wait for all to complete
        results = await asyncio.gather(*futures)

        return BatchLookupResult(
            total_count=len(urls),
            successful_count=len([r for r in results if r.success]),
            results=results
        )
```

### Temporal Activities

```python
# comic_identity_engine/temporal/activities/lookup.py

from temporalio import activity

@activity.defn
async def parse_url_activity(url: str) -> ParsedURL:
    """Parse URL and extract platform + IDs"""
    parser = URLParser()
    return parser.parse(url)

@activity.defn
async def fetch_from_platform_activity(
    platform: str,
    issue_id: str
) -> IssueCandidate:
    """Fetch issue from platform (retries on failure)"""
    adapter = get_adapter(platform)
    logger = activity.logger()

    logger.info("fetch_start",
                platform=platform,
                issue_id=issue_id)

    try:
        result = await adapter.fetch_issue(issue_id)
        logger.info("fetch_success",
                    platform=platform,
                    issue_id=issue_id,
                    upc=result.upc)
        return result
    except Exception as e:
        logger.error("fetch_failed",
                     platform=platform,
                     issue_id=issue_id,
                     error=str(e),
                     exc_info=True)
        raise

@activity.defn
async def resolve_identity_activity(
    candidate: IssueCandidate,
    source_platform: str
) -> ResolutionResult:
    """Resolve candidate to canonical issue"""
    resolver = IdentityResolver(db, cache)
    return await resolver.resolve(candidate, source_platform)
```

---

## Docker Compose Setup

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: comic_identity
      POSTGRES_USER: comic_user
      POSTGRES_PASSWORD: comic_pass
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U comic_user"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  temporal:
    image: temporalio/auto-setup:latest
    environment:
      - DB=postgresql
      - DB_PORT=5432
      - POSTGRES_USER=temporal
      - POSTGRES_PWD=temporal
      - POSTGRES_SEEDS=postgres
    ports:
      - "7233:7233"
    depends_on:
      postgres:
        condition: service_healthy

  temporal-ui:
    image: temporalio/ui:latest
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
    ports:
      - "8088:8088"
    depends_on:
      - temporal

volumes:
  postgres_data:
  redis_data:
```

---

## CLZ CSV Import Adapter

### CLZ CSV Format (91 Columns)

Based on analysis of actual CLZ exports from `/mnt/extra/josh/code/comics_backend/data/clz_export.csv`:

**Key Identity Columns:**
- `Core ComicID` - Unique CLZ internal ID (integer)
- `Core SeriesID` - CLZ series identifier (integer)
- `Barcode` - UPC/Barcode for cross-platform matching
- `Series` - Series name
- `Issue Nr` - Issue number with **combined variant notation** (e.g., `-1A`)
- `Variant` - Variant code (when separated from issue)
- `Publisher`
- `Release Date` vs `Cover Date`
- `Format`
- `No. of Pages`

**Critical Format Note:**
CLZ uses **combined variant notation** like `#-1A` (issue + variant together).
Different from other platforms:
- GCD: Separate variant field
- LoCG: Query parameter
- CCL: Letter codes separate from issue
- AA: Slash notation (`-1/A`)

### Implementation

```python
# comic_identity_engine/adapters/clz.py

import pandas as pd
from pathlib import Path

class CLZCSVAdapter(SourceAdapter):
    """
    CLZ (Collectorz.com) CSV import adapter.

    CLZ doesn't have a public API, but users can export their inventory
    as CSV files. This adapter parses those exports.

    Key Format Details:
    - Uses combined variant notation: "-1A" (issue + variant together)
    - 91 columns of data
    - Core ComicID as unique identifier
    - Barcode field for UPC cross-platform matching
    """

    @property
    def platform_name(self) -> str:
        return "clz"

    def __init__(self, csv_path: str):
        self.csv_path = Path(csv_path)
        self._df: Optional[pd.DataFrame] = None
        self.logger = get_logger(__name__)

    async def load_csv(self) -> None:
        """Load CSV file into memory"""
        self.logger.info("clz_csv_loading", path=str(self.csv_path))

        try:
            self._df = pd.read_csv(self.csv_path)
            self.logger.info("clz_csv_loaded",
                           rows=len(self._df),
                           columns=len(self._df.columns))
        except Exception as e:
            self.logger.error("clz_csv_load_failed",
                            path=str(self.csv_path),
                            error=str(e),
                            exc_info=True)
            raise AdapterError(f"Failed to load CLZ CSV: {e}")

    def _parse_combined_issue(self, issue_nr: str) -> Tuple[str, Optional[str]]:
        """
        Parse CLZ's combined issue notation.

        Examples:
            "-1A" → ("-1", "A")
            "1"   → ("1", None)
            "0.5B" → ("0.5", "B")
        """
        if not issue_nr or pd.isna(issue_nr):
            return "", None

        issue_nr = str(issue_nr).strip()

        # Check if ends with letter (variant)
        match = re.match(r'^(-?\d+\.?\d*)([A-Za-z]+)$', issue_nr)
        if match:
            issue_number = match.group(1)
            variant = match.group(2)
            return issue_number, variant

        # No variant
        return issue_nr, None

    async def fetch_issue(self, clz_comic_id: str) -> IssueCandidate:
        """Lookup issue by CLZ Comic ID from loaded CSV"""
        if self._df is None:
            await self.load_csv()

        self.logger.debug("clz_lookup_start",
                         clz_comic_id=clz_comic_id)

        # Find row
        row = self._df[self._df['Core ComicID'] == int(clz_comic_id)]

        if row.empty:
            raise NotFoundError(f"CLZ Comic ID {clz_comic_id} not found")

        row = row.iloc[0]

        # Parse combined issue number
        issue_number, variant = self._parse_combined_issue(row.get('Issue Nr', ''))

        # Extract fields
        candidate = IssueCandidate(
            source='clz',
            source_issue_id=str(row['Core ComicID']),
            source_series_id=str(row['Core SeriesID']),
            series_title=row.get('Series', ''),
            issue_number=issue_number,
            variant_suffix=variant,
            publisher=row.get('Publisher', ''),
            upc=str(row.get('Barcode', '')) if pd.notna(row.get('Barcode')) else None,
            cover_date=self._parse_date(row.get('Cover Date')),
            page_count=int(row['No. of Pages']) if pd.notna(row.get('No. of Pages')) else None,
            format=row.get('Format', ''),
        )

        self.logger.debug("clz_lookup_success",
                         clz_comic_id=clz_comic_id,
                         series=candidate.series_title,
                         issue=candidate.issue_number,
                         variant=variant,
                         upc=candidate.upc)

        return candidate

    async def import_inventory(self) -> List[IssueCandidate]:
        """Import all issues from CSV (for batch processing)"""
        if self._df is None:
            await self.load_csv()

        self.logger.info("clz_import_start",
                        total_issues=len(self._df))

        candidates = []
        for _, row in self._df.iterrows():
            issue_number, variant = self._parse_combined_issue(row.get('Issue Nr', ''))

            candidate = IssueCandidate(
                source='clz',
                source_issue_id=str(row['Core ComicID']),
                source_series_id=str(row['Core SeriesID']),
                series_title=row.get('Series', ''),
                issue_number=issue_number,
                variant_suffix=variant,
                publisher=row.get('Publisher', ''),
                upc=str(row.get('Barcode', '')) if pd.notna(row.get('Barcode')) else None,
            )
            candidates.append(candidate)

        self.logger.info("clz_import_complete",
                        imported=len(candidates))

        return candidates
```

### CLI Command

```bash
# Import CLZ inventory
cie-import-clz /path/to/clz-export.csv --db postgresql:///comic_identity

# Output:
# Loading CLZ CSV: /path/to/clz-export.csv
# Loaded 5,724 issues
# Importing to database...
# ✓ Imported 5,724 issues
# ✓ Created 1,234 new series
# ✓ Generated external ID mappings
# Complete!
```

---

## HTTP API (FastAPI + AIP 151 + AIP 236)

### Endpoints

#### Async Issue Lookup (AIP 151)

```http
POST /v1/issues:lookupByUrlAsync
Content-Type: application/json

{
  "url": "https://www.comics.org/api/issue/125295/"
}
```

**Response (202 Accepted):**
```json
{
  "name": "operations/abc123-xyz789",
  "metadata": {
    "@type": "type.googleapis.com/comic_identity_engine.LookupOperationMetadata",
    "inputUrl": "https://www.comics.org/api/issue/125295/",
    "createTime": "2026-03-01T12:00:00Z"
  },
  "done": false
}
```

#### Poll Operation Status

```http
GET /v1/operations/abc123-xyz789
```

**Response (In Progress):**
```json
{
  "name": "operations/abc123-xyz789",
  "metadata": {
    "stage": "FETCHING_FROM_PLATFORM",
    "platform": "locg",
    "progress": 25
  },
  "done": false
}
```

**Response (Complete):**
```json
{
  "name": "operations/abc123-xyz789",
  "done": true,
  "response": {
    "@type": "type.googleapis.com/comic_identity_engine.LookupIssueResponse",
    "issue": {
      "name": "issues/550e8400-e29b-41d4-a716-446655440001",
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "series": {
        "name": "X-Men",
        "yearBegan": 1991,
        "publisher": "Marvel"
      },
      "number": "-1",
      "displayNumber": "#-1",
      "variant": null,
      "upc": "75960601772099911",
      "coverDate": "1997-07-01"
    },
    "platformUrls": [
      {
        "platform": "gcd",
        "url": "https://www.comics.org/api/issue/125295/?format=json",
        "isCanonical": true
      },
      {
        "platform": "locg",
        "url": "https://leagueofcomicgeeks.com/comic/1169529/x-men-1",
        "isCanonical": true
      }
    ]
  }
}
```

#### Batch Lookup (AIP 236)

```http
POST /v1/issues:batchLookupByUrls
Content-Type: application/json

{
  "urls": [
    "https://www.comics.org/api/issue/125295/",
    "https://leagueofcomicgeeks.com/comic/1169529/x-men-1",
    "https://comiccollectorlive.com/issue/.../-1/..."
  ]
}
```

**Response (202 Accepted):**
```json
{
  "name": "operations/batch-xyz789",
  "metadata": {
    "@type": "type.googleapis.com/comic_identity_engine.BatchLookupOperationMetadata",
    "urlCount": 3,
    "createTime": "2026-03-01T12:00:00Z"
  },
  "done": false
}
```

#### Cancel Operation

```http
POST /v1/operations/abc123-xyz789:cancel
```

#### List Operations

```http
GET /v1/operations?filter=status="running"&pageSize=50&pageToken=xyz
```

---

## CLI Commands (Always Async)

```bash
# Lookup issue (async with polling)
cie-find "https://www.comics.org/api/issue/125295/"

# Output (polling):
# ✓ Operation started: operations/abc123-xyz789
# ⏳ Fetching from platform: gcd...
# ✓ Identity resolved: UPC match (100% confidence)
# ✓ Generating URLs...
#
# GCD:  https://www.comics.org/api/issue/125295/
# LoCG: https://leagueofcomicgeeks.com/comic/1169529/x-men-1
# CCL:  https://comiccollectorlive.com/issue/.../-1/...
# AA:   https://atomicavenue.com/atomic/item/217255/...
# CPG:  https://www.comicspriceguide.com/titles/x-men/-1/phvpiu
# HIP:  https://www.hipcomic.com/price-guide/us/marvel/comic/x-men-1991/1-1/
# CLZ:  https://collectorz.com/comic/x-men-1991/issue/12345
#
# Complete in 3.2s

# Batch lookup
cie-find --batch urls.txt

# Import CLZ CSV
cie-import-clz /path/to/clz-export.csv

# Admin commands
cie-admin migrate
cie-admin seed-database
cie-admin cache-stats
cie-admin bust-cache

# Start API server
cie-api --port 8000
```

---

## Database Schema (Complete)

```sql
-- Canonical series
CREATE TABLE series (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    year_began INTEGER,
    publisher TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(name, year_began, publisher)
);

-- Canonical issues
CREATE TABLE issues (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    series_id UUID NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    number TEXT NOT NULL,
    display_number TEXT,
    variant_suffix TEXT,
    upc TEXT,
    cover_date DATE,
    page_count INTEGER,
    format TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(series_id, number, variant_suffix)
);

-- External ID mappings
CREATE TABLE external_id_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    external_id TEXT NOT NULL,
    series_external_id TEXT,
    url TEXT,
    is_canonical BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(issue_id, platform),
    UNIQUE(platform, external_id)
);

-- Long-running operations (AIP 151)
CREATE TABLE operations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    operation_type TEXT NOT NULL,
    metadata JSONB NOT NULL,
    status TEXT NOT NULL,
    stage TEXT,
    progress INTEGER DEFAULT 0,
    result JSONB,
    error JSONB,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    UNIQUE(name)
);

-- Resolution log (audit trail)
CREATE TABLE resolution_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id UUID REFERENCES issues(id),
    source_platform TEXT,
    match_method TEXT,
    confidence_score DECIMAL(3,2),
    explanation TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- URL templates
CREATE TABLE url_templates (
    platform TEXT PRIMARY KEY,
    base_url TEXT NOT NULL,
    issue_url_pattern TEXT NOT NULL,
    id_type TEXT NOT NULL
);

-- Performance indexes
CREATE INDEX idx_issues_series_number ON issues(series_id, number, variant_suffix);
CREATE INDEX idx_issues_upc ON issues(upc) WHERE upc IS NOT NULL;
CREATE INDEX idx_external_ids_platform ON external_id_mappings(platform, external_id);
CREATE INDEX idx_external_ids_issue ON external_id_mappings(issue_id);
CREATE INDEX idx_operations_status ON operations(status);
CREATE INDEX idx_operations_created ON operations(created_at DESC);
CREATE INDEX idx_resolution_log_issue ON resolution_log(issue_id);
```

---

## Seed Data Migration

```sql
-- X-Men series
INSERT INTO series (id, name, year_began, publisher) VALUES
('550e8400-e29b-41d4-a716-446655440000', 'X-Men', 1991, 'Marvel');

-- X-Men #-1
INSERT INTO issues (id, series_id, number, display_number, upc, cover_date) VALUES
('550e8400-e29b-41d4-a716-446655440001', '550e8400-e29b-41d4-a716-446655440000',
 '-1', '#-1', '75960601772099911', '1997-07-01');

-- External mappings (all 7 platforms)
INSERT INTO external_id_mappings (issue_id, platform, external_id, series_external_id, url) VALUES
('550e8400-e29b-41d4-a716-446655440001', 'gcd', '125295', '4254',
 'https://www.comics.org/api/issue/125295/?format=json'),
('550e8400-e29b-41d4-a716-446655440001', 'locg', '1169529', '111275',
 'https://leagueofcomicgeeks.com/comic/1169529/x-men-1'),
('550e8400-e29b-41d4-a716-446655440001', 'ccl', '98ab98c9-a87a-4cd2-b49a-ee5232abc0ad',
 '84ac79ed-2a10-4a38-9b4c-6df3e0db37de',
 'https://comiccollectorlive.com/issue/comic-books/X-Men-1991/-1/98ab98c9-a87a-4cd2-b49a-ee5232abc0ad'),
('550e8400-e29b-41d4-a716-446655440001', 'aa', '217255', '16287',
 'https://atomicavenue.com/atomic/item/217255/1/XMen-2nd-Series-XMen-2nd-Series-1'),
('550e8400-e29b-41d4-a716-446655440001', 'cpg', 'phvpiu', 'rluy',
 'https://www.comicspriceguide.com/titles/x-men/-1/phvpiu'),
('550e8400-e29b-41d4-a716-446655440001', 'hip', '1-1', 'x-men-1991',
 'https://www.hipcomic.com/price-guide/us/marvel/comic/x-men-1991/1-1/'),
('550e8400-e29b-41d4-a716-446655440001', 'clz', '60070', '5166',
 'https://collectorz.com/comic/x-men-1991/issue/60070');

-- URL templates
INSERT INTO url_templates (platform, base_url, issue_url_pattern, id_type) VALUES
('gcd', 'https://www.comics.org', '/api/issue/{issue_id}/?format=json', 'integer'),
('locg', 'https://leagueofcomicgeeks.com', '/comic/{issue_id}/x-men-1', 'integer'),
('ccl', 'https://comiccollectorlive.com', '/issue/comic-books/{series_slug}/{issue}/{uuid}', 'uuid'),
('aa', 'https://atomicavenue.com', '/atomic/item/{item_id}/1/{slug}', 'integer'),
('cpg', 'https://www.comicspriceguide.com', '/titles/{series_slug}/{issue}/{issue_id}', 'alphanumeric'),
('hip', 'https://www.hipcomic.com', '/price-guide/us/marvel/comic/{series_slug}/{encoded_issue}/', 'complex'),
('clz', 'https://collectorz.com', '/comic/x-men-1991/issue/{issue_id}', 'integer');
```

---

## Redis Caching Strategy

### Cache Keys & TTLs

```python
# Web request cache (HTML/JSON responses)
"web:request:{platform}:{url}" → TTL: 1 hour
"web:request:{platform}:{issue_id}" → TTL: 24 hours

# Database read cache
"db:issue:external_id:{platform}:{external_id}" → TTL: 1 hour
"db:issue:upc:{upc}" → TTL: 1 hour
"db:issue:series_issue:{series_id}:{number}:{variant}" → TTL: 1 hour
"db:series:name:{name}:{year}" → TTL: 24 hours

# Computed results cache
"resolution:{platform}:{external_id}" → TTL: 30 minutes
"urls:{issue_id}" → TTL: 15 minutes
```

### Cache Invalidation

```python
# Invalidate on write
- When new issue stored: invalidate `db:issue:*` caches
- When new mapping added: invalidate `urls:*` caches
- When issue updated: invalidate `resolution:*` caches

# Manual cache busting
CLI: --bust-cache flag
API: POST /v1/admin/cache/bust
```

---

## Dependencies

```toml
[project.dependencies]
# Core
pydantic = "^2.9"
pydantic-settings = "^2.6"

# Database
asyncpg = "^0.30"
alembic = "^1.14"
sqlalchemy = "^2.0"

# Caching
redis = "^5.2"

# Temporal
temporalio = "^1.8"

# HTTP / Scraping
aiohttp = "^3.11"
httpx = "^0.28"
selectolax = "^0.3"

# API
fastapi = "^0.115"
uvicorn = {extras = ["standard"], version = "^0.32"}

# CLI
click = "^8.1"
rich = "^13.9"

# CSV Processing
pandas = "^2.2"

# Logging
structlog = "^25.1"
python-json-logger = "^2.0"

# Environment
python-dotenv = "^1.0"

[project.scripts]
cie-find = "comic_identity_engine.cli.main:cli_find"
cie-import-clz = "comic_identity_engine.cli.commands.import_clz:cli_import_clz"
cie-admin = "comic_identity_engine.cli.commands.admin:cli_admin"
cie-api = "comic_identity_engine.api.app:main"
```

---

## Project Structure

```
comic-identity-engine/
├── comic_identity_engine/
│   ├── __init__.py
│   ├── parsing.py              # Existing (issue number parsing)
│   ├── models.py               # Existing (IssueCandidate, SeriesCandidate)
│   ├── adapters.py             # Existing (SourceAdapter base)
│   ├── gcd_adapter.py          # Existing (extend for fetching)
│   │
│   ├── core/                   # NEW (from comic-web-scrapers/common)
│   │   ├── __init__.py
│   │   ├── errors.py           # Copied from comic-scrapers
│   │   ├── interfaces.py       # Copied from comic-scrapers
│   │   ├── cache.py            # Copied + adapted
│   │   └── logging.py          # Structured logging setup
│   │
│   ├── services/               # NEW (shared business logic)
│   │   ├── __init__.py
│   │   ├── url_parser.py       # URL parsing for all platforms
│   │   ├── identity_resolver.py# Matching & resolution logic
│   │   ├── orchestration.py    # Main lookup orchestration
│   │   ├── url_builder.py      # URL generation
│   │   └── operations.py       # AIP 151 operation management
│   │
│   ├── database/               # NEW (data layer)
│   │   ├── __init__.py
│   │   ├── connection.py       # PostgreSQL connection pool
│   │   ├── models.py           # SQLAlchemy models
│   │   ├── repositories.py     # Repository pattern
│   │   ├── cache.py            # Redis cache layer
│   │   └── seed.py             # Seed data loader
│   │
│   ├── adapters/               # NEW (platform implementations)
│   │   ├── __init__.py
│   │   ├── gcd.py              # Extend existing GCDAdapter
│   │   ├── locg.py             # NEW (LoCG scraping)
│   │   ├── ccl.py              # Adapt from comic-scrapers
│   │   ├── aa.py               # Adapt from comic-scrapers
│   │   ├── cpg.py              # Adapt from comic-scrapers
│   │   ├── hip.py              # Adapt from comic-scrapers
│   │   └── clz.py              # NEW (CSV import adapter)
│   │
│   ├── temporal/               # NEW (Temporal workflows)
│   │   ├── __init__.py
│   │   ├── workflows/
│   │   │   ├── __init__.py
│   │   │   ├── issue_lookup.py
│   │   │   ├── batch_lookup.py
│   │   │   └── clz_import.py
│   │   └── activities/
│   │       ├── __init__.py
│   │       ├── url_parser.py
│   │       ├── fetch.py
│   │       ├── resolve.py
│   │       └── store.py
│   │
│   ├── api/                    # NEW (FastAPI application)
│   │   ├── __init__.py
│   │   ├── app.py              # FastAPI app setup
│   │   ├── routes/
│   │   │   ├── issues.py       # Issue endpoints
│   │   │   ├── operations.py   # AIP 151 endpoints
│   │   │   └── admin.py        # Admin/cache endpoints
│   │   └── schemas.py          # Pydantic models (request/response)
│   │
│   └── cli/                    # NEW (CLI entry point)
│       ├── __init__.py
│       ├── main.py             # CLI entry point
│       └── commands/
│           ├── __init__.py
│           ├── find.py         # cie-find command
│           ├── import_clz.py   # cie-import-clz command
│           └── admin.py        # Admin commands
│
├── tests/                      # Expand with integration tests
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│       └── seed_data.sql       # X-Men #-1 seed data
│
├── migrations/                 # Alembic migrations
│   └── versions/
│       ├── 001_initial_schema.py
│       └── 002_seed_data.py    # Seed X-Men #-1
│
├── docker-compose.yml          # NEW (PostgreSQL + Redis + Temporal)
├── alembic.ini                 # NEW (Alembic config)
├── .env.example                # NEW (template)
├── IMPLEMENTATION_PLAN.md      # This file
├── AGENTS.md                   # Existing (update with new commands)
└── README.md                   # Existing (update)
```

---

## Implementation Phases (6 Weeks)

### Week 1: Foundation
1. Docker Compose (PostgreSQL + Redis + Temporal)
2. PostgreSQL schema + Alembic
3. Seed data migration
4. Copy core infrastructure from comic-web-scrapers
5. Structured logging setup

### Week 2: Core Services
1. URL parser for all 7 platforms
2. Identity resolver service
3. URL builder service
4. Operations manager (AIP 151)
5. Redis cache layer

### Week 3: Platform Adapters (Part 1)
1. Adapt CCL from comic-scrapers to SourceAdapter
2. Adapt AA from comic-scrapers to SourceAdapter
3. Adapt CPG from comic-scrapers to SourceAdapter
4. Adapt HIP from comic-scrapers to SourceAdapter

### Week 4: Platform Adapters (Part 2) + Temporal
1. Extend GCD adapter with async fetching
2. Implement LoCG adapter (new scraper)
3. Implement CLZ CSV adapter (parse combined variant notation)
4. Temporal workflows (IssueLookup, BatchLookup)
5. Temporal activities (fetch, resolve, store)

### Week 5: API + CLI
1. FastAPI application setup
2. AIP 151 endpoints (POST lookupByUrlAsync, GET operations, POST cancel)
3. AIP 236 batch endpoint (POST issues:batchLookupByUrls)
4. CLI with async/polling support
5. CLZ import command

### Week 6: Polish
1. Comprehensive tests (unit + integration)
2. Documentation
3. OpenAPI spec generation
4. Performance tuning
5. Cache optimization

---

## Key Design Decisions

✅ **Temporal** for workflow orchestration with retries
✅ **PostgreSQL** in local Docker for data persistence
✅ **Redis** in local Docker for multi-layer caching
✅ **FastAPI** for HTTP API with Google API Design Guide compliance
✅ **Reuse comic-web-scrapers** infrastructure (errors, cache, session management)
✅ **Reuse 4 existing platform scrapers** (CCL, AA, CPG, HIP)
✅ **CLZ CSV import** based on actual 91-column format with combined variant notation
✅ **Async/await** throughout (aiohttp, asyncpg, aioredis, temporal)
✅ **Shared service layer** for CLI and API
✅ **No authentication** (open access)
✅ **Type hints** and Pydantic validation throughout
✅ **AIP 151** compliant long-running operations
✅ **AIP 236** compliant batch operations
✅ **Structured logging** only (no print statements)
✅ **Keep operations** for audit/analysis (no auto-deletion)
✅ **Allow retries** on failed operations

---

## Platform Adapters Summary

| Platform | Source | Status | Notes |
|----------|--------|--------|-------|
| **GCD** | Existing | Extend | Already have GCDAdapter, add async fetching |
| **LoCG** | NEW | Implement | JavaScript-heavy site, need scraping |
| **CCL** | comic-scrapers | Adapt | UUID-based, excellent URLs |
| **AA** | comic-scrapers | Adapt | Integer IDs, marketplace |
| **CPG** | comic-scrapers | Adapt | Alphanumeric IDs, good URLs |
| **HIP** | comic-scrapers | Adapt | Cryptic encoding (1-1 for -1) |
| **CLZ** | CSV import | NEW | Combined variant notation (-1A) |

---

## Success Criteria

### Functional Requirements
- ✅ Accept URL from any of 7 platforms
- ✅ Parse URL and extract platform + ID
- ✅ Fetch issue data from source platform
- ✅ Resolve to canonical issue entity
- ✅ Generate URLs for all 7 platforms
- ✅ Return results in JSON format
- ✅ Support batch operations (multiple URLs)
- ✅ Support CLZ CSV import
- ✅ Auto-retry failed operations

### Non-Functional Requirements
- ✅ All operations async (no blocking calls)
- ✅ Structured logging only (no prints)
- ✅ Google API Design Guide compliant
- ✅ AIP 151 compliant (long-running operations)
- ✅ AIP 236 compliant (batch operations)
- ✅ PostgreSQL persistence
- ✅ Redis caching with TTL
- ✅ Temporal workflow orchestration
- ✅ Type hints throughout
- ✅ Comprehensive tests

### Performance Targets
- Cache hit: < 10ms
- Database lookup: < 50ms
- Platform fetch: < 30s (with retries)
- End-to-end lookup: < 60s (worst case)

---

## Open Questions for Review

1. **Temporal Worker Deployment**: Should we run Temporal workers in:
   - Same Docker Compose (development)
   - Separate containers (production)
   - Kubernetes (future scalability)

2. **Operation Retention**: You said "keep them" - is there any retention policy needed? (e.g., keep operations for 90 days, then archive)

3. **Batch Size Limits**: For AIP 236 batch operations, what's the maximum batch size we should support? (10, 100, 1000 URLs?)

4. **Rate Limiting**: You said platforms don't rate limit, but should we implement any internal throttling for fairness?

5. **Error Notifications**: Should we add webhook/email notifications for failed operations, or just rely on Temporal's built-in retry?

---

## Next Steps

1. **Review this plan** - Provide feedback on architecture, phases, decisions
2. **Confirm tech stack** - Temporal, FastAPI, PostgreSQL, Redis, asyncio
3. **Approve implementation start** - Begin with Week 1 foundation
4. **Set up review checkpoints** - Weekly progress reviews

---

**Plan Status**: Ready for review and feedback
**Estimated Timeline**: 6 weeks
**Current Status**: Planning complete, awaiting approval to begin implementation
