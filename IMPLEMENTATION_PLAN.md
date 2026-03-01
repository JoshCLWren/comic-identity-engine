# Comic Identity Engine - Implementation Plan (Revised)

## Executive Summary

Build a production-ready **cross-platform comic URL lookup service** with:
- **CLI tool + HTTP API** sharing the same async service layer
- **arq** for async job queue orchestration with retries
- **PostgreSQL** for canonical storage and job queue
- **Redis** for caching and arq backend
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
                │            arq Job Queue (Redis-backed)              │
                ├───────────────────────────────────────────────────────┤
                │ • enqueue_issue_lookup()                             │
                │ • enqueue_batch_lookup() (with concurrency limit)     │
                │ • enqueue_clz_import()                               │
                │ • Worker functions with retry policies                │
                └─────────────┬───────────────────────────────────────┘
                              │
                ┌─────────────▼───────────────────────────────────────┐
                │           Shared Service Layer (All Async)            │
                ├───────────────────────────────────────────────────────┤
                │ • URL Parser (7 platforms)                            │
                │ • Identity Resolver (detailed algorithm below)         │
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
│ • operations    │  │ • arq queue     │  │ • AA (reused)      │
│ • jobs          │  │ • TTL + bust    │  │ • CPG (reused)     │
│ (asyncpg)       │  │ (redis-py 5.x)  │  │ • HIP (reused)     │
└─────────────────┘  └─────────────────┘  │ • CLZ CSV (new)    │
                                           └────────────────────┘
```

---

## arq Job Queue Design

### Why arq?

**arq** is an async job queue built on asyncio and Redis:
- **Async-native**: Built with `asyncio` from the ground up
- **Connection pooling**: Integrates with `aiohttp` session pooling from comic-web-scrapers
- **Redis backend**: Uses Redis (already in stack) for job queue
- **Retry logic**: Built-in exponential backoff and retries
- **Simple**: Much lighter than Temporal or Celery
- **Monitoring**: Built-in job stats and monitoring
- **Workers**: Async worker processes with configurable concurrency

### Worker Functions

```python
# comic_identity_engine/jobs/workers.py

import asyncio
from arq import create_pool
from arq.connections import RedisSettings
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

from comic_identity_engine.core.logging import get_logger
from comic_identity_engine.services.url_parser import URLParser
from comic_identity_engine.services.identity_resolver import IdentityResolver
from comic_identity_engine.database.repositories import IssueRepository
from comic_identity_engine.adapters import get_adapter

logger = get_logger(__name__)

# Dependency injection via worker ctx
async def startup(ctx):
    """Initialize worker dependencies"""
    ctx['db'] = await IssueRepository.create()
    ctx['cache'] = await create_pool(RedisSettings())
    ctx['session_manager'] = AioHttpSessionManager()
    logger.info("worker_started")

async def shutdown(ctx):
    """Cleanup worker dependencies"""
    await ctx['db'].close()
    await ctx['cache'].close()
    await ctx['session_manager'].close()
    logger.info("worker_stopped")

