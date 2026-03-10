# Master Implementation Plan: HTTP Request-Level Task Granularity
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


## Overview

This document provides a complete execution plan for refactoring the Comic Identity Engine to achieve maximum parallelism by making **individual HTTP requests** the atomic task unit.

**Current state:** One giant task processes entire CSV serially
**Target state:** 93,600-218,400 independent HTTP request tasks, all workers processing continuously

## Prerequisites

**Read these documents first (in order):**

1. **CLZ_IMPORT_REDESIGN.md** - Original redesign plan (CLZ Core ComicID, identity resolution pipeline)
2. **CLZ_IMPORT_COMPLETE.md** - Current implementation summary
3. **CONCURRENCY_ANALYSIS.md** - Current architecture problems and why it's serial
4. **PLATFORM_SEARCH_GRANULARITY_ANALYSIS.md** - Detailed breakdown of platform search operations

**Context from these documents:**
- CLZ imports should use Core ComicID as universal identifier
- Identity resolution pipeline creates external mappings
- Cross-platform search finds comics on GCD, LoCG, CCL, AA, CPG, HIP
- Current implementation processes rows serially (one worker, others idle)
- True atomic unit = one HTTP request + parse operation

## Problem Statement

**Current Architecture (SERIAL):**
```
CSV → 1 import_clz_task → Worker 1 processes 5,200 rows serially
                            Workers 2-10: IDLE for hours

Concurrency: 6 platform searches (only 1 row at a time)
Time: 2-4 hours for 5,200 rows
```

**Desired Architecture (MASSIVELY PARALLEL):**
```
CSV → 93,600 HTTP request tasks → All 10 workers processing continuously

Worker 1: req → parse → req → parse → req → parse
Worker 2: req → parse → req → parse → req → parse
Worker 3: req → parse → req → parse → req → parse
...

Concurrency: 10 workers × continuous requests
Time: 15-30 minutes for 5,200 rows
```

## Implementation Plan

### Phase 1: Create HTTP Request Task Infrastructure

**Objective:** Build foundation for HTTP request-level tasks

#### Task 1.1: Create HTTP Request Task

**File:** `comic_identity_engine/jobs/tasks.py`

**Create new task:**
```python
async def http_request_task(
    ctx: dict[str, Any],
    platform: str,
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: dict[str, Any] | None = None,
    operation_id: str,
) -> dict[str, Any]:
    """Execute a single HTTP request as an independent task.

    This is the atomic task unit - one HTTP request to a platform.

    Args:
        ctx: ARQ context
        platform: Platform code (gcd, locg, ccl, aa, cpg, hip)
        url: URL to request
        method: HTTP method (GET, POST)
        headers: HTTP headers
        data: Request body data
        operation_id: Operation UUID for tracking

    Returns:
        {
            "url": str,
            "status_code": int,
            "content": str,  # HTML/JSON response
            "elapsed_ms": int,
            "success": bool,
            "error": str | None
        }
    """
    async with AsyncSessionLocal() as session:
        try:
            import httpx
            import time

            from comic_identity_engine.core.http_client import HttpClient
            from comic_identity_engine.services.operations import OperationsManager

            operation_uuid = uuid.UUID(operation_id)
            operations_manager = OperationsManager(session)

            # Mark operation running
            await operations_manager.mark_running(operation_uuid)

            logger.info(
                "HTTP request task",
                operation_id=operation_id,
                platform=platform,
                url=url,
                method=method,
            )

            # Execute HTTP request
            http_client = HttpClient(platform=platform, verify_ssl=platform != "ccl")
            start_time = time.time()

            try:
                if method.upper() == "GET":
                    response = await http_client.client.get(url, headers=headers, timeout=30.0)
                elif method.upper() == "POST":
                    response = await http_client.client.post(url, headers=headers, json=data, timeout=30.0)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                elapsed_ms = int((time.time() - start_time) * 1000)
                content = response.text

                result = {
                    "url": url,
                    "status_code": response.status_code,
                    "content": content,
                    "elapsed_ms": elapsed_ms,
                    "success": 200 <= response.status_code < 300,
                    "error": None,
                }

                logger.info(
                    "HTTP request succeeded",
                    operation_id=operation_id,
                    url=url,
                    status_code=response.status_code,
                    elapsed_ms=elapsed_ms,
                )

                await operations_manager.mark_completed(operation_uuid, result)
                await session.commit()

                return result

            except httpx.HTTPError as e:
                elapsed_ms = int((time.time() - start_time) * 1000)
                error_msg = f"HTTP request failed: {e}"

                result = {
                    "url": url,
                    "status_code": None,
                    "content": None,
                    "elapsed_ms": elapsed_ms,
                    "success": False,
                    "error": error_msg,
                }

                logger.error(
                    "HTTP request failed",
                    operation_id=operation_id,
                    url=url,
                    error=str(e),
                    elapsed_ms=elapsed_ms,
                )

                await operations_manager.mark_failed(operation_uuid, error_msg)
                await session.commit()

                return result

        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error("HTTP request task error", operation_id=operation_id, error=str(e))
            await operations_manager.mark_failed(operation_uuid, error_msg)
            await session.commit()
            return {
                "url": url,
                "success": False,
                "error": error_msg,
            }
```

