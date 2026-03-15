# Fix Plan: Comic Identity Engine

**Date**: 2026-03-14
**Verified By**: Three independent sub-agent audits + independent external audit
**Test Baseline**: 1,331 tests collected; 41 failed, 21 errors, 1,267 passed, 2 skipped
**Last Updated**: 2026-03-14 (post-consolidation plan review)

> **⚠️ CONSOLIDATION PLAN IN PROGRESS** — See `../CONSOLIDATION_PLAN.md`
>
> A cross-project consolidation will extract most CIE modules into shared packages
> (`longbox-commons`, `scrapekit`, `longbox-scrapers`, `longbox-matcher`, `dbkit`).
> This plan is now scoped to: (1) fixes that unblock current usage, (2) fixes that
> stay with CIE after extraction, and (3) hygiene fixes worth doing before extraction.
> Fixes that will be thrown away during consolidation are marked **SKIP**.

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

**Fix 16: Bare `except:` clauses in `hip_auth.py`**
- **Severity**: 🟡 MEDIUM
- **File**: `comic_identity_engine/adapters/hip_auth.py:147-150, 193-194`
- **Problem**: Two bare `except:` clauses (lines 147 and 149) in `_close_promo_iframe()`, and one at line 193 in `_login_with_playwright()`. These silently swallow all exceptions including `KeyboardInterrupt` and `SystemExit`. This violates the project's own style guide in AGENTS.md ("Never catch bare `Exception`").
- **Fix**: Change to `except Exception:` at minimum, or more specific types like `except (TimeoutError, Exception):` with logging.
- **Effort**: 5 minutes

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

All 59 test failures/errors fall into **9 root causes**. Most are tests that fell behind code refactors — the production code is more correct than the tests in nearly every case. The one real production bug is the state machine's terminal `failed` state, but it's already worked around by `create_or_resume_import_operation` bypassing the validator.

The log file `output_3_14.loG` reveals a separate runtime issue: `import_clz_task` crashes with `"Invalid status transition: running -> running"` when it calls `update_operation()` without a `result` dict. This is different from the state machine's `failed → pending` limitation.

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

## Fix 4: Worker function list and shutdown hook

**Effort**: 20 minutes
**Files**: `tests/test_jobs/test_worker.py`
**Root cause**: `_process_series_bulk_task` was added to `WorkerSettings.functions` (now 8, was 7). `on_shutdown=_on_worker_shutdown` was added to `create_worker()`. A second log line for HTTP pool init was added to `_on_worker_startup`.

**Fixes**:
- `test_worker_settings_class_attributes` (~line 139): Change `== 7` to `== 8`
- `test_worker_settings_functions_list` (~line 162): Add `_process_series_bulk_task` at correct position (index 3)
- `test_create_worker_uses_class_settings` (~line 177): Add `on_shutdown=_on_worker_shutdown` to expected `create_worker()` call kwargs
- `test_worker_startup_logs_success` (~line 193): Expect 2 info log calls (worker started + HTTP pool initialized) instead of 1

**Tests fixed**: 4

---

## Fix 5: `resolve_identity_task` mock structure stale

**Effort**: 1-2 hours
**Files**: `tests/test_jobs/test_tasks.py`
**Root cause**: The task internals were refactored. Mocks return objects the task can't use — e.g., trying to access `.issue_id` on an unawaited coroutine.

**Fix**: Read the current `resolve_identity_task` implementation carefully and rebuild mock return values to match its internal flow. Key areas:
- What does `IdentityResolver.resolve_issue()` return now?
- What attributes does the task access on the result?
- Build a proper mock result object (possibly a dataclass or dict) that satisfies all attribute accesses.

Affected tests (~line numbers in `test_tasks.py`):
- `test_resolve_identity_task_success` (~81)
- `test_resolve_identity_task_resolution_error` (~220)
- `test_resolve_identity_task_no_best_match` (~340)
- `test_resolve_identity_task_existing_mapping_uses_series_start_year_for_search` (~580)
- `test_resolve_task_status_transition_pending_to_running_to_completed` (~1402)

**Tests fixed**: 5

---

## Fix 6: `import_clz_task` refactored to orchestrator pattern

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

## Fix 8: `AsyncHttpExecutor` internal flow changed

**Effort**: 45 minutes
**Files**: `tests/test_integration/test_async_http_executor.py`
**Root cause**: The executor's `get()`/`post()` methods were refactored. Tests construct `AsyncHttpExecutor(mock_queue, mock_operations_manager)` and patch `AsyncSessionLocal`, but the internal flow no longer matches.

**Fix**: Read the current `AsyncHttpExecutor` implementation, understand the new call flow, and update all 4 tests.

- `test_get_request_success` (~47)
- `test_get_request_with_timeout` (~82)
- `test_get_request_handles_error_response` (~113)
- `test_post_request_with_json_data` (~140)

**Tests fixed**: 4

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

This is the only actual production code bug. Everything else is stale tests.

---

## Fix 11: Documentation cleanup

**Effort**: 1 hour
**Not blocking, but important for maintainability**

### Files to keep (5):
- `README.md` — main entry point
- `AGENTS.md` — agent instructions
- `CRITICAL_BUGS_PLAN.md` — active bug tracking
- `SERIES_PAGE_STRATEGY.md` — referenced by AGENTS.md as mandatory reading
- `CROSS_PLATFORM_SEARCH.md` — referenced by AGENTS.md as mandatory reading