# Worker function: Issue lookup
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
)
async def lookup_issue(ctx, operation_id: str, url: str) -> dict:
    """
    Worker function for single issue lookup.

    Steps:
    1. Parse URL to extract platform + ID
    2. Check cache (Redis + PostgreSQL)
    3. If not cached, fetch from platform
    4. Resolve to canonical issue
    5. Store mappings
    6. Generate all platform URLs
    7. Update operation status
    """
    log = logger.bind(operation_id=operation_id, url=url)

    # Step 1: Parse URL
    log.info("parsing_url")
    parser = URLParser()
    parsed_url = parser.parse(url)
    log.debug("url_parsed", platform=parsed_url.platform, issue_id=parsed_url.issue_id)

    # Step 2: Check cache
    cached = await ctx['cache'].get(f"resolution:{parsed_url.platform}:{parsed_url.issue_id}")
    if cached:
        log.info("cache_hit", platform=parsed_url.platform)
        result = json.loads(cached)
        await update_operation_status(operation_id, "completed", result=result)
        return result

    # Step 3: Fetch from platform (with retry via tenacity decorator)
    log.info("fetching_from_platform", platform=parsed_url.platform)
    adapter = get_adapter(parsed_url.platform, session_manager=ctx['session_manager'])
    issue_candidate = await adapter.fetch_issue(parsed_url.issue_id)
    log.debug("platform_fetch_success",
                platform=parsed_url.platform,
                series=issue_candidate.series_title,
                issue=issue_candidate.issue_number,
                upc=issue_candidate.upc)

    # Step 4: Resolve identity
    log.info("resolving_identity")
    resolver = IdentityResolver(ctx['db'], ctx['cache'])
    resolution = await resolver.resolve(issue_candidate, parsed_url.platform)
    log.debug("identity_resolved",
                issue_id=str(resolution.issue_id),
                confidence=resolution.confidence,
                match_method=resolution.match_method)

    # Step 5: Store mappings
    log.info("storing_mappings")
    await ctx['db'].store_external_mapping(
        issue_id=resolution.issue_id,
        platform=parsed_url.platform,
        external_id=parsed_url.issue_id,
        url=url
    )

    # Step 6: Generate all URLs
    log.info("generating_urls")
    from comic_identity_engine.services.url_builder import URLBuilder
    url_builder = URLBuilder(ctx['db'], ctx['cache'])
    all_urls = await url_builder.build_urls_for_issue(resolution.issue_id)
    log.debug("urls_generated", count=len(all_urls))

    # Step 7: Cache result
    result = {
        "issue_id": str(resolution.issue_id),
        "urls": all_urls,
        "confidence": resolution.confidence,
        "match_method": resolution.match_method
    }
    await ctx['cache'].set(
        f"resolution:{parsed_url.platform}:{parsed_url.issue_id}",
        json.dumps(result),
        ex=1800  # 30 minutes
    )

    # Step 8: Update operation status
    await update_operation_status(operation_id, "completed", result=result)

    log.info("lookup_complete",
                issue_id=str(resolution.issue_id),
                urls_count=len(all_urls))

    return result

# Worker function: Batch lookup with concurrency control
async def lookup_batch(ctx, operation_id: str, urls: list[str]) -> dict:
    """
    Worker function for batch issue lookup.

    Processes URLs in parallel with semaphore-controlled concurrency.

    Note: Retry logic is inside process_one AFTER semaphore acquisition
    to prevent holding semaphore slot during retries.
    """
    log = logger.bind(operation_id=operation_id, url_count=len(urls))

    semaphore = asyncio.Semaphore(10)  # Max 10 concurrent
    results = []

    async def process_one(url):
        """
        Process a single URL with timeout.

        Acquires semaphore first, then retries with timeout.
        This prevents holding semaphore during retry backoff.
        """
        async with semaphore:
            sub_op_id = str(uuid.uuid4())
            try:
                # Add timeout to prevent one slow URL from blocking batch
                result = await asyncio.wait_for(
                    lookup_issue(ctx, sub_op_id, url),
                    timeout=60.0  # 60 second timeout per URL
                )
                return {"url": url, "success": True, "result": result}
            except asyncio.TimeoutError:
                log.error("batch_item_timeout", url=url, timeout_seconds=60)
                return {"url": url, "success": False, "error": "Timeout after 60s"}
            except Exception as e:
                log.error("batch_item_failed", url=url, error=str(e), exc_info=True)
                return {"url": url, "success": False, "error": str(e)}

    log.info("batch_processing_start", concurrent_limit=10)
    results = await asyncio.gather(*[process_one(url) for url in urls])

    successful = len([r for r in results if r["success"]])
    log.info("batch_processing_complete", successful=successful, total=len(results))

    await update_operation_status(
        operation_id,
        "completed",
        result={
            "total_count": len(urls),
            "successful_count": successful,
            "results": results
        }
    )

    return {
        "total_count": len(urls),
        "successful_count": successful,
        "results": results
    }