**Acceptance Criteria:**
- Task executes single HTTP request
- Returns status code, content, timing
- Handles errors gracefully
- Updates operation status

#### Task 1.2: Add HTTP Request to Queue

**File:** `comic_identity_engine/jobs/queue.py`

**Add method to JobQueue class:**
```python
async def enqueue_http_request(
    self,
    platform: str,
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: dict[str, Any] | None = None,
    operation_id: uuid.UUID | None = None,
) -> Job:
    """Enqueue a single HTTP request task.

    Args:
        platform: Platform code
        url: URL to request
        method: HTTP method
        headers: HTTP headers
        data: Request body
        operation_id: Operation UUID (auto-generated if None)

    Returns:
        arq Job instance
    """
    pool = await self._get_pool()

    if operation_id is None:
        operation_id = uuid.uuid4()

    logger.info(
        "Enqueueing HTTP request task",
        platform=platform,
        url=url,
        operation_id=str(operation_id),
    )

    return await pool.enqueue_job(
        "http_request_task",
        platform=platform,
        url=url,
        method=method,
        headers=headers,
        data=data,
        operation_id=str(operation_id),
    )
```

**Acceptance Criteria:**
- Method enqueues http_request_task
- Auto-generates operation_id if not provided
- Logs enqueue operation

---

### Phase 2: Refactor Platform Adapters

**Objective:** Make adapters enqueue HTTP requests instead of executing them directly

#### Task 2.1: Create Async HTTP Request Wrapper

**File:** `comic_identity_engine/core/http_client.py` or new file `comic_identity_engine/core/async_http.py`

**Create async HTTP client that uses task queue:**
```python
from comic_identity_engine.jobs.queue import JobQueue
from comic_identity_engine.services.operations import OperationsManager

class AsyncHttpExecutor:
    """Execute HTTP requests via task queue for maximum parallelism."""

    def __init__(self, queue: JobQueue, operations_manager: OperationsManager):
        self.queue = queue
        self.operations_manager = operations_manager

    async def get(
        self,
        platform: str,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """Execute GET request via task queue.

        Args:
            platform: Platform code
            url: URL to request
            headers: HTTP headers
            timeout: Max wait time (seconds)

        Returns:
            Response dict with status_code, content, elapsed_ms
        """
        from comic_identity_engine.services.operations import OperationsManager
        from comic_identity_engine.database.connection import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            operations_manager = OperationsManager(session)

            # Create operation for tracking
            operation = await operations_manager.create_operation(
                operation_type="http_request",
                input_data={"platform": platform, "url": url}
            )
            await session.commit()

            # Enqueue HTTP request task
            job = await self.queue.enqueue_http_request(
                platform=platform,
                url=url,
                method="GET",
                headers=headers,
                operation_id=operation.id,
            )

            # Poll for completion
            import time
            start_time = time.time()
            poll_interval = 0.1

            while time.time() - start_time < timeout:
                result_op = await operations_manager.get_operation(operation.id)

                if result_op.status in ("completed", "failed"):
                    if result_op.result:
                        return result_op.result
                    elif result_op.error_message:
                        raise Exception(result_op.error_message)
                    else:
                        raise Exception(f"HTTP request failed: {result_op.status}")

                time.sleep(poll_interval)

            raise TimeoutError(f"HTTP request timeout after {timeout}s")

    async def post(
        self,
        platform: str,
        url: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """Execute POST request via task queue.

        Args:
            platform: Platform code
            url: URL to request
            json: Request body
            headers: HTTP headers
            timeout: Max wait time (seconds)

        Returns:
            Response dict with status_code, content, elapsed_ms
        """
        # Similar to get() but uses POST
        ...
```

