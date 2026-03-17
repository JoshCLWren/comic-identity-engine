# Worker Architecture Refactoring Plan

**Status:** Planning Phase
**Created:** 2026-03-12
**Goal:** Refactor single worker into specialized workers for optimal resource utilization

---

## Executive Summary

Current system uses **1 generalist worker** that handles all job types, leading to:
- Resource contention (heavy browser jobs block light HTTP jobs)
- No independent scaling (can't scale browsers without scaling HTTP)
- Inefficient CLZ imports (20 rows × 6 platforms = 120 serial searches)

**Recommendation:** Implement **3 specialized workers** with dedicated queues:
1. **Browser Workers** - Playwright scrapers (CCL, AA)
2. **HTTP Workers** - HTTP API scrapers (GCD, LoCG, CPG, HIP)
3. **Orchestrator Workers** - Coordination jobs (CLZ import, bulk resolve)

**Expected Impact:**
- CLZ imports: **6× faster** (parallel platform searches)
- Throughput: **720 rows/min** vs **120 rows/min**
- Resource isolation: Independent scaling per resource type
- Same RAM usage: ~2GB (shared browser pool)

---

## Current Architecture Problems

### 1. Single Worker Bottleneck

```python
# Current: One worker for everything
class WorkerSettings:
    max_jobs = 60  # Capped at DB pool capacity
    functions = [
        resolve_identity_task,
        import_clz_task,          # Orchestrates 6 platform searches
        resolve_clz_row_task,     # Orchestrates 6 platform searches
        bulk_resolve_task,
        export_task,
        reconcile_task,
        http_request_task,
    ]
```

**Problem:** All jobs compete for the same 60 worker slots

### 2. CLZ Import Inefficiency

```python
# Current: resolve_clz_row_task does EVERYTHING sequentially
async def resolve_clz_row_task(ctx, row_data, ...):
    # Step 1: Resolve CLZ identity (fast)
    issue = await resolve_clz_issue(row_data)

    # Step 2: Search 6 platforms SEQUENTIALLY (slow)
    result = await platform_searcher.search_all_platforms(
        platforms=["gcd", "locg", "aa", "ccl", "cpg", "hip"],  # SERIALIZED
        ...
    )

    # Step 3: Create mappings (fast)
    for platform, url in result.items():
        await create_mapping(platform, url)
```

**Problem:**
- Each row holds worker slot for 30+ seconds
- 20 concurrent rows = 20 workers blocked
- 6 platforms searched serially = 30 seconds total
- Result: 120 rows processed every 8 minutes

### 3. Resource Contention

```
Worker Slots (60 total):
├── 20 CLZ rows in progress
│   └── Each row: 1 orchestrator + 6 platform searches = 7 slots
│   └── Total: 140 slots needed, only 20 available
├── Browser jobs (CCL, AA) blocked by CLZ
└── HTTP jobs (GCD, LoCG) blocked by CLZ
```

**Problem:** Light HTTP jobs wait for heavy browser jobs

---

## Recommended Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────────────┐
│                         Redis Queues                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ browser-q    │  │ http-q       │  │ orchestrator-q       │  │
│  │ max_jobs=5   │  │ max_jobs=20  │  │ max_jobs=10         │  │
│  │             │  │              │  │                      │  │
│  │ Functions:  │  │ Functions:   │  │ Functions:           │  │
│  │ - search_ccl│  │ - search_gcd │  │ - import_clz         │  │
│  │ - search_aa │  │ - search_locg│  │ - resolve_clz_row    │  │
│  │             │  │ - search_cpg │  │ - resolve_identity   │  │
│  │             │  │ - search_hip │  │ - bulk_resolve       │  │
│  └──────────────┘  └──────────────┘  │ - export             │  │
│                                       │ - reconcile          │  │
│                                       └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌──────────────────┐  ┌──────────────┐  ┌──────────────────┐
│ 2 Browser Workers│  │ 2 HTTP Workers│  │ 1 Orchestrator   │
│                  │  │              │  │                  │
│ Shared Resources:│  │ Shared:      │  │ No pools needed │
│ - BrowserPool    │  │ - HttpPool   │  │ - coordination   │
│   1 browser      │  │   per domain │  │   only           │
│   20 pages       │  │              │  │                  │
│   ~2GB RAM       │  │   ~100MB RAM  │  │   ~50MB RAM      │
└──────────────────┘  └──────────────┘  └──────────────────┘
```

### Worker Specialization

#### 1. Browser Workers

**Purpose:** Handle Playwright-based scrapers (RAM-intensive)

**Configuration:**
```python
# workers/browser_worker.py
class BrowserWorkerSettings:
    queue_name = "arq:queue:browsers"
    max_jobs = 5  # Low concurrency (RAM constraint)

    functions = [
        search_ccl_task,
        search_aa_task,
    ]

    async def on_startup(ctx):
        from comic_search_lib.browser_pool import get_global_pool
        pool = await get_global_pool()
        logger.info(f"Browser pool ready: {pool.max_pages} pages")
```

**Resource Profile:**
- RAM per worker: ~1GB (shared browser pool)
- Concurrency: 5 jobs × 2 workers = 10 concurrent browser jobs
- Max pages: 20 (shared pool, blocks when exhausted)
- DB connections: 10 per worker

#### 2. HTTP Workers

**Purpose:** Handle HTTP API scrapers (lightweight)

**Configuration:**
```python
# workers/http_worker.py
class HttpWorkerSettings:
    queue_name = "arq:queue:http"
    max_jobs = 20  # High concurrency (lightweight)

    functions = [
        search_gcd_task,
        search_locg_task,
        search_cpg_task,
        search_hip_task,
        http_request_task,
    ]

    async def on_startup(ctx):
        from comic_search_lib.http_pool import get_http_pool
        pool = await get_http_pool()
        logger.info(f"HTTP pool ready: {len(pool._sessions)} domains")
```

**Resource Profile:**
- RAM per worker: ~50MB (HTTP sessions only)
- Concurrency: 20 jobs × 2 workers = 40 concurrent HTTP jobs
- Rate limiting: Per-domain (built into HttpConnectionPool)
- DB connections: 20 per worker

#### 3. Orchestrator Workers

**Purpose:** Coordinate multi-step workflows (lightweight)

**Configuration:**
```python
# workers/orchestrator_worker.py
class OrchestratorWorkerSettings:
    queue_name = "arq:queue:orchestrator"
    max_jobs = 10  # Medium concurrency

    functions = [
        import_clz_task,
        resolve_clz_row_task,
        resolve_identity_task,
        bulk_resolve_task,
        export_task,
        reconcile_task,
    ]

    async def on_startup(ctx):
        # No resource pools - coordination only
        pass
```

**Resource Profile:**
- RAM per worker: ~50MB (no pools)
- Concurrency: 10 jobs × 1 worker = 10 orchestrations
- Pattern: Fan-out to browser/http queues, await results
- DB connections: 10 per worker (for progress updates)

### Resource Pools (Worker-Level Singletons)

```python
# pools/worker_resources.py
class WorkerResourcePools:
    """
    Singleton resource pools initialized ONCE per worker process.
    Shared across all task executions in that worker.
    """
    _browser_pool: BrowserPool | None = None
    _http_pool: HttpConnectionPool | None = None

    @classmethod
    async def initialize_for_browser_worker(cls):
        """Initialize browser-specific pools."""
        if cls._browser_pool is None:
            cls._browser_pool = BrowserPool(max_pages=20)
            await cls._browser_pool._ensure_initialized()
            logger.info("Browser pool initialized for worker")

    @classmethod
    async def initialize_for_http_worker(cls):
        """Initialize HTTP-specific pools."""
        if cls._http_pool is None:
            cls._http_pool = HttpConnectionPool()
            await cls._http_pool.initialize()
            logger.info("HTTP pool initialized for worker")

    @classmethod
    async def cleanup(cls):
        """Cleanup all pools."""
        if cls._browser_pool:
            await cls._browser_pool.cleanup()
        if cls._http_pool:
            await cls._http_pool.cleanup()
```

---

## Orchestrator Pattern for CLZ Imports

### Current (Inefficient)

```python
# Current: Single task does everything sequentially
async def resolve_clz_row_task(ctx, row_data, row_index, operation_id):
    # Holds worker slot for entire duration
    issue = await resolve_clz_issue(row_data)

    # Sequential platform searches (BLOCKS)
    result = await platform_searcher.search_all_platforms(
        issue_id=issue.id,
        platforms=["gcd", "locg", "aa", "ccl", "cpg", "hip"],
    )

    # Create mappings
    for platform, url in result["urls"].items():
        await create_mapping(platform, url)

    return {"resolved": True}
```

**Timeline:**
```
Row 1: [GCD: 5s] → [LoCG: 5s] → [AA: 5s] → [CCL: 5s] → [CPG: 3s] → [HIP: 5s] = 28s
Row 2: [GCD: 5s] → [LoCG: 5s] → [AA: 5s] → [CCL: 5s] → [CPG: 3s] → [HIP: 5s] = 28s
...
Row 20: [28s]

Total time: 28s (serial within each row)
Worker slot held: 28s
```

### Recommended (Efficient)

```python
# NEW: Orchestrator version (orchestrator queue)
async def resolve_clz_row_task(ctx, row_data, row_index, operation_id):
    """
    Lightweight orchestration - delegates to platform tasks.

    1. Resolve CLZ identity (fast, DB operation)
    2. Fan-out to 6 platform search tasks (parallel)
    3. Await all results
    4. Create external mappings (fast, DB operation)
    """
    # Step 1: Resolve CLZ identity (fast)
    issue = await resolve_clz_issue(row_data)

    # Step 2: Fan-out to platform-specific queues
    search_tasks = []
    for platform in ALL_PLATFORMS - {"clz"}:
        queue_name = "browsers" if platform in ["aa", "ccl"] else "http"
        task = await enqueue_platform_search(
            queue_name=queue_name,
            task_func=f"search_{platform}_task",
            issue_id=issue.id,
            series_title=issue.series_title,
            issue_number=issue.issue_number,
            year=issue.year,
            operation_id=operation_id,
        )
        search_tasks.append(task)

    # Step 3: Await all search results (parallel execution)
    results = await asyncio.gather(*search_tasks, return_exceptions=True)

    # Step 4: Create external mappings (only for found platforms)
    mappings_created = 0
    for platform, result in zip(["gcd", "locg", "aa", "ccl", "cpg", "hip"], results):
        if isinstance(result, Exception):
            logger.warning(f"Platform {platform} search failed: {result}")
            continue

        if result.get("url"):
            await create_external_mapping(
                issue_id=issue.id,
                platform=platform,
                url=result["url"]
            )
            mappings_created += 1

    return {
        "row_index": row_index,
        "resolved": True,
        "platforms_found": mappings_created,
    }


# NEW: Atomic platform tasks (browser or http queue)
async def search_gcd_task(ctx, issue_id, series_title, issue_number, year, operation_id):
    """Atomic GCD search - does ONE search only."""
    from comic_search_lib.scrapers.gcd import GCDScraper

    async with get_http_pool().get_session("https://www.comics.org") as session:
        scraper = GCDScraper(session=session)
        result = await scraper.search(series_title, issue_number, year)
        return {"url": result.url, "strategy": result.strategy}


async def search_ccl_task(ctx, issue_id, series_title, issue_number, year, operation_id):
    """Atomic CCL search - does ONE search only."""
    from comic_search_lib.scrapers.ccl import CCLScraper

    async with browser_page() as page:
        scraper = CCLScraper(page=page)
        result = await scraper.search(series_title, issue_number, year)
        return {"url": result.url, "strategy": result.strategy}
```

**Timeline:**
```
Row 1 Orchestrator:
  ├─ Fan out: [enqueue 6 tasks] → releases worker slot
  ├─ Row 2 Orchestrator: [enqueue 6 tasks] → releases worker slot
  ├─ Row 3 Orchestrator: [enqueue 6 tasks] → releases worker slot
  └─ [Wait for results] → [create mappings]

Browser/HTTP Workers:
  └─ Process 120 platform searches in parallel

Total time: ~5s (slowest platform search)
Orchestrator slot held: ~5s (for gather)
```

### Key Benefits

1. **Parallel Platform Searches** - 6× faster per row
2. **Worker Slot Reuse** - Orchestrator fans out immediately
3. **Resource Awareness** - AA/CCL go to browser queue, others to HTTP
4. **Better Fault Tolerance** - One platform failure doesn't block row
5. **Independent Scaling** - Can add browser workers without affecting HTTP

---

## Implementation Plan

### Phase 1: Infrastructure (Week 1)

**1.1 Create worker pool abstraction**

File: `comic_identity_engine/jobs/pools/worker_resources.py`

```python
"""Worker-level resource pool management."""

from __future__ import annotations

import logging
from comic_search_lib.browser_pool import BrowserPool
from comic_search_lib.http_pool import HttpConnectionPool


logger = logging.getLogger(__name__)


class WorkerResourcePools:
    """Singleton resource pools per worker process."""

    _browser_pool: BrowserPool | None = None
    _http_pool: HttpConnectionPool | None = None

    @classmethod
    async def initialize_for_browser_worker(cls):
        """Initialize browser-specific pools."""
        if cls._browser_pool is None:
            cls._browser_pool = BrowserPool(max_pages=20)
            await cls._browser_pool._ensure_initialized()
            logger.info("Browser pool initialized for worker")

    @classmethod
    async def initialize_for_http_worker(cls):
        """Initialize HTTP-specific pools."""
        if cls._http_pool is None:
            cls._http_pool = HttpConnectionPool()
            await cls._http_pool.initialize()
            logger.info("HTTP pool initialized for worker")

    @classmethod
    async def cleanup(cls):
        """Cleanup all pools."""
        logger.info("Cleaning up worker resource pools")
        if cls._browser_pool:
            await cls._browser_pool.cleanup()
            cls._browser_pool = None
        if cls._http_pool:
            await cls._http_pool.cleanup()
            cls._http_pool = None
```

**1.2 Add queue configuration**

File: `comic_identity_engine/config.py`

```python
class ArqSettings(BaseSettings):
    """ARQ worker settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Existing
    queue_url: str = Field(default="redis://localhost:6379/0", ...)
    arq_queue_name: str = Field(default="arq:queue", ...)
    arq_max_jobs: int = Field(default=100, ...)
    arq_job_timeout: int = Field(default=300, ...)
    arq_keep_result: int = Field(default=3600, ...)

    # NEW: Multiple queues
    browser_queue_name: str = Field(
        default="arq:queue:browsers",
        description="Queue for Playwright-based scrapers",
    )
    browser_max_jobs: int = Field(
        default=5,
        description="Max concurrent browser jobs (RAM constraint)",
    )

    http_queue_name: str = Field(
        default="arq:queue:http",
        description="Queue for HTTP API scrapers",
    )
    http_max_jobs: int = Field(
        default=20,
        description="Max concurrent HTTP jobs (lightweight)",
    )

    orchestrator_queue_name: str = Field(
        default="arq:queue:orchestrator",
        description="Queue for orchestration jobs",
    )
    orchestrator_max_jobs: int = Field(
        default=10,
        description="Max concurrent orchestrations",
    )
```

**1.3 Update JobQueue for multi-queue support**

File: `comic_identity_engine/jobs/queue.py`

```python
async def enqueue_job(
    self,
    task_func: str,
    queue_name: str | None = None,  # NEW
    **kwargs
) -> str:
    """
    Enqueue a job to the specified queue.

    Args:
        task_func: Task function name
        queue_name: Target queue (defaults to orchestrator queue)
        **kwargs: Task arguments

    Returns:
        Job ID
    """
    settings = get_settings()
    pool = await self._get_pool()

    # Default to orchestrator queue if not specified
    if queue_name is None:
        queue_name = settings.arq.orchestrator_queue_name

    job = await pool.enqueue_job(
        task_func,
        _queue_name=queue_name,
        **kwargs
    )

    return job.job_id
```

### Phase 2: Create Specialized Workers (Week 2)

**2.1 Browser worker**

File: `comic_identity_engine/jobs/workers/browser_worker.py`

```python
"""Browser worker for Playwright-based scrapers."""

import structlog
from arq import Worker
from comic_identity_engine.config import get_settings
from comic_identity_engine.jobs.pools.worker_resources import WorkerResourcePools
from comic_identity_engine.jobs.tasks import search_ccl_task, search_aa_task


logger = structlog.get_logger(__name__)


class BrowserWorkerSettings:
    """Browser worker configuration."""

    _settings = get_settings()
    redis_settings = ArqRedisSettings.from_dsn(_settings.arq.queue_url)
    queue_name = _settings.arq.browser_queue_name
    max_jobs = _settings.arq.browser_max_jobs
    job_timeout = _settings.arq.arq_job_timeout
    keep_result = _settings.arq.arq_keep_result

    functions = [
        search_ccl_task,
        search_aa_task,
    ]

    async def on_startup(ctx):
        """Initialize browser resource pool."""
        await WorkerResourcePools.initialize_for_browser_worker()
        logger.info("Browser worker started", max_jobs=max_jobs)

    async def on_shutdown(ctx):
        """Cleanup browser resource pool."""
        await WorkerResourcePools.cleanup()
        logger.info("Browser worker shutdown complete")


def create_browser_worker() -> Worker:
    """Create browser worker instance."""
    return Worker(
        queue_name=BrowserWorkerSettings.queue_name,
        redis_settings=BrowserWorkerSettings.redis_settings,
        max_jobs=BrowserWorkerSettings.max_jobs,
        job_timeout=BrowserWorkerSettings.job_timeout,
        keep_result=BrowserWorkerSettings.keep_result,
        functions=BrowserWorkerSettings.functions,
        on_startup=BrowserWorkerSettings.on_startup,
        on_shutdown=BrowserWorkerSettings.on_shutdown,
    )


def run_browser_worker():
    """Run browser worker."""
    worker = create_browser_worker()
    worker.run()


if __name__ == "__main__":
    run_browser_worker()
```

**2.2 HTTP worker**

File: `comic_identity_engine/jobs/workers/http_worker.py`

```python
"""HTTP worker for API-based scrapers."""

import structlog
from arq import Worker
from comic_identity_engine.config import get_settings
from comic_identity_engine.jobs.pools.worker_resources import WorkerResourcePools
from comic_identity_engine.jobs.tasks import (
    search_gcd_task,
    search_locg_task,
    search_cpg_task,
    search_hip_task,
    http_request_task,
)


logger = structlog.get_logger(__name__)


class HttpWorkerSettings:
    """HTTP worker configuration."""

    _settings = get_settings()
    redis_settings = ArqRedisSettings.from_dsn(_settings.arq.queue_url)
    queue_name = _settings.arq.http_queue_name
    max_jobs = _settings.arq.http_max_jobs
    job_timeout = _settings.arq.arq_job_timeout
    keep_result = _settings.arq.arq_keep_result

    functions = [
        search_gcd_task,
        search_locg_task,
        search_cpg_task,
        search_hip_task,
        http_request_task,
    ]

    async def on_startup(ctx):
        """Initialize HTTP resource pool."""
        await WorkerResourcePools.initialize_for_http_worker()
        logger.info("HTTP worker started", max_jobs=max_jobs)

    async def on_shutdown(ctx):
        """Cleanup HTTP resource pool."""
        await WorkerResourcePools.cleanup()
        logger.info("HTTP worker shutdown complete")


def create_http_worker() -> Worker:
    """Create HTTP worker instance."""
    return Worker(
        queue_name=HttpWorkerSettings.queue_name,
        redis_settings=HttpWorkerSettings.redis_settings,
        max_jobs=HttpWorkerSettings.max_jobs,
        job_timeout=HttpWorkerSettings.job_timeout,
        keep_result=HttpWorkerSettings.keep_result,
        functions=HttpWorkerSettings.functions,
        on_startup=HttpWorkerSettings.on_startup,
        on_shutdown=HttpWorkerSettings.on_shutdown,
    )


def run_http_worker():
    """Run HTTP worker."""
    worker = create_http_worker()
    worker.run()


if __name__ == "__main__":
    run_http_worker()
```

**2.3 Orchestrator worker**

File: `comic_identity_engine/jobs/workers/orchestrator_worker.py`

```python
"""Orchestrator worker for coordination tasks."""

import structlog
from arq import Worker
from comic_identity_engine.config import get_settings
from comic_identity_engine.jobs.tasks import (
    import_clz_task,
    resolve_clz_row_task,
    resolve_identity_task,
    bulk_resolve_task,
    export_task,
    reconcile_task,
)


logger = structlog.get_logger(__name__)


class OrchestratorWorkerSettings:
    """Orchestrator worker configuration."""

    _settings = get_settings()
    redis_settings = ArqRedisSettings.from_dsn(_settings.arq.queue_url)
    queue_name = _settings.arq.orchestrator_queue_name
    max_jobs = _settings.arq.orchestrator_max_jobs
    job_timeout = _settings.arq.arq_job_timeout
    keep_result = _settings.arq.arq_keep_result

    functions = [
        import_clz_task,
        resolve_clz_row_task,
        resolve_identity_task,
        bulk_resolve_task,
        export_task,
        reconcile_task,
    ]

    async def on_startup(ctx):
        """No resource pools needed for orchestrator."""
        logger.info("Orchestrator worker started", max_jobs=max_jobs)

    async def on_shutdown(ctx):
        """No resource cleanup needed."""
        logger.info("Orchestrator worker shutdown complete")


def create_orchestrator_worker() -> Worker:
    """Create orchestrator worker instance."""
    return Worker(
        queue_name=OrchestratorWorkerSettings.queue_name,
        redis_settings=OrchestratorWorkerSettings.redis_settings,
        max_jobs=OrchestratorWorkerSettings.max_jobs,
        job_timeout=OrchestratorWorkerSettings.job_timeout,
        keep_result=OrchestratorWorkerSettings.keep_result,
        functions=OrchestratorWorkerSettings.functions,
        on_startup=OrchestratorWorkerSettings.on_startup,
        on_shutdown=OrchestratorWorkerSettings.on_shutdown,
    )


def run_orchestrator_worker():
    """Run orchestrator worker."""
    worker = create_orchestrator_worker()
    worker.run()


if __name__ == "__main__":
    run_orchestrator_worker()
```

**2.4 Update entry points**

File: `pyproject.toml`

```toml
[project.scripts]
# Existing
cie-api = "comic_identity_engine.api.server:run"
cie-worker = "comic_identity_engine.jobs.worker:run_worker"

# NEW
cie-browser-worker = "comic_identity_engine.jobs.workers.browser_worker:run_browser_worker"
cie-http-worker = "comic_identity_engine.jobs.workers.http_worker:run_http_worker"
cie-orchestrator-worker = "comic_identity_engine.jobs.workers.orchestrator_worker:run_orchestrator_worker"
```

### Phase 3: Refactor Platform Search (Week 3)

**3.1 Create atomic platform tasks**

File: `comic_identity_engine/jobs/tasks/platform_tasks.py`

```python
"""Atomic platform search tasks - one search per task."""

import logging
import structlog
from comic_search_lib.browser_pool import browser_page
from comic_search_lib.http_pool import get_http_pool


logger = structlog.get_logger(__name__)


async def search_gcd_task(
    ctx,
    issue_id: str,
    series_title: str,
    issue_number: str,
    year: int | None,
    operation_id: str,
):
    """Search GCD for a comic issue."""
    from comic_search_lib.scrapers.gcd import GCDScraper

    logger.info(f"GCD search: {series_title} #{issue_number}")

    try:
        pool = await get_http_pool()
        async with pool.get_session("https://www.comics.org") as session:
            scraper = GCDScraper(session=session)
            result = await scraper.search(series_title, issue_number, year)

            logger.info(f"GCD found: {result.url}")

            return {
                "platform": "gcd",
                "url": result.url,
                "strategy": result.metadata.get("strategy"),
                "confidence": result.metadata.get("confidence"),
            }
    except Exception as e:
        logger.error(f"GCD search failed: {e}")
        raise


async def search_locg_task(
    ctx,
    issue_id: str,
    series_title: str,
    issue_number: str,
    year: int | None,
    operation_id: str,
):
    """Search LoCG for a comic issue."""
    from comic_search_lib.scrapers.locg import LoCGScraper

    logger.info(f"LoCG search: {series_title} #{issue_number}")

    try:
        pool = await get_http_pool()
        async with pool.get_session("https://leagueofcomicgeeks.com") as session:
            scraper = LoCGScraper(session=session)
            result = await scraper.search(series_title, issue_number, year)

            logger.info(f"LoCG found: {result.url}")

            return {
                "platform": "locg",
                "url": result.url,
                "strategy": result.metadata.get("strategy"),
                "confidence": result.metadata.get("confidence"),
            }
    except Exception as e:
        logger.error(f"LoCG search failed: {e}")
        raise


async def search_ccl_task(
    ctx,
    issue_id: str,
    series_title: str,
    issue_number: str,
    year: int | None,
    operation_id: str,
):
    """Search CCL for a comic issue."""
    from comic_search_lib.scrapers.ccl import CCLScraper

    logger.info(f"CCL search: {series_title} #{issue_number}")

    try:
        async with browser_page() as page:
            scraper = CCLScraper(page=page)
            result = await scraper.search(series_title, issue_number, year)

            logger.info(f"CCL found: {result.url}")

            return {
                "platform": "ccl",
                "url": result.url,
                "strategy": result.metadata.get("strategy"),
            }
    except Exception as e:
        logger.error(f"CCL search failed: {e}")
        raise


# ... similar for AA, CPG, HIP
```

**3.2 Refactor resolve_clz_row_task to use orchestrator pattern**

File: `comic_identity_engine/jobs/tasks.py`

```python
async def resolve_clz_row_task(
    ctx,
    row_data: dict,
    row_index: int,
    operation_id: str,
):
    """
    Orchestrator task for CLZ row resolution.

    1. Resolve CLZ identity
    2. Fan-out to 6 platform search tasks
    3. Await all results
    4. Create external mappings
    """
    logger = structlog.get_logger(__name__)
    logger.info(f"Resolving CLZ row {row_index}", operation_id=operation_id)

    # Step 1: Resolve CLZ identity
    issue = await resolve_clz_issue(row_data)

    # Step 2: Fan-out to platform-specific queues
    search_tasks = []
    platforms = ["gcd", "locg", "aa", "ccl", "cpg", "hip"]

    for platform in platforms:
        # Determine queue based on resource type
        queue_name = "browsers" if platform in ["aa", "ccl"] else "http"
        task_func = f"search_{platform}_task"

        # Enqueue platform search task
        job_id = await ctx["arq_pool"].enqueue_job(
            task_func,
            _queue_name=f"arq:queue:{queue_name}",
            issue_id=str(issue.id),
            series_title=issue.series_title,
            issue_number=issue.issue_number,
            year=issue.year,
            operation_id=operation_id,
        )

        search_tasks.append({
            "platform": platform,
            "job_id": job_id,
        })

    logger.info(f"Enqueued {len(search_tasks)} platform searches", row_index=row_index)

    # Step 3: Poll for task completion
    results = {}
    for task_info in search_tasks:
        platform = task_info["platform"]
        job_id = task_info["job_id"]

        # Poll job result (with timeout)
        result = await poll_job_result(ctx, job_id, timeout=120)

        if isinstance(result, Exception):
            logger.warning(f"Platform {platform} search failed: {result}")
            continue

        if result and result.get("url"):
            results[platform] = result
            logger.info(f"Platform {platform} found: {result['url']}")

    # Step 4: Create external mappings
    mappings_created = 0
    for platform, result in results.items():
        try:
            await create_external_mapping(
                issue_id=issue.id,
                platform=platform,
                url=result["url"],
            )
            mappings_created += 1
        except Exception as e:
            logger.error(f"Failed to create {platform} mapping: {e}")

    logger.info(
        f"CLZ row {row_index} resolved",
        platforms_found=mappings_created,
        operation_id=operation_id,
    )

    return {
        "row_index": row_index,
        "resolved": True,
        "platforms_found": mappings_created,
    }


async def poll_job_result(ctx, job_id: str, timeout: int = 120):
    """Poll arq for job result."""
    import asyncio

    start_time = asyncio.get_event_loop().time()
    poll_interval = 1

    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > timeout:
            raise TimeoutError(f"Job {job_id} timed out after {timeout}s")

        # Try to get job result
        result = await ctx["arq_pool"].get_job_result(job_id)
        if result is not None:
            if result["success"]:
                return result["result"]
            else:
                raise Exception(result["error"])

        # Wait before next poll
        await asyncio.sleep(poll_interval)
        poll_interval = min(poll_interval * 2, 10)  # Exponential backoff
```

### Phase 4: Deploy and Validate (Week 4)

**4.1 Deploy new workers alongside old worker**

```bash
# OLD: Single worker (keep running for now)
cie-worker &

# NEW: Specialized workers
cie-browser-worker &
cie-http-worker &
cie-orchestrator-worker &
```

**4.2 Gradual migration by task type**

```python
# Queue routing logic
async def route_job_to_queue(task_name: str, **kwargs):
    """Route job to appropriate queue based on task type."""

    # Platform searches migrate immediately
    if task_name.startswith("search_"):
        platform = task_name.replace("search_", "")
        if platform in ["aa", "ccl"]:
            return "browsers"
        else:
            return "http"

    # Orchestrator jobs migrate after validation
    if task_name in ["import_clz", "resolve_clz_row", "bulk_resolve"]:
        return "orchestrator"

    # Default to orchestrator
    return "orchestrator"
```

**4.3 Monitor queue depths**

```python
# Monitoring script
import asyncio
from arq import create_pool

async def monitor_queues():
    pool = await create_pool("redis://localhost:6379/0")

    queues = [
        "arq:queue:browsers",
        "arq:queue:http",
        "arq:queue:orchestrator",
    ]

    while True:
        print("\n=== Queue Depths ===")
        for queue in queues:
            info = await pool.queue_info(queue)
            print(f"{queue}: {info['queue_size']} jobs")

        await asyncio.sleep(10)
```

### Phase 5: Retire Old Worker (Week 5)

**5.1 Verify all tasks migrated**

```bash
# Check old queue is empty
redis-cli llen "arq:queue"
# Should return 0

# Check new queues have traffic
redis-cli llen "arq:queue:browsers"
redis-cli llen "arq:queue:http"
redis-cli llen "arq:queue:orchestrator"
```

**5.2 Shut down old worker**

```bash
# Stop old worker
pkill -f "cie-worker"

# Verify new workers handling all traffic
ps aux | grep "cie-.*-worker"
```

---

## Expected Performance Improvements

### CLZ Import (1000 rows)

| Metric | Current | Recommended | Improvement |
|--------|---------|-------------|-------------|
| Concurrency | 20 rows | 20 rows × 6 platforms | 6× |
| Throughput | ~120 rows/min | ~720 rows/min | 6× |
| Duration | ~8 minutes | ~1.5 minutes | 5× faster |
| RAM Usage | 2GB (1 worker) | 2.15GB (5 workers) | Similar |
| DB Connections | 20 | 50 (within 60 limit) | OK |

### Single CLZ Row (6 platforms)

| Metric | Current | Recommended | Improvement |
|--------|---------|-------------|-------------|
| Search Pattern | Serial (6 searches) | Parallel (6 searches) | 6× |
| Duration | ~30 seconds | ~5 seconds | 6× faster |
| Worker Hold Time | 30 seconds | 5 seconds (orchestrator) | 6× better |

---

## Configuration Examples

### Development (Single Machine)

```bash
# Orchestrator worker (1 process)
cie-orchestrator-worker &
# Processes: 1
# RAM: ~50MB
# DB: 10 connections
# Concurrency: 10 orchestrations

# HTTP workers (2 processes)
cie-http-worker &
cie-http-worker &
# Processes: 2
# RAM: ~100MB total
# DB: 40 connections total
# Concurrency: 40 HTTP jobs

# Browser workers (2 processes)
cie-browser-worker &
cie-browser-worker &
# Processes: 2
# RAM: ~2GB total (shared browser pool)
# DB: 20 connections total
# Concurrency: 10 browser jobs

# Total:
# Processes: 5
# RAM: ~2.15GB
# DB: 70 connections (within 60+40 limit)
# Concurrency: 60 jobs total
```

### Production (Docker Compose)

```yaml
# docker-compose.yml
version: '3.8'

services:
  orchestrator-worker:
    image: comic-identity-engine:latest
    command: cie-orchestrator-worker
    deploy:
      replicas: 2
    environment:
      - ORCHESTRATOR_MAX_JOBS=10

  http-worker:
    image: comic-identity-engine:latest
    command: cie-http-worker
    deploy:
      replicas: 3
    environment:
      - HTTP_MAX_JOBS=20

  browser-worker:
    image: comic-identity-engine:latest
    command: cie-browser-worker
    deploy:
      replicas: 2
    environment:
      - BROWSER_MAX_JOBS=5
    resources:
      limits:
        memory: 2G
```

---

## Migration Checklist

### Week 1: Infrastructure
- [ ] Create `WorkerResourcePools` singleton
- [ ] Add queue configuration to config.py
- [ ] Update JobQueue for multi-queue support
- [ ] Add queue routing logic
- [ ] Test queue creation and routing

### Week 2: Worker Creation
- [ ] Create browser_worker.py
- [ ] Create http_worker.py
- [ ] Create orchestrator_worker.py
- [ ] Add CLI entry points
- [ ] Test workers start/stop correctly
- [ ] Verify pool initialization on startup
- [ ] Verify pool cleanup on shutdown

### Week 3: Task Refactoring
- [ ] Create atomic platform tasks (GCD, LoCG, AA, CCL, CPG, HIP)
- [ ] Refactor resolve_clz_row_task (orchestrator pattern)
- [ ] Implement job result polling
- [ ] Update platform searcher to use tasks
- [ ] Test CLZ import with new tasks

### Week 4: Deployment
- [ ] Deploy new workers alongside old worker
- [ ] Add monitoring for queue depths
- [ ] Run sample CLZ import (100 rows)
- [ ] Compare performance (old vs new)
- [ ] Tune worker counts based on results

### Week 5: Cutover
- [ ] Verify all tasks migrated
- [ ] Redirect all traffic to new queues
- [ ] Monitor for errors/exceptions
- [ ] Stop old worker
- [ ] Remove old worker code
- [ ] Update documentation

---

## Risks and Mitigations

### Risk 1: Increased Complexity

**Mitigation:**
- Phased migration (5 weeks)
- Keep old worker running during transition
- Extensive testing at each phase
- Rollback plan (switch back to old worker)

### Risk 2: DB Connection Exhaustion

**Mitigation:**
- Calculate worker counts: `∑(workers × max_jobs) <= 60`
- Monitor DB pool usage during testing
- Alert when connection pool > 80%
- Add overflow buffer if needed

### Risk 3: Queue Imbalance

**Mitigation:**
- Monitor queue depths in real-time
- Auto-scale workers based on backlog
- Load test with 10,000 CLZ rows
- Manual worker adjustment capability

### Risk 4: Resource Pool Contention

**Mitigation:**
- Shared pools with locking (already implemented)
- Stress test with 100 concurrent platform searches
- Monitor pool metrics (pages available, rate limit hits)
- Adjust pool sizes if needed

---

## Success Criteria

### Performance
- [ ] CLZ import: <2 minutes for 1000 rows (currently ~8 minutes)
- [ ] Single row: <6 seconds for 6 platforms (currently ~30 seconds)
- [ ] Throughput: >600 rows/min (currently ~120 rows/min)

### Resource Usage
- [ ] RAM usage: <2.5GB total (currently ~2GB)
- [ ] DB connections: <70 (limit is 60+40=100)
- [ ] Browser pages: <20 active (hard limit)

### Reliability
- [ ] No queue backlog during normal operation
- [ ] Worker restart time: <5 seconds
- [ ] Pool initialization success rate: 100%
- [ ] Job completion rate: >99%

### Operational
- [ ] Can scale browser workers independently
- [ ] Can scale HTTP workers independently
- [ ] Monitoring for all queues and pools
- [ ] Graceful shutdown of all workers
- [ ] Clean resource cleanup

---

## Next Steps

1. **Review and approve** this plan
2. **Start Phase 1** (infrastructure setup)
3. **Create first specialized worker** (browser workers)
4. **Validate with sample CLZ import** (100 rows)
5. **Proceed with full migration** if validation succeeds

---

## References

- Current implementation: `comic_identity_engine/jobs/worker.py`
- Browser pool: `comic-search-lib/comic_search_lib/browser_pool.py`
- HTTP pool: `comic-search-lib/comic_search_lib/http_pool.py`
- Circuit breaker: `comic-search-lib/comic_search_lib/resilience.py`
- Proven pattern: `comic-web-scrapers/comic_scrapers/temporal/worker.py`