### Files to archive (move to `docs/archive/`):
All other `.md` files in root (~30 files, 12,000+ lines). These are historical phase summaries, implementation plans, analysis docs, and progress trackers that have been superseded.

### Also fix:
- Remove duplicate "MANDATORY: Fix Broken Code" preamble from all files except `AGENTS.md` and `README.md`
- Remove leftover `print()` debug statements in `platform_searcher.py` (lines 1010-1046) — replace with `logger.debug()` or delete

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

## Execution Order (Consolidation-Aware)

Given `../CONSOLIDATION_PLAN.md`, most adapter/parser/matcher code and tests will
be extracted into shared packages. This reorders fixes by: what unblocks usage NOW,
what stays in CIE long-term, and what's wasted effort.

### Phase 0: Security/hygiene — DO NOW (5 minutes)
These fixes apply regardless of consolidation.

1. Fix 15 — Add `hip_cookies.json` to `.gitignore` (**security**)
2. Fix 16 — Replace bare `except:` with `except Exception:` in `hip_auth.py`
3. Fix 18 — Move `import time` to top-level in `hip_auth.py`
4. Fix 19 — Switch `hip_auth.py` from `logging` to `structlog`
5. Fix 20 — Remove 22 `print()` debug statements in `platform_searcher.py` (lines 676-1046)

### Phase 1: Production bug — DO NOW (30 minutes)
The import pipeline must work. This stays in CIE post-consolidation.

6. Fix 10 — `running → running` status crash in `operations.py`

### Phase 2: CIE-resident test fixes — DO NOW (1 hour, fixes 9+ tests)
These tests cover code that **stays in CIE** after consolidation (API, jobs, config, CLI).

7. Fix 1 — config defaults (2 tests) — **stays in CIE**
8. Fix 2 — `get_job_queue` generator→coroutine (3 tests) — **stays in CIE**
9. Fix 4 — worker function list (4 tests) — **stays in CIE**

### Phase 3: CIE-resident mock fixes — DO NOW (2-3 hours, fixes ~22 tests)
These test the job/operations layer which stays in CIE.

10. Fix 3 — `_code_version` in operation mocks (4 tests) — **stays in CIE**
11. Fix 6 — `import_clz_task` orchestrator mocks (11 tests) — **stays in CIE**
12. Fix 7 — `reconcile_task` mock chain (2 tests) — **stays in CIE**
13. Fix 12 — CLI test mocks (2 tests) — **stays in CIE**
14. Fix 13 — Queue depth mocks (2 tests) — **stays in CIE**
15. Fix 14 — Schema test (1 test) — **stays in CIE**

### Phase 4: DB integration tests — DO NOW (30 minutes, fixes 21 errors)
16. Fix 9 — DB integration test skip/config (21 errors) — **stays in CIE**

### Phase 5: SKIP until consolidation
These fix tests for code that will be **extracted** into shared packages.
Doing these now wastes effort — the tests will be rewritten during extraction.

17. ~~Fix 5~~ — `resolve_identity_task` mocks (5 tests) — **SKIP** (resolver → `longbox-matcher`)
18. ~~Fix 8~~ — `AsyncHttpExecutor` mocks (4 tests) — **SKIP** (http client → `scrapekit`)

### Phase 6: Documentation — DO BEFORE CONSOLIDATION (1 hour)
Clean docs make the consolidation migration easier.

19. Fix 11 — Archive ~31 root `.md` files to `docs/archive/`
20. Fix 17 — Delete or archive `HIP_AUTH_IMPLEMENTATION.md`
21. Keep: `README.md`, `AGENTS.md`, `CRITICAL_BUGS_PLAN.md`, `SERIES_PAGE_STRATEGY.md`, `CROSS_PLATFORM_SEARCH.md`, `FIX_PLAN.md`

---

## Expected Outcome

### After Phases 0-4 (fixes that matter NOW):

| Metric | Before | After |
|--------|--------|-------|
| Tests passing | 1,267 / 1,331 | ~1,319 / 1,331 |
| Errors | 21 | 0 |
| Tests still failing | 41 | ~9 (deferred to consolidation) |
| CLZ import | Crashes after ~5 min | Completes (or gracefully degrades) |
| Debug prints in prod | 22 `print()` calls | 0 |
| Bare `except:` clauses | 3 in hip_auth.py | 0 |
| Cookie file gitignored | No | Yes |
| Logging consistency | Mixed logging/structlog | All structlog |

### After Phase 6 (docs cleanup):

| Metric | Before | After |
|--------|--------|-------|
| Root docs | 37 files | 6 files |
| Archived docs | 0 | ~31 in `docs/archive/` |

### Deferred to consolidation (~9 tests):
- 5 `resolve_identity_task` tests → rewritten when resolver moves to `longbox-matcher`
- 4 `AsyncHttpExecutor` tests → rewritten when http client moves to `scrapekit`

**Total estimated effort (Phases 0-4)**: ~4-5 hours
**Total estimated effort (Phase 6)**: ~1 hour
**Skipped effort saved**: ~2-3 hours (would be thrown away during consolidation)