# Worker function: CLZ CSV import
async def import_clz_csv(ctx, operation_id: str, csv_path: str) -> dict:
    """
    Worker function for importing CLZ CSV inventory.

    Uses csv module (not pandas) for lighter weight parsing.

    Note: CSV file I/O is blocking. For 5,700 rows this blocks for ~100-200ms.
    This is acceptable for a one-time import operation.
    """
    log = logger.bind(operation_id=operation_id, csv_path=csv_path)
    log.info("clz_import_start")

    from comic_identity_engine.adapters.clz import CLZCSVAdapter

    adapter = CLZCSVAdapter(csv_path)
    await adapter.load_csv()
    candidates = await adapter.import_inventory()

    log.info("clz_import_processing", total=len(candidates))

    # Move resolver out of loop to avoid re-instantiation
    resolver = IdentityResolver(ctx['db'], ctx['cache'])
    imported = 0

    for candidate in candidates:
        try:
            resolution = await resolver.resolve(candidate, "clz")
            await ctx['db'].store_external_mapping(
                issue_id=resolution.issue_id,
                platform="clz",
                external_id=candidate.source_issue_id,
                url=None  # CLZ doesn't have URLs
            )
            imported += 1
        except Exception as e:
            log.warning("clz_import_item_failed",
                          clz_id=candidate.source_issue_id,
                          error=str(e))

    log.info("clz_import_complete", imported=imported, total=len(candidates))

    await update_operation_status(
        operation_id,
        "completed",
        result={"imported": imported, "total": len(candidates)}
    )

    return {"imported": imported, "total": len(candidates)}
```

### arq Worker Configuration

```python
# comic_identity_engine/jobs/worker.py

from arq import Worker
from arq.connections import RedisSettings

from comic_identity_engine.jobs.workers import (
    startup,
    shutdown,
    lookup_issue,
    lookup_batch,
    import_clz_csv
)

class WorkerSettings:
    """
    arq worker configuration.

    Features:
    - Redis backend
    - Connection pooling via startup/shutdown hooks
    - Retry policies via tenacity decorators
    - Concurrency limits
    """
    functions = [lookup_issue, lookup_batch, import_clz_csv]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings(
        host='localhost',
        port=6379,
        database=0  # Use DB 0 for arq queue, DB 1 for app cache
    )
    max_jobs = 10  # Max 10 concurrent jobs per worker
    job_timeout = 300  # 5 minutes max per job
    retry_jobs = True
    max_tries = 3
    health_check_interval = 60
```

---

## Identity Resolution Algorithm

This is the core of the system. The `IdentityResolver` determines whether a candidate issue from a platform matches an existing canonical issue, or if a new canonical issue should be created.

### Matching Priority (Confidence Scores)

```python
# comic_identity_engine/services/identity_resolver.py

from dataclasses import dataclass
from typing import Optional, Tuple
from decimal import Decimal

@dataclass
class ResolutionResult:
    issue_id: UUID
    confidence: Decimal  # 0.00 to 1.00
    match_method: str
    explanation: str

