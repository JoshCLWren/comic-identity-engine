# Fix Plan: Comic Identity Engine

**Date**: 2026-03-16
**Test Baseline**: 1,331 tests; 41 failed, 21 errors, 1,267 passed, 2 skipped
**Last Updated**: 2026-03-16 (corrected - consolidation incomplete)

> **⚠️ CONSOLIDATION STATUS** — See `../CONSOLIDATION_PLAN.md`
>
> Cross-project consolidation has COMPLETED shared packages:
> (`longbox-commons`, `scrapekit`, `longbox-scrapers`, `longbox-matcher`, `dbkit`).
>
> **However**, CIE did NOT finish migrating to these packages:
> - CIE still has 588 lines of duplicate HTTP client code (should use `scrapekit`)
> - CIE still has generic matching algorithms locked in `identity_resolver` (should use `longbox-matcher`)
> - Other projects (comic-web-scrapers, comic_pricer, comics_backend) USE the packages
> - CIE is the OUTLIER that hasn't finished the migration
>
> This plan includes: (1) fixes that unblock current usage, (2) fixes for code that stays in CIE,
> and (3) **COMPLETING THE CONSOLIDATION MIGRATION** that CIE skipped.

---

## Recent Commit Review: `649afb3` — Authenticated HipComics Adapter

**Status**: New feature, all 12 tests passing, no regressions to existing tests.

### What it adds
- `comic_identity_engine/adapters/hip_auth.py` — `AuthenticatedHIPAdapter` with Playwright login + cookie caching
- `tests/test_adapters/test_hip_auth.py` — 12 tests, all passing
- `docs/HIP_AUTH.md` + `HIP_AUTH_IMPLEMENTATION.md` — documentation
- Adds `playwright>=1.48` dependency

### Issues found in this commit

**Fix 15: `hip_cookies.json` not in `.gitignore`** (security risk)
- **Severity**: 🟠 HIGH
- **File**: `.gitignore`
- **Problem**: `hip_cookies.json` (default `COOKIE_FILE` in `hip_auth.py:41`) contains session tokens but is not gitignored. `.env` is properly ignored, but cookie files are not.
- **Fix**: Add `hip_cookies.json` to `.gitignore`
- **Effort**: 1 minute

**Fix 17: `HIP_AUTH_IMPLEMENTATION.md` should be archived**
- **Severity**: 🟢 LOW
- **Problem**: Yet another root-level implementation summary doc (188 lines). This is exactly the documentation bloat pattern identified in the audit. The useful info is already in `docs/HIP_AUTH.md`.
- **Fix**: Delete or move to `docs/archive/`
- **Effort**: 1 minute

**Fix 18: `import time` inside method body**
- **Severity**: 🟢 LOW
- **File**: `comic_identity_engine/adapters/hip_auth.py:97`
- **Problem**: `import time` is inside `_load_cookies()`. Should be a top-level import.
- **Fix**: Move to top of file with other imports.
- **Effort**: 1 minute

**Fix 19: `logging` vs `structlog` inconsistency**
- **Severity**: 🟢 LOW
- **File**: `comic_identity_engine/adapters/hip_auth.py:14,26`
- **Problem**: Uses stdlib `logging.getLogger()` while the rest of the codebase uses `structlog.get_logger()`. f-string interpolation in log calls (`f"Loaded {len(valid_cookies)}..."`) is also incompatible with structlog's key-value style.
- **Fix**: Change to `structlog.get_logger(__name__)` and convert f-string log messages to structlog kwargs.
- **Effort**: 10 minutes

