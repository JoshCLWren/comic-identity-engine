# START_HERE.md - For the Next Developer

**Status:** 🚨 BROKEN - Cross-platform search does NOT work  
**Tests:** 1,186 tests pass (but they don't test the broken feature)  
**Date:** 2026-03-04

---

## Quick Summary

The Comic Identity Engine has:
- ✅ Working async adapters (all 7 platforms can fetch data)
- ✅ Solid database, API, CLI infrastructure
- ❌ **BROKEN:** Cross-platform search (Redis + database errors)

**What you wanted:** One URL → URLs for ALL platforms  
**What you get:** One URL → URLs ONLY if pre-linked manually

---

## Read These Files IN ORDER

### 1. APOLOGY.md (5 minutes) **← START HERE**
Honest assessment of what's broken. Written by the previous developer who broke it.

### 2. CROSS_PLATFORM_SEARCH.md (10 minutes)
What was attempted. Shows the code that was written but doesn't actually work.

### 3. AGENTS.md (5 minutes)
Development guidelines. How to run tests, code style, build commands.

### 4. SYSTEM_PROMPT.md (5 minutes)
Async patterns used in this codebase. Critical for understanding the code.

### 5. README.md (3 minutes)
Basic project overview (somewhat outdated but good context).

---

## What's Broken (The Short Version)

When you give the system a URL:
1. ✅ It parses the URL correctly
2. ✅ It fetches issue data from the platform
3. ❌ Cross-platform search tries to run
4. ❌ Scrapers throw "Redis not initialized" errors
5. ❌ Database authentication fails when saving mappings
6. ❌ **Result:** New comics show ZERO URLs from other platforms

**Test this yourself:**
```bash
export DATABASE_URL="postgresql+asyncpg://comic_user:comic_pass@localhost:5434/comic_identity"
uv run cie-find "https://www.comiccollectorlive.com/issue/comic-books/X-Men-1991/1/60580fdf-e19b-40dc-84c9-0f043807992b" -o json
# Should return URLs for AA, HIP, etc.
# Currently returns: ALL EMPTY
```

---

## Files You Need to Fix

**Primary:**
- `comic_identity_engine/services/identity_resolver.py` - Lines 527-724 (search methods)
- `comic_identity_engine/jobs/tasks.py` - Lines 170, 249 (calls search)

**The Problem:**
- `search_cross_platform()` method exists
- Tries to use scrapers from `comic-web-scrapers` package
- Scrapers require Redis cache that doesn't initialize properly
- Database connection errors prevent saving results

---

## How to Run Tests

```bash
# Run all tests (1,186 pass)
uv run pytest tests/ -v

# Run specific adapter
uv run pytest tests/adapters/test_gcd.py -v

# Run with coverage
uv run pytest --cov=comic_identity_engine tests/
```

---

## Options to Fix

**Option 1: Fix Redis/cache issues** (2-4 hours)
- Debug Redis initialization in `identity_resolver.py:_search_single_platform()`
- Ensure scrapers can work without Redis cache
- Test database mapping creation

**Option 2: Bypass scrapers, use direct search** (4-8 hours)
- Implement search methods directly in adapters
- Use platform APIs (AA has search API)
- Don't depend on `comic-web-scrapers` package

**Option 3: Manual linking only** (1 hour)
- Remove cross-platform search entirely
- Require users to manually link comics from multiple platforms
- System becomes just a URL storage/retrieval tool

---

## Environment

- **Database:** PostgreSQL on port 5434 (user: comic_user, pass: comic_pass)
- **Redis:** On port 6381
- **Working scrapers:** `/mnt/extra/josh/code/comic-web-scrapers/`
- **This repo:** `/mnt/extra/josh/code/comic-identity-engine/`

---

## Skip These (Outdated)

- STATUS_TRACKER.md - Tracks completed async conversion, not the broken feature
- PLAN_REVIEW.md - Recovery plan for async work (already done)
- AUDIT_REPORT.md - Claims adapters don't fetch (they do now)
- PROGRESS.md - From 2025, very outdated
- IMPLEMENTATION_PLAN.md - 1,480-line plan (aspirational, not reality)

---

## Good Luck

The previous developer said: *"I apologize for wasting your time and claiming things work when they don't."*

Read APOLOGY.md first. Then fix the damn thing.