class IdentityResolver:
    """
    Resolve candidate issues to canonical entities.

    Matching priority:
    1. UPC exact match → 1.00 confidence (100%)
    2. Series name + issue number + year → 0.95 confidence (95%)
    3. Series name + issue number (no year) → 0.85 confidence (85%)
    4. Title similarity + publisher + year → 0.70 confidence (70%)
    5. No match → create new → 1.00 confidence (new entry)
    """

    async def resolve(
        self,
        candidate: IssueCandidate,
        source_platform: str
    ) -> ResolutionResult:
        """
        Resolve candidate to canonical issue.

        Returns ResolutionResult with confidence score and explanation.
        """
        logger = get_logger(__name__).bind(
            source_platform=source_platform,
            series=candidate.series_title,
            issue=candidate.issue_number,
            variant=candidate.variant_suffix
        )

        # Priority 1: UPC exact match (100% confidence)
        if candidate.upc:
            logger.debug("attempting_upc_match", upc=candidate.upc)
            issue = await self.db.find_issue_by_upc(candidate.upc)
            if issue:
                logger.info("upc_match_found",
                           issue_id=str(issue.id),
                           upc=candidate.upc)
                return ResolutionResult(
                    issue_id=issue.id,
                    confidence=Decimal('1.00'),
                    match_method="upc_exact_match",
                    explanation=f"UPC {candidate.upc} matches exactly"
                )

        # Priority 2: Series name + issue number + year (95% confidence)
        if candidate.cover_date:
            year = candidate.cover_date.year
            logger.debug("attempting_series_issue_year_match", year=year)
            issues = await self.db.find_issues_by_series_issue_year(
                series_name=candidate.series_title,
                issue_number=candidate.issue_number,
                year=year
            )
            if issues:
                # Filter by variant
                variant_match = [
                    i for i in issues
                    if i.variant_suffix == candidate.variant_suffix
                ]
                if variant_match:
                    issue = variant_match[0]
                    logger.info("series_issue_year_match_found",
                               issue_id=str(issue.id),
                               series=candidate.series_title,
                               issue=candidate.issue_number,
                               year=year)
                    return ResolutionResult(
                        issue_id=issue.id,
                        confidence=Decimal('0.95'),
                        match_method="series_issue_year_match",
                        explanation=f"Series '{candidate.series_title}' issue {candidate.issue_number} from {year} matches"
                    )

        # Priority 3: Series name + issue number (no year) (85% confidence)
        logger.debug("attempting_series_issue_match")
        issues = await self.db.find_issues_by_series_issue(
            series_name=candidate.series_title,
            issue_number=candidate.issue_number
        )
        if issues:
            # Prefer variant match, fall back to base issue
            variant_match = [
                i for i in issues
                if i.variant_suffix == candidate.variant_suffix
            ]
            if variant_match:
                issue = variant_match[0]
            else:
                # Use base issue (no variant)
                base_match = [i for i in issues if i.variant_suffix is None]
                if base_match:
                    issue = base_match[0]
                else:
                    issue = issues[0]  # Fallback to first match

            logger.info("series_issue_match_found",
                       issue_id=str(issue.id),
                       series=candidate.series_title,
                       issue=candidate.issue_number)
            return ResolutionResult(
                issue_id=issue.id,
                confidence=Decimal('0.85'),
                match_method="series_issue_match",
                explanation=f"Series '{candidate.series_title}' issue {candidate.issue_number} matches (no year)"
            )

        # Priority 4: Fuzzy title similarity (70% confidence)
        # Only used if we have publisher and title
        if candidate.publisher and candidate.series_title:
            logger.debug("attempting_fuzzy_title_match")
            series = await self.db.find_series_by_fuzzy_name(
                name=candidate.series_title,
                publisher=candidate.publisher
            )
            if series:
                # Check for issue match within this series
                issues = await self.db.find_issues_by_series(
                    series_id=series.id,
                    issue_number=candidate.issue_number
                )
                if issues:
                    issue = issues[0]
                    logger.info("fuzzy_title_match_found",
                               issue_id=str(issue.id),
                               input_series=candidate.series_title,
                               matched_series=series.name,
                               similarity=series.similarity_score)
                    return ResolutionResult(
                        issue_id=issue.id,
                        confidence=Decimal('0.70'),
                        match_method="fuzzy_title_match",
                        explanation=f"Fuzzy series name match: '{candidate.series_title}' → '{series.name}' (score: {series.similarity_score:.2f})"
                    )

        # Priority 5: No match found → create new canonical issue
        logger.info("no_match_found_creating_new")
        issue_id = await self.db.create_issue_from_candidate(candidate)
        logger.info("new_issue_created",
                   issue_id=str(issue_id),
                   series=candidate.series_title,
                   issue=candidate.issue_number)

        return ResolutionResult(
            issue_id=issue_id,
            confidence=Decimal('1.00'),
            match_method="new_issue_created",
            explanation=f"Created new canonical issue for {candidate.series_title} #{candidate.issue_number}"
        )