**Observation: Adapter not wired into platform searcher**
- The `AuthenticatedHIPAdapter` is exported in `__init__.py` and documented, but `platform_searcher.py` still uses the unauthenticated `HIPAdapter`. This means the auth adapter is available but **not yet integrated** into the import/search pipeline. This is fine as-is (it's a new feature), but worth noting — it won't affect import behavior until explicitly wired in.

---

## Overview

All 62 test failures/errors fall into **11 root causes**. Most are tests that fell behind code refactors — the production code is more correct than the tests in nearly every case. There are 2 real production bugs (Fixes 10, 21) and 1 major architecture issue (Fix 23 - duplicate code from incomplete migration).

---

## Fix 1: Config defaults out of sync with tests

**Effort**: 10 minutes
**Files**: `tests/test_config.py`
**Root cause**: `pool_size`, `max_overflow`, and `arq_job_timeout` defaults were changed in `config.py` but tests still assert old values.

| Setting | Old test expectation | Actual default |
|---------|---------------------|----------------|
| `pool_size` | 10 | 20 |
| `max_overflow` | 20 | 40 |
| `pool_capacity` | 30 | 60 |
| `arq_job_timeout` | 300 | 3000 |

**Fix**: Update assertions at:
- `tests/test_config.py:116` — change `== 10` to `== 20`, `== 20` to `== 40`, `== 30` to `== 60`
- `tests/test_config.py:213` — change `== 300` to `== 3000`

**Tests fixed**: 2

---

## Fix 2: `get_job_queue` refactored from async generator to coroutine

**Effort**: 15 minutes
**Files**: `tests/test_api/test_dependencies.py`
**Root cause**: `get_job_queue()` in `comic_identity_engine/api/dependencies.py:39` was changed from an async generator (`yield`) to a plain `async def` returning `JobQueue`. Tests still call `gen.asend(None)`.

**Fix**: Change test pattern from:
```python
gen = get_job_queue()
queue = await gen.asend(None)
```
to:
```python
queue = await get_job_queue()
```

Remove any generator cleanup code (`gen.aclose()`, `StopAsyncIteration` handling).

**Tests fixed**: 3

---

## Fix 3: `create_or_resume_import_operation` code version check

**Effort**: 30 minutes
**Files**: `tests/test_services/test_operations.py`
**Root cause**: The method now checks `existing.result["_code_version"]` against the current git hash (line 206-207 of `operations.py`). Mock operations don't have `_code_version` in their result, so the method takes the "code changed" branch and calls `self.operation_repo.create_operation()` — which is a `MagicMock`, not `AsyncMock`, so `await` crashes.

**Fix** (two changes needed per test):
1. Add `"_code_version"` to mock operation's `result` dict, matching the value `_get_code_version()` returns
2. Also make `mock_repo.create_operation` an `AsyncMock` as a safety net

Affected tests:
- `test_create_or_resume_import_operation_reuses_running_operation` (~line 323)
- `test_create_or_resume_import_operation_resumes_failed_operation` (~line 363)
- `test_create_or_resume_import_operation_retries_only_failed_rows` (~line 427)

Also check:
- `tests/test_api/test_import_router.py::test_import_clz_submits_checksum_addressed_operation`

**Tests fixed**: 3-4

---

## Fix 6: `resolve_identity_task` refactored to orchestrator pattern

**Effort**: 1-2 hours
**Files**: `tests/test_jobs/test_tasks.py`, `tests/test_integration/test_clz_import.py`, `tests/test_performance/test_queue_performance.py`
**Root cause**: `import_clz_task` now groups rows by series and enqueues `_process_series_bulk_task` sub-tasks. The mock context (`ctx`) doesn't provide an `AsyncMock` for whatever enqueue method it uses, so the task catches the `TypeError`, marks the operation as failed, and returns a result without `total_rows` — causing `KeyError`.

**Fix**:
1. Read the current `import_clz_task` to understand what it calls on `ctx` to enqueue sub-tasks
2. Provide appropriate `AsyncMock` for that enqueue call
3. Mock the sub-task return values
4. Update assertions to match the new orchestrator result format

Affected tests:
- `test_import_clz_task_success` (~845)
- `test_import_clz_task_with_existing_mapping` (~1733)
- `test_import_clz_task_resolution_failure` (~1828)
- `test_import_clz_task_row_level_error` (~2076)
- `test_import_small_csv_enqueues_tasks`, `test_import_medium_csv_enqueues_tasks` (integration)
- `test_import_retry_failed_only_enqueues_only_missing_rows`
- `test_import_resume_clears_stale_active_rows_and_requeues_remaining_rows`
- `test_clz_import_performance_small`, `test_clz_import_performance_medium`
- `test_worker_utilization_parallel`

**Tests fixed**: ~11

---

## Fix 7: `reconcile_task` query pattern

**Effort**: 30 minutes
**Files**: `tests/test_jobs/test_tasks.py`
**Root cause**: `reconcile_task` now calls `session.execute(...)` with a different query pattern. The mock `session.execute` returns an `AsyncMock` whose return value lacks `.scalars().all()` or whatever the current code chain is.

**Fix**: Read the current `reconcile_task` implementation and update the mock `session.execute()` return chain to match.

- `test_reconcile_task_success` (~1208)
- `test_reconcile_task_with_existing_mapping` (~2128)

**Tests fixed**: 2

---

## Fix 9: Database integration tests need credentials

**Effort**: 30 minutes
**Files**: `tests/conftest.py`, `tests/test_api/test_correction_analytics.py`, `tests/test_services/test_correction_analytics.py`
**Root cause**: The `db_session` fixture at `tests/conftest.py:51` connects to `postgresql://user:pass@localhost/test_db` — which doesn't exist. These 21 test errors are all `asyncpg.exceptions.InvalidPasswordError`.

**Fix options** (pick one):
1. **Skip when DB unavailable**: Add `pytest.mark.integration` and skip condition
2. **Use the real Docker DB**: Point `TEST_DATABASE_URL` at `postgresql+asyncpg://comic_user:comic_pass@localhost:5434/comic_identity` (the Docker postgres)
3. **Create a test database**: Add a script to create `test_db` with the right credentials

**Recommendation**: Option 1 (skip) is fastest. Option 2 is most practical since Docker infra is already running.

**Tests fixed**: 18 errors → 0 (or 18 skipped)

---

## Fix 10: Production bug — `import_clz_task` status update crash

**Effort**: 30 minutes
**Files**: `comic_identity_engine/jobs/tasks.py`, `comic_identity_engine/services/operations.py`
**Root cause**: From the log, `import_clz_task` crashes with:
```
Invalid status transition: running -> running. Allowed transitions: completed, failed
```

The `update_operation()` method allows `running → running` **only** when `result is not None or error_message is not None` (line 399-403). Somewhere in the import task, `update_operation(op_id, "running")` is called without passing a `result` dict.

**Fix**: Two complementary changes:
1. **Find the bare `update_operation(op_id, "running")` call** in `tasks.py` (likely near the start of `import_clz_task` when it marks the operation as running on retry). Always pass `result=` even if it's the existing result.
2. **Harden the state machine**: Allow `running → running` unconditionally as an idempotent no-op (or at least don't crash):

```python
# operations.py:399-403
# Change from requiring result/error_message to just allowing it:
is_progress_update = (
    operation.status == status
    and status == "running"
)
```

This is one of two actual production code bugs.

---

## Fix 12: CLI test stale mocks

**Effort**: 30 minutes
**Files**: `tests/test_cli/test_import_clz.py`

- `test_import_clz_attach_polls_existing_operation_without_posting` — CLI now uses different API call pattern
- `test_import_clz_retry_failed_only_posts_flag` — same

**Fix**: Read the current CLI `import_clz` command and update mocks to match its HTTP call pattern.

**Tests fixed**: 2

---

## Fix 13: Queue depth API change

**Effort**: 20 minutes
**Files**: `tests/test_jobs/test_queue.py`

- `test_get_queue_depth_returns_total_depth`
- `test_get_queue_depth_filters_by_operation`

**Root cause**: Queue depth method signature or return format changed.

**Fix**: Read current `JobQueue.get_queue_depth()` and update test mocks/assertions.

**Tests fixed**: 2

---

## Fix 14: Schema validation test

**Effort**: 10 minutes
**Files**: `tests/test_api/test_schemas.py`

- `test_valid_file_path_passes` — likely a Pydantic schema field change

**Fix**: Check current `ImportClzRequest` schema and update test input.

**Tests fixed**: 1

---

## Fix 20: Debug print statements in platform_searcher.py

**Effort**: 5 minutes
**File**: `comic_identity_engine/services/platform_searcher.py`
**Problem**: 22 `print()` debug statements (lines 676-1046) that should use `logger.debug()` or be deleted.

**Fix**: Replace all `print()` calls with `logger.debug()` or delete if redundant.

**Tests fixed**: 0 (hygiene fix)

---

## Fix 21: Production bug — `http_request_task` success logic

**Effort**: 15 minutes
**File**: `comic_identity_engine/jobs/tasks.py:530`
**Root cause**: `http_request_task` sets `success: True` for ALL HTTP responses, including 404s, 500s, etc. The test correctly expects 404 to be a failure.

**Current code**:
```python
result_dict = {
    "success": True,  # ← BUG: Always True, even for 404/500
    "status_code": response.status_code,
    "content": response.text,
    ...
}
```

**Fix**: Change line 530 to check status code:
```python
success = 200 <= response.status_code < 300
result_dict = {
    "success": success,
    "status_code": response.status_code,
    "content": response.text,
    ...
}
```

This is the second actual production code bug.

**Tests fixed**: 1

---

## Fix 22: `platform_searcher` API change after consolidation

**Effort**: 15 minutes
**Files**: `tests/test_cross_platform_search.py`
**Root cause**: After consolidation, `platform_searcher.py` now creates a `Comic` object (from `longbox-scrapers`) and passes it to `scraper.search_comic(comic)`, but the test expects the old API with individual parameters.

**Actual call**: `search_comic(Comic(id='aa:X-Men:1', title='X-Men', issue='1', ...))`
**Expected by test**: `search_comic(title='X-Men', issue='1', year=1963, publisher='Marvel')`

**Fix**: Update test to expect `Comic` object parameter.

**Tests fixed**: 1

---

## Fix 23: INCOMPLETE MIGRATION — Replace duplicate HTTP client with scrapekit

**Effort**: 1 hour
**Priority**: 🟠 HIGH — Eliminates 588 lines of duplicate code
**Files**: `comic_identity_engine/core/http_client.py`, `pyproject.toml`, all adapters

**Root cause**: CIE has 588 lines of duplicate HTTP client code that should use `scrapekit`. The consolidation plan designated CIE's `http_client.py` as the "best version" to be moved to `scrapekit`, **but the migration never happened**.

**Evidence of duplication:**
- CIE's `http_client.py`: 588 lines using httpx + tenacity
- `scrapekit/http.py`: 588 lines using httpx + tenacity
- Only difference: parameter name (`platform` vs `name`)
- Both provide: connection pooling, exponential backoff, rate limiting, request logging

**Migration steps:**
1. Add `scrapekit` to CIE's `pyproject.toml` dependencies:
   ```toml
   dependencies = [
       "scrapekit @ git+https://github.com/JoshCLWren/scrapekit.git",
       ...
   ]
   ```

2. Update imports in 9 files:
   ```bash
   # adapters/
   comic_identity_engine/adapters/aa.py
   comic_identity_engine/adapters/ccl.py
   comic_identity_engine/adapters/cpg.py
   comic_identity_engine/adapters/gcd.py
   comic_identity_engine/adapters/hip.py
   comic_identity_engine/adapters/locg.py
   comic_identity_engine/adapters/clz.py
   # other files
   comic_identity_engine/jobs/tasks.py
   comic_identity_engine/services/series_page_extractor.py
   ```

   Change:
   ```python
   from comic_identity_engine.core.http_client import HttpClient
   ```

   To:
   ```python
   from scrapekit import HttpClient
   ```

3. Update constructor calls (parameter name change):
   ```python
   # Old
   HttpClient(platform="gcd", timeout=30.0)

   # New
   HttpClient(name="gcd", timeout=30.0)
   ```

4. Delete duplicate file:
   ```bash
   rm comic_identity_engine/core/http_client.py
   ```

5. Update tests that import `http_client`:
   - Check if any tests mock `HttpClient` and update imports

6. Verify:
   ```bash
   uv sync
   uv run pytest tests/ -v
   ```

**Tests fixed**: 0 (code duplication fix, no test changes expected)

**Impact**:
- Removes 588 lines of duplicate code
- Aligns CIE with other projects (comic_pricer, comics_backend use scrapekit)
- Eliminates maintenance burden of duplicate HTTP client

---

## Fix 24: INCOMPLETE MIGRATION — Refactor identity_resolver to use longbox-matcher

**Effort**: 2-3 hours
**Priority**: 🟡 MEDIUM — Extracts generic matching algorithms to package
**Files**: `comic_identity_engine/services/identity_resolver.py`, `longbox-matcher`, tests

**Root cause**: CIE's `identity_resolver.py` (1,064 lines) contains generic matching algorithms that should be in `longbox-matcher`. The consolidation plan said "N/A: Application service (requires database/repos)", which is **partially correct** — the database-dependent parts should stay in CIE, but the pure matching algorithms should be extracted.

**What should stay in CIE (application-specific):**
- Database access via `AsyncSession` and repositories
- CIE's tiered matching strategy (UPC → series+issue → fuzzy → create)
- Entity creation/merging logic (Issues, Variants, ExternalMappings)
- `ResolutionResult` with CIE-specific UUIDs

**What should move to `longbox-matcher` (generic):**
- UPC matching algorithm: `match_upc(upc: str, candidates: List[Comic]) -> Optional[MatchResult]`
- Series/issue/year matching: `match_series_issue_year(series, issue, year, candidates) -> Optional[MatchResult]`
- Fuzzy title matching: `match_fuzzy_title(title, issue, candidates) -> List[MatchResult]`
- Similarity scoring logic (Jaro-Winkler, Jaccard, etc.)

**Migration steps:**

1. **Add generic matching methods to `longbox-matcher`:**

   Create or extend `longbox_matcher/comic.py`:
   ```python
   from typing import List, Optional
   from longbox_matcher import MatchResult

   class ComicMatcher:
       """Pure matching algorithms - no database dependencies."""

       def match_upc(self, upc: str, candidates: List[IssueCandidate]) -> Optional[MatchResult]:
           """Exact UPC matching."""
           for candidate in candidates:
               if candidate.upc == upc:
                   return MatchResult(
                       candidate=candidate,
                       confidence=1.0,
                       explanation="Exact UPC match"
                   )
           return None

       def match_series_issue_year(
           self,
           series: str,
           issue: str,
           year: int,
           candidates: List[IssueCandidate]
       ) -> Optional[MatchResult]:
           """Deterministic series + issue + year matching."""
           # Implementation from CIE's _match_by_series_issue_year
           ...

       def match_fuzzy_title(
           self,
           title: str,
           issue: str,
           candidates: List[IssueCandidate]
       ) -> List[MatchResult]:
           """Fuzzy title matching with Jaro-Winkler similarity."""
           # Implementation from CIE's _match_by_fuzzy_title
           ...
   ```

2. **Refactor CIE's `IdentityResolver` to use `ComicMatcher`:**

   ```python
   from longbox_matcher import ComicMatcher
   from comic_identity_engine.database.repositories import ...

   class IdentityResolver:
       def __init__(self, session: AsyncSession) -> None:
           self.session = session
           self.matcher = ComicMatcher()  # Generic matcher from package
           self.issue_repo = IssueRepository(session)
           self.series_repo = SeriesRunRepository(session)
           self.mapping_repo = ExternalMappingRepository(session)
           self.variant_repo = VariantRepository(session)

       async def _match_by_upc(self, upc: str) -> Optional[MatchCandidate]:
           # Use generic matcher from package
           candidates = await self.issue_repo.find_by_upc(upc)
           match = self.matcher.match_upc(upc, candidates)
           if match:
               return self._to_candidate(match)
           return None

       async def _match_by_series_issue_year(
           self,
           series: str,
           issue: str,
           year: int
       ) -> Optional[MatchCandidate]:
           # Use generic matcher from package
           candidates = await self.issue_repo.find_by_series_and_year(series, year)
           match = self.matcher.match_series_issue_year(series, issue, year, candidates)
           if match:
               return self._to_candidate(match)
           return None

       # ... similar for fuzzy matching
   ```

3. **Add `longbox-matcher` to CIE dependencies:**

   ```toml
   dependencies = [
       "longbox-matcher @ git+https://github.com/JoshCLWren/longbox-matcher.git",
       ...
   ]
   ```

4. **Update `longbox-matcher` to export `ComicMatcher`:**

   ```python
   # longbox-matcher/longbox_matcher/__init__.py
   from .comic import ComicMatcher
   from .matcher import ComicMatcher as FullMatcher

   __all__ = ["ComicMatcher", "FullMatcher", "find_fuzzy_matches", ...]
   ```

5. **Fix failing tests** (9 tests in `test_tasks.py`):
   - Tests that mock `IdentityResolver` now need to account for the injected `ComicMatcher`
   - Update mock structure to match refactored code

6. **Verify:**
   ```bash
   cd ../longbox-matcher
   uv run pytest

   cd ../comic-identity-engine
   uv sync
   uv run pytest tests/test_jobs/test_tasks.py::TestResolveIdentityTask -v
   ```

**Tests fixed**: 9 (currently failing)

**Impact**:
- Generic matching algorithms available to other projects
- CIE's `IdentityResolver` becomes thinner (orchestration + persistence only)
- Reduces code duplication across projects
- Aligns with consolidation goals

---

## Fix 25: AsyncHttpExecutor mock structure

**Effort**: 45 minutes
**Files**: `tests/test_integration/test_async_http_executor.py`
**Root cause**: The executor's `get()`/`post()` methods were refactored. Tests construct `AsyncHttpExecutor(mock_queue, mock_operations_manager)` and patch `AsyncSessionLocal`, but the internal flow no longer matches.

**Fix**: Read the current `AsyncHttpExecutor` implementation, understand the new call flow, and update all 4 tests.

- `test_get_request_success` (~47)
- `test_get_request_with_timeout` (~82)
- `test_get_request_handles_error_response` (~113)
- `test_post_request_with_json_data` (~140)

**Tests fixed**: 4

**Note**: `AsyncHttpExecutor` is legitimately CIE-specific (task queue based), not a candidate for package extraction.

---

## Fix 26: Documentation cleanup

**Effort**: 1 hour
**Not blocking, but important for maintainability**

### Files to keep (6):
- `README.md` — main entry point
- `AGENTS.md` — agent instructions
- `CRITICAL_BUGS_PLAN.md` — active bug tracking
- `SERIES_PAGE_STRATEGY.md` — referenced by AGENTS.md as mandatory reading
- `CROSS_PLATFORM_SEARCH.md` — referenced by AGENTS.md as mandatory reading
- `FIX_PLAN.md` — this file

### Files to archive (move to `docs/archive/`):
All other `.md` files in root (~31 files, 12,000+ lines). These are historical phase summaries, implementation plans, analysis docs, and progress trackers that have been superseded.

### Also fix:
- Remove duplicate "MANDATORY: Fix Broken Code" preamble from all files except `AGENTS.md` and `README.md`

---

## Execution Order

Given the incomplete consolidation migration, this plan prioritizes: (1) fixes that unblock current usage, (2) finishing the consolidation migration, and (3) remaining test fixes.

### Phase 0: Security/hygiene — DO NOW (5 minutes)

1. Fix 15 — Add `hip_cookies.json` to `.gitignore` (**security**)
2. Fix 17 — Archive `HIP_AUTH_IMPLEMENTATION.md`
3. Fix 18 — Move `import time` to top-level in `hip_auth.py`
4. Fix 19 — Switch `hip_auth.py` from `logging` to `structlog`
5. Fix 20 — Remove 22 `print()` debug statements in `platform_searcher.py`

### Phase 1: Production bugs — DO NOW (45 minutes)

The import pipeline and HTTP task must work correctly.

6. Fix 10 — `running → running` status crash in `operations.py` (30 min)
7. Fix 21 — `http_request_task` success logic bug (15 min)

### Phase 2: Complete consolidation migration — DO NOW (3-4 hours)

These fixes align CIE with the shared packages and eliminate code duplication.

8. Fix 23 — Replace duplicate HTTP client with `scrapekit` (1 hour)
9. Fix 24 — Refactor `identity_resolver` to use `longbox-matcher` (2-3 hours)

### Phase 3: CIE-resident test fixes — DO NOW (1 hour, fixes 9 tests)

These tests cover code that stays in CIE after consolidation (API, jobs, config, CLI).

10. Fix 1 — config defaults (2 tests)
11. Fix 2 — `get_job_queue` generator→coroutine (3 tests)
12. Fix 4 — worker function list (4 tests) — *already passing, skip*

### Phase 4: CIE-resident mock fixes — DO NOW (2-3 hours, fixes ~29 tests)

These test the job/operations layer which stays in CIE.

13. Fix 3 — `_code_version` in operation mocks (4 tests)
14. Fix 6 — `import_clz_task` orchestrator mocks (11 tests)
15. Fix 7 — `reconcile_task` mock chain (2 tests)
16. Fix 12 — CLI test mocks (2 tests)
17. Fix 13 — Queue depth mocks (2 tests)
18. Fix 14 — Schema test (1 test)
19. Fix 22 — `platform_searcher` API change (1 test)
20. Fix 25 — `AsyncHttpExecutor` mocks (4 tests)

### Phase 5: DB integration tests — DO NOW (30 minutes, fixes 21 errors)

21. Fix 9 — DB integration test skip/config (21 errors)

### Phase 6: Documentation — DO BEFORE CONSOLIDATION (1 hour)

22. Fix 26 — Archive ~31 root `.md` files to `docs/archive/`

---

## Expected Outcome

### After Phases 0-5 (fixes that matter NOW):

| Metric | Before | After |
|--------|--------|-------|
| Tests passing | 1,267 / 1,331 | ~1,329 / 1,331 |
| Errors | 21 | 0 |
| Tests still failing | 41 | ~2 |
| HTTP error handling | Broken (404=success) | Fixed ✅ |
| Status transition crash | `running → running` fails | Fixed ✅ |
| Duplicate HTTP client | 588 lines | 0 lines ✅ |
| Code alignment | CIE outlier | Uses shared packages ✅ |
| Generic matching | Locked in CIE | In `longbox-matcher` ✅ |

### After Phase 6 (docs cleanup):

| Metric | Before | After |
|--------|--------|-------|
| Root docs | 37 files | 6 files |
| Archived docs | 0 | ~31 in `docs/archive/` |

### Remaining failures (~2 tests):
- Any edge cases not covered by the fixes above
- Will be addressed individually as they surface

**Total estimated effort (Phases 0-5)**: ~7-9 hours
**Total estimated effort (Phase 6)**: ~1 hour

**Key improvements:**
1. ✅ Eliminates 588 lines of duplicate HTTP client code
2. ✅ Extracts generic matching algorithms to shared package
3. ✅ Fixes 2 production bugs (status crash, HTTP success logic)
4. ✅ Aligns CIE with consolidation architecture
5. ✅ Reduces test failures from 62 to ~2
