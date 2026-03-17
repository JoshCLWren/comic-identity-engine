# Comic Identity Engine - Recovery Plan (CORRECTED)
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


**Version:** 2.0 (Post-Code-Review)  
**Status:** READY TO START  
**Last Updated:** 2026-03-03

---

## Executive Summary

**What went wrong:** Previous subagents implemented **synchronous** HTTP fetching using `httpx.get()` instead of **async** fetching. While the adapters now fetch real data (unlike before), they block the event loop, preventing proper integration with the async job queue (arq) and concurrent operations.

**What we're fixing:** Converting 6 adapters from sync to async:
- Change method signatures: `def fetch_issue()` → `async def fetch_issue()`
- Change HTTP client: `httpx.get()` → `httpx.AsyncClient` (via existing HttpClient)
- Update all call sites: `adapter.fetch_issue()` → `await adapter.fetch_issue()`
- Update tests: sync mocks → async mocks with pytest-asyncio

**What already works:**
- ✅ Existing `HttpClient` at `core/http_client.py` uses `httpx.AsyncClient` (we'll use this)
- ✅ Adapters fetch real data (just need to make them async)
- ✅ Test suite passes (1,180 tests)
- ✅ Database, API, CLI infrastructure is solid

**Code Review Finding:** Previous plan incorrectly stated adapters don't fetch data. They DO fetch - just synchronously. This revised plan focuses on async conversion.

---

## 7-Phase Recovery Plan

### Phase 1: Update Base Class (CRITICAL FOUNDATION)
**Status:** 🔴 NOT STARTED  
**Estimated Time:** 30 minutes  
**Owner:** TBD

**Tasks:**
1. [ ] Change `SourceAdapter.fetch_series()` to `async def`
2. [ ] Change `SourceAdapter.fetch_issue()` to `async def`
3. [ ] Update docstrings to indicate async nature
4. [ ] Verify no breaking changes to other methods

**Quality Gates:**
- [ ] Base class file loads without errors
- [ ] Abstract methods properly defined as async
- [ ] STATUS_TRACKER.md updated

---

### Phase 2: Test Infrastructure (ENABLES PHASES 3-7)
**Status:** 🔴 NOT STARTED  
**Estimated Time:** 45 minutes  
**Owner:** TBD  
**Blocked by:** Phase 1

**Tasks:**
1. [ ] Add `pytest-asyncio` to dev dependencies (if not present)
2. [ ] Configure pytest-asyncio in `pyproject.toml` or `conftest.py`
3. [ ] Create async test fixtures in `tests/conftest.py`
4. [ ] Update one adapter test as proof-of-concept

**Quality Gates:**
- [ ] `uv run pytest tests/test_adapters/test_gcd.py -v` passes with async tests
- [ ] No `RuntimeWarning: coroutine was never awaited` errors
- [ ] All existing tests still pass
- [ ] STATUS_TRACKER.md updated

---

### Phase 3: Fix GCD Adapter (REFERENCE IMPLEMENTATION)
**Status:** 🔴 NOT STARTED  
**Estimated Time:** 1 hour  
**Owner:** TBD  
**Blocked by:** Phase 2

**Tasks:**
1. [ ] Change `def fetch_series()` → `async def fetch_series()`
2. [ ] Change `def fetch_issue()` → `async def fetch_issue()`
3. [ ] Replace `httpx.get()` with `self.http_client.get()` (using existing HttpClient)
4. [ ] Update error handling for async context
5. [ ] Update all GCD tests to use `@pytest.mark.asyncio`
6. [ ] Convert sync mocks to AsyncMock where needed

**Quality Gates:**
- [ ] Subagent B code review approved
- [ ] `uv run pytest tests/adapters/test_gcd.py -v` passes
- [ ] Manual test: fetch real issue from GCD API works
- [ ] STATUS_TRACKER.md updated
- [ ] Git commit with clear message

---

### Phase 4: Fix LoCG Adapter
**Status:** 🔴 NOT STARTED  
**Estimated Time:** 1 hour  
**Owner:** TBD  
**Blocked by:** Phase 3

**Tasks:**
1. [ ] Convert to async following GCD pattern
2. [ ] Use HttpClient for requests
3. [ ] Update tests to async

**Quality Gates:** Same as Phase 3

---

### Phase 5: Fix Remaining Adapters (Parallelizable)
**Status:** 🔴 NOT STARTED  
**Estimated Time:** 3 hours total  
**Owner:** TBD (can run CCL, AA, CPG, HIP in parallel with multiple subagents)  
**Blocked by:** Phase 3 (need GCD as reference)

**Sub-phases:**
- **5a: CCL Adapter** (45 min)
- **5b: AA Adapter** (45 min)
- **5c: CPG Adapter** (45 min)
- **5d: HIP Adapter** (45 min)

**Tasks for each:**
1. [ ] Convert fetch methods to async
2. [ ] Integrate HttpClient
3. [ ] Update tests to async

**Quality Gates:** Same as Phase 3

---

### Phase 6: Update Integration Points
**Status:** 🔴 NOT STARTED  
**Estimated Time:** 1.5 hours  
**Owner:** TBD  
**Blocked by:** Phases 3-5 complete

**Tasks:**
1. [ ] Update `tasks.py`:
   - [ ] Add `await` before adapter calls
   - [ ] Ensure get_adapter returns async-capable adapters
2. [ ] Update CLI if needed (check for sync calls)
3. [ ] Update API routers if needed
4. [ ] Update any other call sites

**Files to Check:**
- `comic_identity_engine/jobs/tasks.py`
- `comic_identity_engine/cli/commands/find.py`
- `comic_identity_engine/api/routers/identity.py`

**Quality Gates:**
- [ ] All integration tests pass
- [ ] Full test suite passes (1,180 tests)
- [ ] Manual end-to-end test works
- [ ] STATUS_TRACKER.md updated

---

### Phase 7: Final Verification & Cleanup
**Status:** 🔴 NOT STARTED  
**Estimated Time:** 1 hour  
**Owner:** TBD  
**Blocked by:** Phase 6

**Tasks:**
1. [ ] Run full test suite: `uv run pytest tests/ -v`
2. [ ] Verify coverage hasn't dropped
3. [ ] Create verification script for manual testing
4. [ ] Test with real URLs from each platform
5. [ ] Update documentation if needed
6. [ ] Create SYSTEM_PROMPT.md for future work

**Quality Gates:**
- [ ] All 1,180 tests pass
- [ ] Manual verification passes
- [ ] STATUS_TRACKER.md shows all phases complete
- [ ] Git log shows clean commit history

---

## Subagent Workflows

### Standard 4-Step Workflow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Subagent A     │────▶│  Subagent B     │────▶│  Lead (me)      │────▶│  Git Commit     │
│  (Implementer)  │     │  (Reviewer)     │     │  (Verify/Test)  │     │  (Status Update)│
└─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘
```

**Step 1: Implementation** (Subagent A)
- Makes the code changes
- Follows patterns from Phase 3 (GCD adapter)
- Includes test updates
- Reports: "Implementation complete for [Phase X]"

**Step 2: Code Review** (Subagent B)
- Reviews against Code Review Checklist
- Checks for async/await correctness
- Verifies error handling
- Reports: "Review [PASS/NEEDS_WORK] - [details]"

**Step 3: Verification** (Lead - that's me)
- Runs tests: `uv run pytest tests/[relevant]/ -v`
- Checks STATUS_TRACKER.md
- Approves or requests changes
- Reports: "Verification complete - [result]"

**Step 4: Commit & Track** (Lead or Subagent A)
- `git add -p` (review changes)
- `git commit -m "[phase]: [clear description]"`
- Update STATUS_TRACKER.md
- Push if appropriate

---

## Code Review Checklist

### Architecture & Patterns
- [ ] Uses `async def` for all fetch methods
- [ ] Uses `await` for all HTTP calls
- [ ] Uses existing `HttpClient` from `core.http_client`
- [ ] No blocking I/O in async methods (no `requests`, no sync `httpx`)
- [ ] Follows pattern from Phase 3 (GCD adapter)

### Error Handling
- [ ] `NotFoundError` raised for 404/not found cases
- [ ] `SourceError` raised for network/HTTP errors
- [ ] `ValidationError` raised for parsing/validation failures
- [ ] All exceptions properly chained with `from e`

### Code Quality
- [ ] Type hints present (`async def fetch_issue(self, source_issue_id: str) -> IssueCandidate:`)
- [ ] Docstrings updated to mention async behavior
- [ ] No print statements (use logging if needed)
- [ ] No hardcoded URLs (use BASE_URL constants)

### Testing
- [ ] Tests marked with `@pytest.mark.asyncio`
- [ ] Mocks use `AsyncMock` for async calls
- [ ] Tests use `async def` for test functions
- [ ] All tests pass: `uv run pytest tests/[adapter]/ -v`
- [ ] No warnings about unawaited coroutines

### Dependencies
- [ ] No new dependencies added without approval
- [ ] Uses existing HttpClient (not creating new HTTP libraries)
- [ ] pytest-asyncio properly configured

---

## Quality Gates

Each phase must pass all gates before proceeding:

### Gate 1: Code Review
- [ ] Subagent B approves the implementation
- [ ] All items on Code Review Checklist checked
- [ ] No critical or major concerns from reviewer

### Gate 2: Test Suite
```bash
# Must pass with no errors
uv run pytest tests/[relevant]/ -v

# Example for GCD adapter:
# uv run pytest tests/adapters/test_gcd.py -v
```
- [ ] All tests pass
- [ ] No new warnings
- [ ] Coverage maintained (check with `uv run pytest --cov`)

### Gate 3: Manual Verification (Phases 3-7 only)
- [ ] Adapter can fetch real data from platform
- [ ] Example: `await adapter.fetch_issue("12345")` returns valid IssueCandidate
- [ ] No SSL errors or blocking issues

### Gate 4: Documentation
- [ ] STATUS_TRACKER.md updated with:
  - [ ] Phase marked complete
  - [ ] Completion date
  - [ ] Test results logged
  - [ ] Any blockers or notes documented

### Gate 5: Git Commit
- [ ] Changes committed with descriptive message:
  ```
  [phase-X]: Convert [Adapter] to async
  
  - Changed fetch_issue/fetch_series to async def
  - Integrated HttpClient for async HTTP
  - Updated tests to use pytest-asyncio
  - All tests passing
  ```
- [ ] Commit hash recorded in STATUS_TRACKER.md

---

## Recovery Procedures

### When Tests Fail

**DO NOT** proceed to next phase. Instead:

1. **STOP** - Do not continue
2. **Diagnose** - Run tests with verbose output:
   ```bash
   uv run pytest tests/[relevant]/ -v --tb=short
   ```
3. **Consult** - Ask subagent to analyze failures
4. **Fix** - Make corrections or rollback if needed
5. **Document** - Add note to STATUS_TRACKER.md about the issue
6. **Re-verify** - Re-run all gates

### When Review Finds Issues

1. **Acknowledge** - Subagent A acknowledges review feedback
2. **Fix** - Address all review comments
3. **Re-review** - Subagent B re-reviews
4. **Proceed** - Only after reviewer approves

### When Blocked

If stuck for more than 30 minutes:
1. Document current state in STATUS_TRACKER.md
2. Escalate to user with:
   - What you were trying to do
   - What went wrong
   - What you've tried
   - Specific question or help needed

---

## Communication Protocol

### Between Subagents

**Handoff Language:**
```
[Subagent A → Subagent B]: "Phase X implementation complete. 
Please review [file1.py, file2.py] against checklist. 
Focus areas: [specific concerns]."

[Subagent B → Subagent A]: "Review complete - [PASS/NEEDS_WORK].
Issues found: [list]. Recommendations: [list]."
```

### To Lead (me)

**Status Updates:**
```
"Phase X [started/in-progress/complete/blocked]
Progress: [Y]/[Z] tasks
Blockers: [none or description]
ETA: [time estimate]"
```

### Updates to User

I will update you:
- When a phase completes (all 5 gates passed)
- When we encounter blockers (after 30 min of trying)
- At natural stopping points
- When requesting decisions (architecture choices, etc.)

---

## Reference Materials

### Working Examples Location
```
/mnt/extra/josh/code/comic-web-scrapers/
├── comic_scrapers/
│   ├── common/
│   │   ├── session_manager.py      # AioHttpSessionManager pattern
│   │   └── utils/__init__.py       # get_default_headers()
│   ├── atomic_avenue/scraper.py    # AA async implementation
│   ├── ccl/scraper_http.py         # CCL async implementation
│   └── hip/scraper.py              # HIP async implementation
```

### Key Files in This Repo
```
/mnt/extra/josh/code/comic-identity-engine/
├── comic_identity_engine/
│   ├── adapters/
│   │   ├── base.py                 # Phase 1 - make async
│   │   ├── gcd.py                  # Phase 3 - reference impl
│   │   ├── locg.py                 # Phase 4
│   │   ├── ccl.py                  # Phase 5a
│   │   ├── aa.py                   # Phase 5b
│   │   ├── cpg.py                  # Phase 5c
│   │   └── hip.py                  # Phase 5d
│   ├── core/
│   │   └── http_client.py          # EXISTING - use this
│   └── jobs/
│       └── tasks.py                # Phase 6 - add await
├── tests/
│   └── adapters/                   # All need async updates
└── PLAN_REVIEW.md                  # This file
└── STATUS_TRACKER.md               # Progress tracking
```

### Commands

```bash
# Run all tests
uv run pytest tests/ -v

# Run specific adapter tests
uv run pytest tests/adapters/test_gcd.py -v

# Check coverage
uv run pytest --cov=comic_identity_engine tests/

# Type checking (if available)
uv run mypy comic_identity_engine/

# Linting (if available)
uv run ruff check .
```

---

## Current Status

See **STATUS_TRACKER.md** for detailed, up-to-date progress.

**Summary:**
- 🔴 Phase 1: NOT STARTED
- 🔴 Phase 2: NOT STARTED
- 🔴 Phase 3: NOT STARTED
- 🔴 Phase 4: NOT STARTED
- 🔴 Phase 5: NOT STARTED
- 🔴 Phase 6: NOT STARTED
- 🔴 Phase 7: NOT STARTED

**Next Action:** Await user approval to begin Phase 1.

---

## Notes

- **Rate limiting:** User will handle VPN/rate limits - don't implement complex rate limiting
- **httpx vs aiohttp:** We're using httpx (already in codebase via HttpClient), not aiohttp
- **Breaking changes:** This IS a breaking change (sync → async), but it's internal to the adapters
- **Test infrastructure:** Phase 2 is critical - without it, Phases 3-7 can't verify their work
- **Code Review Finding:** Previous subagent review revealed the adapters DO fetch data (just sync), which corrected our understanding

---

## Changelog

**v2.0 (2026-03-03):** Corrected understanding after code review
- Changed from "add HTTP fetching" to "convert to async"
- Updated to use existing HttpClient (httpx-based)
- Reduced from 9 to 7 phases
- Added explicit note about code review finding
- Marked all phases as NOT STARTED (since we need to redo with async)

**v1.0 (2026-03-04):** Initial plan (incorrect understanding)
- Assumed adapters didn't fetch data
- Planned to use aiohttp from comic-web-scrapers
- Had 9 phases