**Acceptance Criteria:**
- Enqueues HTTP request tasks
- Polls for completion
- Returns response data
- Handles timeouts and errors

#### Task 2.2: Update Platform Adapters

**Files:** `comic_identity_engine/adapters/gcd.py`, `locg.py`, `ccl.py`, `aa.py`, `cpg.py`, `hip.py`

**For each adapter:**

1. **Replace synchronous HTTP calls with task-based async calls**

Example for GCDAdapter:
```python
# Before (synchronous):
response = self._http_client.get(url)

# After (task-based):
result = await self._async_http_executor.get("gcd", url)
status_code = result["status_code"]
content = result["content"]
```

2. **Update adapter initialization:**

```python
# Add parameter to __init__
def __init__(self, async_http_executor: AsyncHttpExecutor | None = None):
    self._async_http_executor = async_http_executor
    if not async_http_executor:
        # Fallback to synchronous HTTP client
        from comic_identity_engine.core.http_client import HttpClient
        self._http_client = HttpClient(platform="gcd")
```

**Acceptance Criteria:**
- All HTTP requests go through task queue
- Adapters work with both sync and async executors
- Backward compatible (fallback to sync if executor not provided)

---

### Phase 3: Redesign Platform Search

**Objective:** Make platform search enqueue individual HTTP request tasks

#### Task 3.1: Refactor PlatformSearcher

**File:** `comic_identity_engine/services/platform_searcher.py` (or create it)

**Create new PlatformSearcher that enqueues HTTP tasks:**
```python
class PlatformSearcher:
    """Search for issues across all platforms using task queue."""

    def __init__(
        self,
        session: AsyncSession,
        queue: JobQueue,
        operations_manager: OperationsManager,
    ):
        self.session = session
        self.queue = queue
        self.operations_manager = operations_manager
        self.async_http = AsyncHttpExecutor(queue, operations_manager)

    async def search_single_platform(
        self,
        platform: str,
        series_title: str,
        issue_number: str,
        year: int | None,
        operation_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Search a single platform by enqueuing HTTP request tasks.

        This replaces the old search_all_platforms approach with task-based parallelism.

        Args:
            platform: Platform code
            series_title: Series to search
            issue_number: Issue number
            year: Publication year
            operation_id: Parent operation ID

        Returns:
            {
                "platform": str,
                "found": bool,
                "url": str | None,
                "source_issue_id": str | None,
                "strategies_tried": list[str],
                "total_requests": int,
                "elapsed_ms": int,
            }
        """
        import time
        from comic_identity_engine.adapters import get_adapter

        start_time = time.time()
        adapter = get_adapter(platform)

        # Strategy 1: Exact search
        try:
            exact_url = adapter._build_search_url(series_title, issue_number, year)
            result = await self.async_http.get(platform, exact_url)

            if result["success"]:
                parsed = adapter._parse_search_result(result["content"])
                if parsed:
                    return {
                        "platform": platform,
                        "found": True,
                        "url": exact_url,
                        "source_issue_id": parsed.get("id"),
                        "strategies_tried": ["exact"],
                        "total_requests": 1,
                        "elapsed_ms": int((time.time() - start_time) * 1000),
                    }
        except Exception as e:
            logger.warning(f"Exact search failed for {platform}: {e}")

        # Strategy 2: Fuzzy search (additional HTTP request)
        # Strategy 3: Alternative search (additional HTTP request)
        # ...

        return {
            "platform": platform,
            "found": False,
            "url": None,
            "source_issue_id": None,
            "strategies_tried": ["exact", "fuzzy"],
            "total_requests": 2,
            "elapsed_ms": int((time.time() - start_time) * 1000),
        }

    async def search_all_platforms(
        self,
        issue_id: uuid.UUID,
        series_title: str,
        issue_number: str,
        year: int | None,
        publisher: str | None,
        operation_id: uuid.UUID,
        source_platform: str,
    ) -> dict[str, Any]:
        """Search all platforms in parallel using task queue.

        This creates 6 concurrent search tasks (one per platform).
        Each search task may enqueue multiple HTTP request tasks.

        Args:
            issue_id: Canonical issue UUID
            series_title: Series title
            issue_number: Issue number
            year: Publication year
            publisher: Publisher name
            operation_id: Parent operation ID
            source_platform: Original platform (skip searching it again)

        Returns:
            {
                "urls": {platform: url},
                "status": {platform: status},
                "events": [...],
            }
        """
        import asyncio

        platforms = ["gcd", "locg", "ccl", "aa", "cpg", "hip"]

        # Skip source platform
        if source_platform in platforms:
            platforms.remove(source_platform)

        # Create concurrent search tasks (one per platform)
        search_tasks = [
            self.search_single_platform(
                platform=platform,
                series_title=series_title,
                issue_number=issue_number,
                year=year,
                operation_id=operation_id,
            )
            for platform in platforms
        ]

        # Execute all platform searches concurrently
        results = await asyncio.gather(*search_tasks, return_exceptions=True)

        # Aggregate results
        urls = {}
        status = {}
        events = []

        for platform, result in zip(platforms, results):
            if isinstance(result, Exception):
                status[platform] = "failed"
                events.append({
                    "platform": platform,
                    "status": "failed",
                    "error": str(result),
                })
            elif result["found"]:
                urls[platform] = result["url"]
                status[platform] = "found"
                events.append({
                    "platform": platform,
                    "status": "found",
                    "source_issue_id": result["source_issue_id"],
                })
            else:
                status[platform] = "not_found"
                events.append({
                    "platform": platform,
                    "status": "not_found",
                    "strategies_tried": result["strategies_tried"],
                })

        return {
            "urls": urls,
            "status": status,
            "events": events,
        }
```