```

### Fuzzy Matching Algorithm

For series name matching across platforms (e.g., "X-Men" vs "X-Men (2nd Series)"), we use **Jaro-Winkler similarity**:

```python
import jellyfish  # For Jaro-Winkler similarity

async def find_series_by_fuzzy_name(
    self,
    name: str,
    publisher: str,
    threshold: float = 0.85
) -> Optional[Series]:
    """
    Find series by fuzzy name matching.

    Uses Jaro-Winkler similarity for string matching.
    Threshold of 0.85 means 85% similar or better.
    """
    # Normalize input
    normalized_name = self._normalize_series_name(name)

    # Get all series from publisher
    all_series = await self.db.find_series_by_publisher(publisher)

    # Find best match
    best_match = None
    best_score = 0.0

    for series in all_series:
        score = jellyfish.jaro_winkler_similarity(
            normalized_name,
            self._normalize_series_name(series.name)
        )
        if score > best_score and score >= threshold:
            best_match = series
            best_score = score

    if best_match:
        best_match.similarity_score = best_score

    return best_match

def _normalize_series_name(self, name: str) -> str:
    """
    Normalize series name for fuzzy matching.

    Transformations:
    - Lowercase
    - Remove extra whitespace
    - Remove common suffixes: "(2nd Series)", "Vol. 2", etc.
    - Remove special characters
    """
    import re

    name = name.lower().strip()
    name = re.sub(r'\s+', ' ', name)  # Normalize whitespace
    name = re.sub(r'\(.*?\)', '', name)  # Remove parentheticals
    name = re.sub(r'vol\.?\s*\d+', '', name)  # Remove volume numbers
    name = name.strip()

    return name
```

### Series Name Normalization Examples

| Input                     | Normalized Output    | Notes                                    |
|---------------------------|----------------------|------------------------------------------|
| "X-Men"                   | "x-men"              | Base case                                |
| "X-Men (2nd Series)"      | "x-men"              | Parenthetical removed                    |
| "X-Men Vol. 2"           | "x-men"              | Volume removed                           |
| "X-MEN"                   | "x-men"              | Case normalized                          |
| "X-Men  (1991)"          | "x-men"              | Year parenthetical removed               |
| "Justice League: Another Nail" | "justice league: another nail" | Title with subtitle kept |
| "Batman   -   The Dark Knight" | "batman the dark knight" | Extra whitespace removed |

### Confidence Score Interpretation

| Score | Range   | Meaning                              | Action                           |
|-------|---------|--------------------------------------|----------------------------------|
| 1.00  | 100%    | UPC exact match OR new issue created | Automatic acceptance             |
| 0.95  | 95%     | Series + issue + year match          | Automatic acceptance             |
| 0.85  | 85%     | Series + issue match (no year)       | Automatic acceptance             |
| 0.70  | 70%     | Fuzzy title match                    | Flag for review if in production |
| <0.70 | <70%    | Low confidence                       | Reject, create new issue          |

---

## Docker Compose Setup

```yaml
version: '3.8'

services:
  # Application database
  postgres-app:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: comic_identity
      POSTGRES_USER: comic_user
      POSTGRES_PASSWORD: comic_pass
    ports:
      - "5432:5432"
    volumes:
      - postgres_app_data:/var/lib/postgresql/data
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
    command: >
      redis-server
      --databases 2  # DB 0 for arq queue, DB 1 for app cache

volumes:
  postgres_app_data:
  redis_data:
