# Document Index: HTTP Request-Level Task Granularity

## Quick Start

**For agents assigned to implement this plan:**

1. Read `MASTER_IMPLEMENTATION_PLAN.md` (this document)
2. Read all referenced documents in order
3. Implement phases sequentially
4. Test after each phase

## Document Hierarchy

```
MASTER_IMPLEMENTATION_PLAN.md (START HERE)
    │
    ├─→ CLZ_IMPORT_REDESIGN.md
    │   (Context: CLZ Core ComicID, identity resolution)
    │
    ├─→ CLZ_IMPORT_COMPLETE.md
    │   (Context: Current implementation status)
    │
    ├─→ CONCURRENCY_ANALYSIS.md
    │   (Problem: Serial processing, workers idle)
    │
    └─→ PLATFORM_SEARCH_GRANULARITY_ANALYSIS.md
        (Solution: HTTP request = atomic task)
```

## Reading Order

### Phase 1: Understand the Problem (30 minutes)

1. **CONCURRENCY_ANALYSIS.md**
   - Why current implementation is serial
   - Worker utilization problem
   - Visual diagrams of current vs target architecture

2. **PLATFORM_SEARCH_GRANULARITY_ANALYSIS.md**
   - Detailed breakdown of operations
   - What can be parallelized
   - True atomic unit = HTTP request

### Phase 2: Understand Context (15 minutes)

3. **CLZ_IMPORT_REDESIGN.md**
   - CLZ Core ComicID concept
   - Identity resolution pipeline
   - Shared identity graph vision

4. **CLZ_IMPORT_COMPLETE.md**
   - What was already implemented
   - Current state of codebase
   - CLI usage examples

### Phase 3: Execute Implementation (2-4 hours)

5. **MASTER_IMPLEMENTATION_PLAN.md**
   - Complete implementation guide
   - 6 phases with detailed tasks
   - Code examples for each component
   - Acceptance criteria
   - Testing strategy

## Summary by Document

### CONCURRENCY_ANALYSIS.md
**Purpose:** Explain why current implementation is slow
**Key insight:** One giant task processes all rows serially, 9 workers sit idle
**Diagrams:** Current vs target architecture visualizations

### PLATFORM_SEARCH_GRANULARITY_ANALYSIS.md
**Purpose:** Identify true atomic unit of work
**Key insight:** One HTTP request = atomic task (not one row, not one platform search)
**Numbers:** 5,200 rows × 6 platforms × 3-7 HTTP requests = 93,600-218,400 tasks
**Recommendation:** One HTTP request + parse = one task

### CLZ_IMPORT_REDESIGN.md
**Purpose:** Original redesign plan for CLZ imports
**Key concept:** Core ComicID as universal identifier across users
**Benefits:** Shared identity graph, cross-user resolution

### CLZ_IMPORT_COMPLETE.md
**Purpose:** Current implementation status
**What's done:** CLZAdapter, import_clz_task, CLI command
**What changes:** Response format, new metrics (processed, resolved, failed)

### MASTER_IMPLEMENTATION_PLAN.md
**Purpose:** Complete execution guide for HTTP request-level parallelism
**Contents:**
- 6 implementation phases
- Detailed code examples
- File-by-file changes
- Acceptance criteria
- Testing strategy
- Rollout plan
- Risk mitigation

## Implementation Phases (Summary)

**Phase 1:** Create HTTP request task infrastructure
- Add `http_request_task` to tasks.py
- Add `enqueue_http_request` to queue.py

**Phase 2:** Refactor platform adapters
- Create `AsyncHttpExecutor`
- Update adapters to use task-based HTTP

**Phase 3:** Redesign platform search
- Create task-based `PlatformSearcher`
- Each platform search enqueues HTTP tasks

**Phase 4:** Redesign CLZ import
- Replace serial `import_clz_task`
- Add `resolve_clz_row_task`
- One task per row, rows use HTTP tasks

**Phase 5:** Update CLI (likely no changes needed)
- Verify compatibility

**Phase 6:** Configure queue
- Optimize for high task throughput
- Monitor queue depth

## Key Metrics

**Before (current):**
- Time: 2-4 hours for 5,200 rows
- Worker utilization: 10% (1 of 10 workers)
- Task count: 1 giant task

**After (target):**
- Time: 15-30 minutes for 5,200 rows
- Worker utilization: 90-100%
- Task count: 93,600-218,400 HTTP request tasks

## Common Questions

**Q: Why not make every DB query a task?**
A: Diminishing returns. DB queries are ~1ms, HTTP requests are 100ms-30s. Network I/O dominates.

**Q: Will the queue handle 200k tasks?**
A: Yes, Redis queues handle millions. Configure `ARQ_QUEUE_SIZE=10000`.

**Q: What about rate limiting?**
A: Implement exponential backoff, task priorities, monitor platform response times.

**Q: Can we test incrementally?**
A: Yes! Deploy Phase 1 first, test with manual HTTP enqueue, then proceed phase-by-phase.

## Getting Help

If anything is unclear:

1. Re-read the relevant document
2. Check code examples in MASTER_IMPLEMENTATION_PLAN.md
3. Refer to original codebase for patterns
4. Ask questions before implementing

## Success Checklist

After implementation, verify:

- [ ] http_request_task executes single HTTP requests
- [ ] All workers processing continuously (not 1 worker busy, 9 idle)
- [ ] Queue depth visible and reasonable
- [ ] CLZ import completes in 15-30 minutes (not 2-4 hours)
- [ ] Error handling graceful (per-request failures don't stop import)
- [ ] Worker utilization at 90-100%
- [ ] Observable progress (per HTTP request)

## Files to Create/Modify

**New files:**
- `comic_identity_engine/core/async_http.py`
- `comic_identity_engine/services/platform_searcher.py`

**Modify files:**
- `comic_identity_engine/jobs/tasks.py` (3 new tasks, 1 replaced)
- `comic_identity_engine/jobs/queue.py` (2 new methods)
- `comic_identity_engine/adapters/*.py` (use AsyncHttpExecutor)

**CLI:** Likely no changes needed

**Worker config:** Tune for high throughput

---

**Start here:** MASTER_IMPLEMENTATION_PLAN.md

**Questions?** All answers in referenced documents.