**Acceptance Criteria:**
- Each platform search enqueues HTTP request tasks
- Multiple platforms search concurrently
- Returns aggregated results
- Handles per-platform errors gracefully

---

### Phase 4: Redesign CLZ Import

**Objective:** Make CLZ import enqueue row-level tasks that use HTTP request tasks

#### Task 4.1: Replace import_clz_task

**File:** `comic_identity_engine/jobs/tasks.py`

**Replace current serial import_clz_task with parallel version:**
```python
async def import_clz_task(
    ctx: dict[str, Any],
    csv_path: str,
    operation_id: str,
) -> dict[str, Any]:
    """Import CLZ CSV by enqueuing row-level resolution tasks.

    This task orchestrates the import but doesn't process rows itself.
    Each row becomes a separate resolution task that uses HTTP request tasks.

    Args:
        ctx: ARQ context
        csv_path: Path to CLZ CSV
        operation_id: Parent operation ID

    Returns:
        Aggregated results from all row tasks
    """
    async with AsyncSessionLocal() as session:
        operation_uuid = uuid.UUID(operation_id)
        operations_manager = OperationsManager(session)
        queue = JobQueue()

        await operations_manager.mark_running(operation_uuid)

        adapter = CLZAdapter()
        rows = adapter.load_csv_from_file(csv_path)

        logger.info(
            "Starting CLZ import",
            operation_id=operation_id,
            total_rows=len(rows),
        )

        # Enqueue one task per row
        row_tasks = []
        for idx, row in enumerate(rows):
            try:
                candidate = adapter.fetch_issue_from_csv_row(row)

                # Create operation for this row
                row_operation = await operations_manager.create_operation(
                    operation_type="resolve_clz_row",
                    input_data={
                        "row_index": idx,
                        "source_issue_id": candidate.source_issue_id,
                        "series_title": candidate.series_title,
                    }
                )

                # Enqueue resolution task for this row
                job = await queue.enqueue_resolve_clz_row(
                    candidate_data={
                        "source": "clz",
                        "source_issue_id": candidate.source_issue_id,
                        "source_series_id": candidate.source_series_id,
                        "series_title": candidate.series_title,
                        "series_start_year": candidate.series_start_year,
                        "issue_number": candidate.issue_number,
                        "variant_suffix": candidate.variant_suffix,
                        "upc": candidate.upc,
                        "cover_date": candidate.cover_date,
                    },
                    operation_id=row_operation.id,
                )

                row_tasks.append({
                    "row_index": idx,
                    "operation_id": str(row_operation.id),
                    "job_id": str(job.job_id),
                })

            except Exception as e:
                logger.error(f"Failed to enqueue row {idx}: {e}")

        # Wait for all row tasks to complete
        # (This could be polling, or we could return immediately)
        resolved = 0
        failed = 0

        for task_info in row_tasks:
            row_operation_id = uuid.UUID(task_info["operation_id"])

            # Poll for completion
            max_wait = 600  # 10 minutes per row
            import time
            start_time = time.time()

            while time.time() - start_time < max_wait:
                result_op = await operations_manager.get_operation(row_operation_id)

                if result_op.status == "completed":
                    resolved += 1
                    break
                elif result_op.status == "failed":
                    failed += 1
                    break

                time.sleep(1)

        result_dict = {
            "total_rows": len(rows),
            "resolved": resolved,
            "failed": failed,
            "summary": f"Enqueued {len(rows)} row tasks: {resolved} resolved, {failed} failed",
        }

        await operations_manager.mark_completed(operation_uuid, result_dict)
        await session.commit()

        return result_dict
```