```

**Note**: Temporal and Temporal UI removed. We now use arq with Redis backend only.

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

import csv
from pathlib import Path
from typing import List, Optional, Tuple

class CLZCSVAdapter(SourceAdapter):
    """
    CLZ (Collectorz.com) CSV import adapter.

    CLZ doesn't have a public API, but users can export their inventory
    as CSV files. This adapter parses those exports.

    Uses stdlib csv module (not pandas) for lighter weight.

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
        self._rows: Optional[List[dict]] = None
        self.logger = get_logger(__name__)

    async def load_csv(self) -> None:
        """Load CSV file into memory using stdlib csv module"""
        self.logger.info("clz_csv_loading", path=str(self.csv_path))

        try:
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                self._rows = list(reader)

            self.logger.info("clz_csv_loaded",
                           rows=len(self._rows))
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
        if not issue_nr or not issue_nr.strip():
            return "", None

        issue_nr = issue_nr.strip()

        # Check if ends with letter (variant)
        import re
        match = re.match(r'^(-?\d+\.?\d*)([A-Za-z]+)$', issue_nr)
        if match:
            issue_number = match.group(1)
            variant = match.group(2)
            return issue_number, variant

        # No variant
        return issue_nr, None

    async def fetch_issue(self, clz_comic_id: str) -> IssueCandidate:
        """Lookup issue by CLZ Comic ID from loaded CSV"""
        if self._rows is None:
            await self.load_csv()

        self.logger.debug("clz_lookup_start", clz_comic_id=clz_comic_id)

        # Find row
        row = None
        for r in self._rows:
            if r.get('Core ComicID') == clz_comic_id:
                row = r
                break

        if not row:
            raise NotFoundError(f"CLZ Comic ID {clz_comic_id} not found")

        # Parse combined issue number
        issue_number, variant = self._parse_combined_issue(row.get('Issue Nr', ''))

        # Extract fields
        candidate = IssueCandidate(
            source='clz',
            source_issue_id=row['Core ComicID'],
            source_series_id=row['Core SeriesID'],
            series_title=row.get('Series', ''),
            issue_number=issue_number,
            variant_suffix=variant,
            publisher=row.get('Publisher', ''),
            upc=row.get('Barcode') if row.get('Barcode') else None,
            cover_date=self._parse_date(row.get('Cover Date')),
            page_count=int(row['No. of Pages']) if row.get('No. of Pages') and row['No. of Pages'].isdigit() else None,
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
        if self._rows is None:
            await self.load_csv()

        self.logger.info("clz_import_start", total_issues=len(self._rows))

        candidates = []
        for row in self._rows:
            issue_number, variant = self._parse_combined_issue(row.get('Issue Nr', ''))

            candidate = IssueCandidate(
                source='clz',
                source_issue_id=row['Core ComicID'],
                source_series_id=row['Core SeriesID'],
                series_title=row.get('Series', ''),
                issue_number=issue_number,
                variant_suffix=variant,
                publisher=row.get('Publisher', ''),
                upc=row.get('Barcode') if row.get('Barcode') else None,
            )
            candidates.append(candidate)

        self.logger.info("clz_import_complete", imported=len(candidates))

        return candidates
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

# Start arq worker
cie-worker --concurrency 10
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
    status TEXT NOT NULL,  -- 'pending', 'running', 'succeeded', 'failed', 'cancelled'
    stage TEXT,
    progress INTEGER DEFAULT 0,
    result JSONB,
    error JSONB,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
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
    id_type TEXT NOT NULL  -- 'uuid', 'integer', 'alphanumeric', 'complex'
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
 NULL);  -- CLZ doesn't have URLs

-- URL templates
INSERT INTO url_templates (platform, base_url, issue_url_pattern, id_type) VALUES
('gcd', 'https://www.comics.org', '/api/issue/{issue_id}/?format=json', 'integer'),
('locg', 'https://leagueofcomicgeeks.com', '/comic/{issue_id}/x-men-1', 'integer'),
('ccl', 'https://comiccollectorlive.com', '/issue/comic-books/{series_slug}/{issue}/{uuid}', 'uuid'),
('aa', 'https://atomicavenue.com', '/atomic/item/{item_id}/1/{slug}', 'integer'),
('cpg', 'https://www.comicspriceguide.com', '/titles/{series_slug}/{issue}/{issue_id}', 'alphanumeric'),
('hip', 'https://www.hipcomic.com', '/price-guide/us/marvel/comic/{series_slug}/{encoded_issue}/', 'complex'),
('clz', NULL, NULL, 'csv');  -- CLZ is CSV-only, no URLs
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

### Targeted Cache Invalidation

**No wildcard invalidation**. Instead, invalidate only specific keys:

```python
# When storing new issue
await invalidate_cache_keys([
    f"db:issue:upc:{candidate.upc}",
    f"db:issue:external_id:{platform}:{external_id}",
    f"resolution:{platform}:{external_id}",
])

