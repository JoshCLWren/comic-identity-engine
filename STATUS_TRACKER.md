# Comic Identity Engine - Recovery Status Tracker (CORRECTED)

**Last Updated:** 2026-03-03  
**Current Phase:** Phase 1 - Update Base Class  
**Overall Status:** 🔴 NOT STARTED (corrected understanding after code review)  
**Plan Version:** 2.0

---

## Project Overview (CORRECTED)

**What we're fixing:** Previous subagents implemented **synchronous** HTTP fetching (`httpx.get()`) instead of **async** (`httpx.AsyncClient`). The adapters DO fetch real data now - they just block the event loop.

**The Real Problem:**
- ✅ Adapters fetch data (they're not stubs anymore)
- ❌ They use `def fetch_issue()` + `httpx.get()` (blocking)
- ❌ Need `async def fetch_issue()` + `await http_client.get()` (non-blocking)

**Goal:** Convert 6 adapters from sync to async to work properly with the async job queue.

**Scope:**
- Phase 1: Update base class to async
- Phase 2: Set up test infrastructure (pytest-asyncio)
- Phases 3-7: Convert adapters (GCD, LoCG, CCL, AA, CPG, HIP)
- Phase 8: Update integration points (tasks.py, CLI)
- Phase 9: Final verification

**What's Already Working:**
- ✅ Adapters fetch real data (sync version)
- ✅ HttpClient exists at `core/http_client.py` (uses httpx.AsyncClient)
- ✅ Test suite passes (1,180 tests)
- ✅ Database, API, CLI infrastructure solid

---

## Quick Reference

| Resource | Path/Command |
|----------|--------------|
| **Plan** | `/mnt/extra/josh/code/comic-identity-engine/PLAN_REVIEW.md` |
| **Working scrapers** | `/mnt/extra/josh/code/comic-web-scrapers/` |
| **Main source** | `/mnt/extra/josh/code/comic-identity-engine/comic_identity_engine/` |
| **Tests** | `/mnt/extra/josh/code/comic-identity-engine/tests/` |
| **Run all tests** | `uv run pytest tests/ -v` |
| **Run adapter tests** | `uv run pytest tests/adapters/ -v` |
| **Run specific adapter** | `uv run pytest tests/adapters/test_gcd.py -v` |
| **Check coverage** | `uv run pytest --cov=comic_identity_engine tests/` |

---

## Phase Status (7 Phases)

### Phase 1: Update Base Class
**Status:** 🟢 COMPLETE  
**Owner:** Subagent A  
**Start Date:** 2026-03-03  
**Completion Date:** 2026-03-03  
**Blocked by:** None

**Objective:** Make abstract base class async so all adapters inherit async signatures.

#### Tasks:
- [x] Change `SourceAdapter.fetch_series()` to `async def`
- [x] Change `SourceAdapter.fetch_issue()` to `async def`
- [x] Update docstrings to indicate async nature
- [x] Verify no breaking changes to other methods

#### Files to Modify:
- `comic_identity_engine/adapters/base.py`

#### Quality Gates:
- [x] Code review by Subagent B
- [x] Base class file loads without errors
- [x] Abstract methods properly defined as async
- [x] STATUS_TRACKER.md updated
- [x] Git commit with message: `phase-1: Convert base adapter class to async`

#### Notes:
- **CRITICAL:** This is the foundation. All other phases depend on this.
- Changes here affect all downstream adapters
- Must use `async def` not just `def`

---

### Phase 2: Test Infrastructure
**Status:** 🔴 NOT STARTED  
**Owner:** TBD  
**Start Date:** TBD  
**Completion Date:** TBD  
**Blocked by:** Phase 1

**Objective:** Set up pytest-asyncio so we can test async adapters.

#### Tasks:
- [ ] Check if `pytest-asyncio` in dev dependencies
- [ ] If not present, add to `pyproject.toml`
- [ ] Configure pytest-asyncio in `pyproject.toml` or `conftest.py`
- [ ] Create async test fixtures in `tests/conftest.py`
- [ ] Update one GCD test as proof-of-concept
- [ ] Verify all tests still pass

#### Files to Modify:
- `pyproject.toml` (dependencies)
- `tests/conftest.py` (fixtures)
- `tests/adapters/test_gcd.py` (proof-of-concept)

#### Quality Gates:
- [ ] Code review by Subagent B
- [ ] `uv run pytest tests/adapters/test_gcd.py -v` passes
- [ ] No `RuntimeWarning: coroutine was never awaited` errors
- [ ] All existing tests still pass
- [ ] STATUS_TRACKER.md updated
- [ ] Git commit: `phase-2: Add pytest-asyncio infrastructure`

#### Notes:
- Without this phase, we can't verify Phases 3-7 work correctly
- Example fixture needed: async mock HTTP client

---

### Phase 3: Fix GCD Adapter (REFERENCE)
**Status:** 🔴 NOT STARTED  
**Owner:** TBD  
**Start Date:** TBD  
**Completion Date:** TBD  
**Blocked by:** Phase 2

**Objective:** Convert GCD adapter from sync to async. This is the reference implementation for all other adapters.

#### Tasks:
- [ ] Change `def fetch_series()` → `async def fetch_series()`
- [ ] Change `def fetch_issue()` → `async def fetch_issue()`
- [ ] Replace `httpx.get()` with `await self.http_client.get()`
- [ ] Update error handling for async context
- [ ] Update all GCD tests to use `@pytest.mark.asyncio`
- [ ] Convert sync mocks to `AsyncMock` where needed
- [ ] Test with real GCD API call (issue #125295)

#### Files to Modify:
- `comic_identity_engine/adapters/gcd.py`
- `tests/adapters/test_gcd.py`

#### Quality Gates:
- [ ] Subagent B code review approved
- [ ] `uv run pytest tests/adapters/test_gcd.py -v` passes
- [ ] Manual test: `await adapter.fetch_issue("125295")` works
- [ ] No unawaited coroutine warnings
- [ ] STATUS_TRACKER.md updated
- [ ] Git commit: `phase-3: Convert GCD adapter to async`

#### Notes:
- GCD API: `https://www.comics.org/api/issue/{id}/?format=json`
- GCD is public API, no auth needed
- This adapter sets the pattern for all others

---

### Phase 4: Fix LoCG Adapter
**Status:** 🔴 NOT STARTED  
**Owner:** TBD  
**Start Date:** TBD  
**Completion Date:** TBD  
**Blocked by:** Phase 3

**Objective:** Convert LoCG adapter to async, following GCD pattern.

#### Tasks:
- [ ] Convert fetch methods to async
- [ ] Use HttpClient for requests
- [ ] Update tests to async

#### Files to Modify:
- `comic_identity_engine/adapters/locg.py`
- `tests/adapters/test_locg.py`

#### Quality Gates: Same as Phase 3

#### Notes:
- LoCG may need User-Agent header to avoid 403 errors
- Pattern: follow exactly what GCD adapter does

---

### Phase 5: Fix Remaining Adapters (Parallel)
**Status:** 🔴 NOT STARTED  
**Owner:** TBD (multiple subagents)  
**Start Date:** TBD  
**Completion Date:** TBD  
**Blocked by:** Phase 3

**Objective:** Convert CCL, AA, CPG, HIP adapters to async. Can run in parallel.

#### Sub-Phases:

**5a: CCL Adapter**
- Files: `adapters/ccl.py`, `tests/adapters/test_ccl.py`
- Notes: May need SSL verify=False

**5b: AA Adapter**
- Files: `adapters/aa.py`, `tests/adapters/test_aa.py`
- Notes: Check URL patterns

**5c: CPG Adapter**
- Files: `adapters/cpg.py`, `tests/adapters/test_cpg.py`
- Notes: Has Cloudflare, may be tricky

**5d: HIP Adapter**
- Files: `adapters/hip.py`, `tests/adapters/test_hip.py`
- Notes: Check scraper examples

#### Quality Gates per Adapter:
- [ ] Code review by Subagent B
- [ ] Tests pass: `uv run pytest tests/adapters/test_[adapter].py -v`
- [ ] Manual test works
- [ ] STATUS_TRACKER.md updated
- [ ] Git commit: `phase-5[X]: Convert [Platform] adapter to async`

#### Coordination:
- Each sub-phase needs separate subagent
- All follow exact same pattern as Phase 3 (GCD)
- No deviations without approval

---

### Phase 6: Update Integration Points
**Status:** 🔴 NOT STARTED  
**Owner:** TBD  
**Start Date:** TBD  
**Completion Date:** TBD  
**Blocked by:** Phases 3-5 complete

**Objective:** Add `await` to all adapter call sites.

#### Tasks:
- [ ] Update `tasks.py`: add `await` before adapter calls
- [ ] Update CLI: check for sync calls
- [ ] Update API routers: check for sync calls
- [ ] Run integration tests

#### Files to Check:
- `comic_identity_engine/jobs/tasks.py`
- `comic_identity_engine/cli/commands/find.py`
- `comic_identity_engine/api/routers/identity.py`

#### Quality Gates:
- [ ] Code review by Subagent B
- [ ] All integration tests pass
- [ ] Full test suite passes (1,180 tests)
- [ ] Manual end-to-end test works
- [ ] STATUS_TRACKER.md updated
- [ ] Git commit: `phase-6: Add await to integration points`

#### Notes:
- Critical phase - if missed, system won't work
- Look for all `adapter.fetch_issue()` calls, change to `await adapter.fetch_issue()`

---

### Phase 7: Final Verification
**Status:** 🔴 NOT STARTED  
**Owner:** TBD  
**Start Date:** TBD  
**Completion Date:** TBD  
**Blocked by:** Phase 6

**Objective:** Verify everything works end-to-end.

#### Tasks:
- [ ] Run full test suite: `uv run pytest tests/ -v`
- [ ] Verify coverage hasn't dropped
- [ ] Create verification script for manual testing
- [ ] Test with real URLs from each platform
- [ ] Create SYSTEM_PROMPT.md for future work
- [ ] Final documentation updates

#### Quality Gates:
- [ ] All 1,180 tests pass
- [ ] Manual verification passes for all 6 platforms
- [ ] STATUS_TRACKER.md shows all phases complete
- [ ] Git log shows clean commit history
- [ ] Git commit: `phase-7: Final verification and cleanup`

#### Notes:
- Final checkpoint before declaring success
- Create verification script: `verify_adapters.py`

---

## Test Results Log

| Date | Phase | Tests Run | Passed | Failed | Notes |
|------|-------|-----------|--------|--------|-------|
| 2026-03-03 | Baseline | 1,180 | 1,180 | 0 | All tests pass (but adapters are sync) |
| 2026-03-03 | Phase 1 | 39 | 39 | 0 | Base class async, GCD tests still pass |
| 2026-03-03 | Phase 2 | 41 | 41 | 0 | Added async fixtures and 2 async proof-of-concept tests |
| 2026-03-03 | Phase 3 | 41 | 41 | 0 | GCD adapter fully async, all tests pass |

---

## Git Commit Log

| Date | Phase | Commit Hash | Message | Author |
|------|-------|-------------|---------|--------|
| 2026-03-03 | Setup | TBD | Create corrected PLAN_REVIEW.md and STATUS_TRACKER.md | System |
| 2026-03-03 | - | fe3d24b | wip: Current state before scraper integration | Previous |

---

## Known Issues (CORRECTED)

### Critical (Needs Fixing)
1. **Adapters are sync, not async** - They use `def` + `httpx.get()` instead of `async def` + `await`
2. **Base class is sync** - Abstract methods need to be async
3. **Tests are sync** - Need pytest-asyncio infrastructure

### Already Working ✅
- Adapters DO fetch real data (verified with GCD)
- HttpClient exists and uses httpx.AsyncClient
- Database, API, CLI infrastructure solid
- Test suite passes

---

## Resources

### Working Async Examples
```
/mnt/extra/josh/code/comic-web-scrapers/
├── comic_scrapers/
│   ├── common/
│   │   ├── session_manager.py      # AioHttpSessionManager pattern
│   │   └── utils/__init__.py       # get_default_headers()
│   ├── atomic_avenue/scraper.py    # Async pattern example
│   └── hip/scraper.py              # Another async example
```

### Key Files in This Repo
```
/mnt/extra/josh/code/comic-identity-engine/
├── comic_identity_engine/
│   ├── adapters/
│   │   ├── base.py                 # Phase 1
│   │   ├── gcd.py                  # Phase 3 (reference)
│   │   ├── locg.py                 # Phase 4
│   │   ├── ccl.py                  # Phase 5a
│   │   ├── aa.py                   # Phase 5b
│   │   ├── cpg.py                  # Phase 5c
│   │   └── hip.py                  # Phase 5d
│   ├── core/
│   │   └── http_client.py          # Use this (httpx.AsyncClient)
│   └── jobs/
│       └── tasks.py                # Phase 6
├── tests/
│   └── adapters/                   # All need async updates
└── PLAN_REVIEW.md                  # Full methodology
└── STATUS_TRACKER.md               # This file
```

### Commands
```bash
# Run all tests
uv run pytest tests/ -v

# Run specific adapter
uv run pytest tests/adapters/test_gcd.py -v

# Check coverage
uv run pytest --cov=comic_identity_engine tests/

# Type check (if available)
uv run mypy comic_identity_engine/
```

---

## Adapter Inventory (CORRECTED STATUS)

| Platform | Adapter | Current Status | Target Status | Phase |
|----------|---------|----------------|---------------|-------|
| GCD | `gcd.py` | 🟡 Sync but works | 🟢 Async | Phase 3 |
| LoCG | `locg.py` | 🟡 Sync but works | 🟢 Async | Phase 4 |
| CCL | `ccl.py` | 🟡 Sync but works | 🟢 Async | Phase 5a |
| AA | `aa.py` | 🟡 Sync but works | 🟢 Async | Phase 5b |
| CPG | `cpg.py` | 🟡 Sync but works | 🟢 Async | Phase 5c |
| HIP | `hip.py` | 🟡 Sync but works | 🟢 Async | Phase 5d |
| CLZ | `clz.py` | 🟢 CSV only (OK) | 🟢 No change needed | N/A |

**Legend:**
- 🔴 Not fetching data (was old status)
- 🟡 Sync but fetching data (current status)
- 🟢 Async and working (target status)

---

## Success Criteria

### Phase Completion Criteria
- [ ] All tasks for phase marked complete
- [ ] Code review approved (Subagent B)
- [ ] Tests pass
- [ ] STATUS_TRACKER.md updated
- [ ] Git commit with clear message

### Project Completion Criteria
- [ ] All 6 adapters converted to async
- [ ] All adapter tests use pytest-asyncio
- [ ] Integration points use `await`
- [ ] Full test suite passes (1,180 tests)
- [ ] Manual verification passes for each platform
- [ ] STATUS_TRACKER.md shows all phases complete
- [ ] SYSTEM_PROMPT.md created for future work

---

## Update Protocol

When updating this tracker:

1. **Update header:** Change "Last Updated" to current time
2. **Update phase status:** Use 🔴🟡🟢 appropriately
3. **Fill in dates:** When phases start/complete
4. **Check off tasks:** Use `[x]` for completed
5. **Add to logs:** Test Results and Git Commit logs
6. **Update blockers:** As dependencies change

### Status Emoji Key
- 🔴 **NOT STARTED** - Phase not begun
- 🟡 **IN PROGRESS** - Phase actively being worked
- 🟢 **COMPLETE** - Phase done, all gates passed

---

## Team Structure

**Lead (Me):** 
- Oversee all phases
- Approve after verification
- Update you on progress
- Handle blockers

**Subagent A (Implementer):**
- Makes code changes
- Follows checklist
- Reports: "Phase X implementation complete"

**Subagent B (Reviewer):**
- Reviews all changes
- Checks against checklist
- Reports: "Review PASS/NEEDS_WORK"

---

## Next Action

**Status:** Awaiting your approval to begin Phase 1.

**Ready to start:** Yes, plan is corrected and documented.

---

*This document reflects CORRECTED understanding after code review. Previous version had incorrect assumption that adapters don't fetch data. They DO fetch - just synchronously. Goal is async conversion.*