**Acceptance Criteria:**
- Orchestrates import but doesn't process rows
- Enqueues one task per row
- Waits for all row tasks to complete
- Returns aggregated results

#### Task 4.2: Create resolve_clz_row Task

**File:** `comic_identity_engine/jobs/tasks.py`

**Create new task:**
```python
async def resolve_clz_row_task(
    ctx: dict[str, Any],
    candidate_data: dict[str, Any],
    operation_id: str,
) -> dict[str, Any]:
    """Resolve a single CLZ CSV row through identity resolution.

    This task:
    1. Checks for existing CLZ mapping
    2. If not found, resolves via IdentityResolver
    3. Creates CLZ external mapping
    4. Runs cross-platform search (enqueues HTTP request tasks)

    Args:
        ctx: ARQ context
        candidate_data: IssueCandidate data from CSV row
        operation_id: Operation UUID

    Returns:
        Resolution result with platform mappings
    """
    async with AsyncSessionLocal() as session:
        operation_uuid = uuid.UUID(operation_id)
        operations_manager = OperationsManager(session)
        mapping_repo = ExternalMappingRepository(session)

        await operations_manager.mark_running(operation_uuid)

        try:
            # Check for existing mapping
            source_issue_id = candidate_data["source_issue_id"]
            existing = await mapping_repo.find_by_source("clz", source_issue_id)

            if existing:
                logger.info(
                    "Reusing existing CLZ mapping",
                    operation_id=operation_id,
                    source_issue_id=source_issue_id,
                    issue_id=str(existing.issue_id),
                )

                result = {
                    "canonical_uuid": str(existing.issue_id),
                    "found_existing": True,
                    "platform_urls": {},
                }

                await operations_manager.mark_completed(operation_uuid, result)
                await session.commit()

                return result

            # Resolve through IdentityResolver
            from comic_identity_engine.services.identity_resolver import IdentityResolver
            from comic_identity_engine.services.url_parser import ParsedUrl

            resolver = IdentityResolver(session)

            parsed_url = ParsedUrl(
                platform="clz",
                source_issue_id=candidate_data["source_issue_id"],
                source_series_id=candidate_data.get("source_series_id"),
            )

            resolve_result = await resolver.resolve_issue(
                parsed_url=parsed_url,
                upc=candidate_data.get("upc"),
                series_title=candidate_data["series_title"],
                series_start_year=candidate_data.get("series_start_year"),
                issue_number=candidate_data["issue_number"],
                cover_date=candidate_data.get("cover_date"),
            )

            if not resolve_result.issue_id:
                raise Exception("Identity resolution failed")

            # Create external mapping
            await _ensure_source_mapping(
                mapping_repo=mapping_repo,
                issue_id=resolve_result.issue_id,
                source="clz",
                source_issue_id=source_issue_id,
                source_series_id=candidate_data.get("source_series_id"),
            )

            # Run cross-platform search (enqueues HTTP request tasks)
            from comic_identity_engine.services.platform_searcher import PlatformSearcher

            searcher = PlatformSearcher(session, JobQueue(), operations_manager)

            cross_platform_result = await searcher.search_all_platforms(
                issue_id=resolve_result.issue_id,
                series_title=candidate_data["series_title"],
                issue_number=candidate_data["issue_number"],
                year=candidate_data.get("series_start_year"),
                publisher=None,
                operation_id=operation_uuid,
                source_platform="clz",
            )

            result = {
                "canonical_uuid": str(resolve_result.issue_id),
                "found_existing": False,
                "platform_urls": cross_platform_result["urls"],
                "confidence": resolve_result.best_match.overall_confidence if resolve_result.best_match else 0.0,
            }

            await operations_manager.mark_completed(operation_uuid, result)
            await session.commit()

            return result

        except Exception as e:
            error_msg = f"Failed to resolve CLZ row: {e}"
            logger.error(error_msg, operation_id=operation_id)
            await operations_manager.mark_failed(operation_uuid, error_msg)
            await session.commit()

            return {
                "error": error_msg,
            }
```