# When updating issue
await invalidate_cache_keys([
    f"urls:{issue_id}",
    f"db:issue:external_id:{platform}:{external_id}",
    f"resolution:{platform}:{external_id}",
])

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

# Caching + Job Queue
redis = "^5.2"  # redis-py 5.x (includes async)
arq = "^0.26"   # Async job queue

# HTTP Client (pick ONE)
httpx = "^0.28"  # Modern async HTTP client

# HTML Parsing
selectolax = "^0.3"  # Fast HTML parser for LoCG scraping

# Retry Logic
tenacity = "^9.0"  # Retry decorators

# Fuzzy Matching
jellyfish = "^1.1"  # Jaro-Winkler similarity

# API
fastapi = "^0.115"
uvicorn = {extras = ["standard"], version = "^0.32"}

# CLI
click = "^8.1"
rich = "^13.9"

# Environment
python-dotenv = "^1.0"

# Logging
structlog = "^25.1"

[project.scripts]
cie-find = "comic_identity_engine.cli.main:cli_find"
cie-import-clz = "comic_identity_engine.cli.commands.import_clz:cli_import_clz"
cie-admin = "comic_identity_engine.cli.commands.admin:cli_admin"
cie-api = "comic_identity_engine.api.app:main"
cie-worker = "comic_identity_engine.jobs.worker:main"
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
│   │   ├── identity_resolver.py# Matching & resolution logic (detailed)
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
│   ├── jobs/                   # NEW (arq job queue)
│   │   ├── __init__.py
│   │   ├── workers.py          # Worker functions
│   │   └── worker.py           # Worker configuration
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
├── docker-compose.yml          # NEW (PostgreSQL + Redis only)
├── alembic.ini                 # NEW (Alembic config)
├── .env.example                # NEW (template)
├── IMPLEMENTATION_PLAN.md      # This file
├── AGENTS.md                   # Existing (update with new commands)
└── README.md                   # Existing (update)
```

---

## Implementation Tasks

### Phase 1: Foundation
1. Docker Compose (PostgreSQL + Redis only - no Temporal)
2. PostgreSQL schema + Alembic
3. Seed data migration
4. Copy core infrastructure from comic-web-scrapers
5. Structured logging setup

### Phase 2: Core Services
1. URL parser for all 7 platforms
2. Identity resolver service (with detailed algorithm)
3. URL builder service
4. Operations manager (AIP 151)
5. Redis cache layer (targeted invalidation)

### Phase 3: Platform Adapters (Part 1)
1. Adapt CCL from comic-scrapers to SourceAdapter
2. Adapt AA from comic-scrapers to SourceAdapter
3. Adapt CPG from comic-scrapers to SourceAdapter
4. Adapt HIP from comic-scrapers to SourceAdapter

### Phase 4: Platform Adapters (Part 2) + Job Queue
1. Extend GCD adapter with async fetching
2. Implement LoCG adapter (new scraper)
3. Implement CLZ CSV adapter (parse combined variant notation, use stdlib csv)
4. Set up arq workers with dependency injection
5. Implement worker functions (lookup_issue, lookup_batch, import_clz_csv)

### Phase 5: API + CLI
1. FastAPI application setup
2. AIP 151 endpoints (POST lookupByUrlAsync, GET operations, POST cancel)
3. AIP 236 batch endpoint (POST issues:batchLookupByUrls)
4. CLI with async/polling support
5. CLZ import command

### Phase 6: Polish
1. Comprehensive tests (unit + integration)
2. Documentation
3. OpenAPI spec generation
4. Performance tuning
5. Cache optimization

---

## Key Design Decisions

✅ **arq** for async job queue (replaces Temporal - much simpler)
✅ **PostgreSQL** in local Docker for data persistence (separate from app DB)
✅ **Redis** in local Docker for caching and arq backend (DB 0 for queue, DB 1 for cache)
✅ **httpx** as the single HTTP client (not both httpx and aiohttp)
✅ **tenacity** for retry logic with exponential backoff
✅ **jellyfish** for Jaro-Winkler fuzzy string matching
✅ **Reuse comic-web-scrapers** infrastructure (errors, cache, session management)
✅ **Reuse 4 existing platform scrapers** (CCL, AA, CPG, HIP)
✅ **CLZ CSV import** based on actual 91-column format with combined variant notation
✅ **csv module** instead of pandas for lighter weight CLZ parsing
✅ **Async/await** throughout (httpx, asyncpg, redis-py, arq)
✅ **Shared service layer** for CLI and API
✅ **No authentication** (open access)
✅ **Type hints** and Pydantic validation throughout
✅ **AIP 151** compliant long-running operations
✅ **AIP 236** compliant batch operations
✅ **Structured logging** only (no print statements)
✅ **Targeted cache invalidation** (no wildcard KEYS/SCAN)
✅ **Keep operations** for audit/analysis (no auto-deletion)
✅ **Allow retries** on failed operations (tenacity + arq)
✅ **Detailed identity resolution algorithm** with confidence scores
✅ **Fuzzy matching** for series name normalization (Jaro-Winkler)
✅ **Dependency injection** via arq worker ctx (no module-level globals)

---

## Platform Adapters Summary

| Platform | Source | Status | Notes |
|----------|--------|--------|-------|
| **GCD** | Existing | Extend | Already have GCDAdapter, add async fetching with httpx |
| **LoCG** | NEW | Implement | JavaScript-heavy site, need scraping with httpx + selectolax |
| **CCL** | comic-scrapers | Adapt | UUID-based, excellent URLs |
| **AA** | comic-scrapers | Adapt | Integer IDs, marketplace |
| **CPG** | comic-scrapers | Adapt | Alphanumeric IDs, good URLs |
| **HIP** | comic-scrapers | Adapt | Cryptic encoding (1-1 for -1) |
| **CLZ** | CSV import | NEW | Combined variant notation (-1A), use stdlib csv |

---

## Success Criteria

### Functional Requirements
- ✅ Accept URL from any of 7 platforms
- ✅ Parse URL and extract platform + ID
- ✅ Fetch issue data from source platform
- ✅ Resolve to canonical issue entity (detailed algorithm)
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
- ✅ Redis caching with targeted invalidation
- ✅ arq job queue for async orchestration
- ✅ Type hints throughout
- ✅ Comprehensive tests

### Performance Targets
- Cache hit: < 10ms
- Database lookup: < 50ms
- Platform fetch: < 30s (with retries)
- End-to-end lookup: < 60s (worst case)

---

## Changes from Initial Plan

Based on feedback from Claude Opus:

1. **Replaced Temporal with arq** - Much simpler async job queue built on asyncio and Redis
2. **Added detailed identity resolution algorithm** - Complete matching priority with confidence scores
3. **Fixed batch lookup concurrency** - Uses semaphore to limit to 10 concurrent operations
4. **Fixed dependency injection** - Uses arq worker ctx for proper DI (no module-level globals)
5. **Removed shared Postgres** - App database only (no Temporal sharing)
6. **Replaced pandas with stdlib csv** - Lighter weight for CLZ parsing
7. **Targeted cache invalidation** - No wildcard KEYS/SCAN operations
8. **Picked single HTTP client** - httpx only (removed aiohttp duplicate)
9. **Added tenacity** - Retry decorator library for exponential backoff
10. **Added jellyfish** - Jaro-Winkler similarity for fuzzy matching
11. **Removed timelines** - Using agentic workflows (not time-based)
12. **Removed UNIQUE constraint duplicate** - Fixed redundant constraint in operations table
13. **Fixed CLZ URL template** - CLZ is CSV-only, no URL pattern

---

**Plan Status**: Revised based on feedback, ready for implementation
**Current Status**: Architecture finalized, detailed algorithms specified