**Acceptance Criteria:**
- Resolves single CLZ row
- Uses IdentityResolver
- Creates external mapping
- Runs cross-platform search via PlatformSearcher
- Handles errors gracefully

---

### Phase 5: Update CLI

**Objective:** CLI remains unchanged (should work with new task structure)

#### Task 5.1: Verify CLI Compatibility

**File:** `comic_identity_engine/cli/commands/import_clz.py`

**No changes needed** - CLI already:
- Submits to `/api/v1/import/clz`
- Polls for operation completion
- Displays results

**Verify:**
- Response format matches expected fields
- Progress tracking works
- Error handling works

---

### Phase 6: Queue Configuration

**Objective:** Configure ARQ for high task throughput

#### Task 6.1: Optimize Worker Settings

**File:** Worker configuration or environment variables

**Settings:**
```python
# arq settings
ARQ_QUEUE_SIZE = 10000  # Allow 10k tasks in queue
ARQ_MAX_JOBS = 100  # Process 100 tasks per poll
ARQ_POLL_INTERVAL = 0.1  # Poll every 100ms
```

**Acceptance Criteria:**
- Queue handles 100k+ tasks
- Workers process tasks rapidly
- No queue overflow

---

## Testing Strategy

### Unit Tests

1. **http_request_task**: Test single HTTP request execution
2. **AsyncHttpExecutor**: Test task enqueueing and polling
3. **resolve_clz_row_task**: Test single row resolution
4. **PlatformSearcher**: Test concurrent platform searches

### Integration Tests

1. **Small CSV (10 rows):** Verify all tasks complete
2. **Medium CSV (100 rows):** Verify parallelism
3. **Error handling:** Test failed HTTP requests, timeouts

### Load Tests

1. **Full CSV (5,200 rows):**
   - Monitor worker utilization
   - Measure total time
   - Verify queue depth

### Performance Metrics

**Before (current serial):**
- Time: 2-4 hours
- Worker utilization: 10% (1 of 10 workers)

**After (target):**
- Time: 15-30 minutes
- Worker utilization: 90-100% (all workers busy)

---

## Rollout Plan

### Step 1: Deploy New Tasks (Phase 1-2)
- Deploy http_request_task
- Deploy queue updates
- Test with manual HTTP request enqueue

### Step 2: Update Adapters (Phase 3)
- Update one adapter (e.g., GCD)
- Test CLZ import with only GCD platform
- Verify HTTP request tasks created
- Roll out to remaining adapters

### Step 3: Redesign CLZ Import (Phase 4)
- Replace import_clz_task
- Add resolve_clz_row_task
- Test with small CSV
- Scale to full CSV

### Step 4: Monitor and Optimize (Phase 5-6)
- Monitor queue depth
- Monitor worker utilization
- Tune queue settings
- Add rate limiting if needed

---

## Success Criteria

✅ **HTTP requests are atomic tasks** in queue
✅ **All 10 workers** processing continuously
✅ **93,600-218,400 tasks** enqueued for 5,200-row CSV
✅ **Import time reduced** from 2-4 hours to 15-30 minutes
✅ **Worker utilization** at 90-100%
✅ **Error handling** graceful (per-request failures don't stop import)
✅ **Observable** (progress per HTTP request)

---

## Files to Modify

### New Files
- `comic_identity_engine/core/async_http.py` - AsyncHttpExecutor
- `comic_identity_engine/services/platform_searcher.py` - Task-based PlatformSearcher

### Modified Files
- `comic_identity_engine/jobs/tasks.py`
  - Add http_request_task
  - Add resolve_clz_row_task
  - Replace import_clz_task
- `comic_identity_engine/jobs/queue.py`
  - Add enqueue_http_request
  - Add enqueue_resolve_clz_row
- `comic_identity_engine/adapters/*.py`
  - Update to use AsyncHttpExecutor
- Worker configuration

---

## Dependencies and Order

**Phase 1 must complete first:**
- http_request_task foundation
- Queue infrastructure

**Phase 2 enables Phase 3:**
- Adapters must use AsyncHttpExecutor
- Before PlatformSearcher can use them

**Phase 3 enables Phase 4:**
- PlatformSearcher must be task-based
- Before CLZ import can use it

**Phases 5-6:**
- Can proceed in parallel with Phase 4

---

## Monitoring and Observability

### Key Metrics

1. **Queue depth:** Number of pending tasks
2. **Worker utilization:** % of workers processing tasks
3. **Task throughput:** Tasks/second
4. **HTTP request latency:** P50, P95, P99
5. **Error rate:** % of failed HTTP requests

### Logs

Each task should log:
- Enqueue time
- Start time
- Completion time
- Duration
- Success/failure
- Error details

### Operations Table

Query to monitor import progress:
```sql
SELECT
    operation_type,
    status,
    COUNT(*),
    AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) as avg_duration_sec
FROM operations
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY operation_type, status;
```

---

## Risk Mitigation

### Risk 1: Queue Overload

**Mitigation:**
- Set maximum queue size
- Implement backpressure
- Monitor queue depth
- Throttle task enqueue if queue full

### Risk 2: Worker Exhaustion

**Mitigation:**
- Increase worker count if needed
- Implement task priorities
- Set timeouts on HTTP requests
- Circuit breaker for failing platforms

### Risk 3: Database Connection Pool

**Mitigation:**
- Increase pool size
- Use connection pooling efficiently
- Monitor connection usage
- Implement retry logic for DB errors

### Risk 4: Rate Limiting

**Mitigation:**
- Respect platform rate limits
- Implement exponential backoff
- Queue tasks with delays
- Monitor platform response times

---

## Next Steps

1. **Review this plan** with all referenced documents
2. **Ask questions** if anything unclear
3. **Assign implementation** to agent(s)
4. **Test incrementally** (Phase by Phase)
5. **Monitor metrics** during rollout
6. **Iterate** based on results

---

## Questions for Agent

Before starting implementation, the agent should:

1. **Confirm understanding** of HTTP request-level task granularity
2. **Verify** all referenced documents have been read
3. **Clarify** any ambiguities in the plan
4. **Suggest improvements** if better approaches exist
5. **Identify risks** not mentioned in this plan

---

## Document References

This plan integrates the following documents:

1. **CLZ_IMPORT_REDESIGN.md** - Original redesign context
2. **CLZ_IMPORT_COMPLETE.md** - Current implementation state
3. **CONCURRENCY_ANALYSIS.md** - Serial vs parallel architecture
4. **PLATFORM_SEARCH_GRANULARITY_ANALYSIS.md** - Detailed operation breakdown

**Read order:** Start with CONCURRENCY_ANALYSIS.md, then PLATFORM_SEARCH_GRANULARITY_ANALYSIS.md, then this document.

---

## Conclusion

This plan transforms the Comic Identity Engine from serial row processing to massively parallel HTTP request processing. By making individual HTTP requests the atomic task unit, we achieve:

- **10x worker utilization** (from 10% to 100%)
- **4-8x speed improvement** (from 2-4 hours to 15-30 minutes)
- **Better observability** (progress per HTTP request)
- **Graceful error handling** (per-request failures don't stop import)
- **Scalable architecture** (easy to add more workers)

The key insight: **the smallest iterable unit is one HTTP request**, not one row or one platform search.
