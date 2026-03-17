# CLZ Batch Import - Implementation Complete
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


## Summary

Successfully redesigned the CLZ import pipeline to use the identity resolution system. CLZ CSV rows now create external mappings using Core ComicID, enabling cross-user identity resolution and cross-platform search.

## What Was Built

### 1. Fixed CLZAdapter (`comic_identity_engine/adapters/clz.py`)
- ✅ Modified `fetch_issue_from_csv_row()` to extract Core ComicID from CSV
- ✅ Removed `source_issue_id` parameter (now extracted from "Core ComicID" column)
- ✅ Raises ValidationError if Core ComicID missing
- ✅ Uses Core ComicID as universal identifier

### 2. Redesigned import_clz_task (`comic_identity_engine/jobs/tasks.py`)
- ✅ Now uses `IdentityResolver` for each CSV row
- ✅ Creates CLZ external mappings using Core ComicID
- ✅ Runs cross-platform search for each resolved issue
- ✅ Checks for existing mappings before resolving (shared identity graph)
- ✅ Returns new format: `{total_rows, processed, resolved, failed, errors, summary}`
- ✅ Updates progress every 10 rows
- ✅ Handles errors per-row (doesn't abort entire import)

### 3. Updated CLI Command (`comic_identity_engine/cli/commands/import_clz.py`)
- ✅ Displays new metrics: total_rows, processed, resolved, failed
- ✅ Calculates and displays success rate percentage
- ✅ Progress bar shows "X of Y rows processed"
- ✅ Verbose mode shows first 20 errors

## Architecture Flow

```
CLZ CSV (with Core ComicID)
    ↓
CLI: cie-import-clz collection.csv
    ↓
API: POST /api/v1/import/clz
    ↓
Task: import_clz_task
    ↓
For each row:
    1. CLZAdapter.fetch_issue_from_csv_row(row)
       → IssueCandidate with source_issue_id = Core ComicID
    ↓
    2. Check for existing CLZ external mapping
       ├─ Exists: Reuse it, skip resolution
       └─ Not exists: Continue
    ↓
    3. IdentityResolver.resolve_issue()
       → Find/create canonical issue
    ↓
    4. Create CLZ external mapping
       source="clz", source_issue_id="60070" → canonical UUID
    ↓
    5. Cross-platform search (GCD, LoCG, CCL, AA, CPG, HIP)
       → Find same issue on all platforms
    ↓
    6. Store all platform mappings in shared identity graph
```

## The Big Win: Shared Identity Graph

**When User A imports CLZ Core ComicID "60070":**
1. System resolves to canonical issue
2. Creates CLZ external mapping
3. Finds cross-platform URLs:
   - GCD: issue 125295
   - LoCG: issue 1169529
   - CCL: issue 98ab98c9-a87a-4cd2-b49a-ee5232abc0ad

**When User B imports the SAME Core ComicID "60070":**
1. System finds existing CLZ mapping
2. **Immediately returns all cross-platform URLs**
3. No redundant searches - instant resolution!

Every CLZ import builds a shared knowledge base that benefits all users.

## Usage

```bash
# Start infrastructure
docker compose up -d postgres-app redis

# Start API and worker
cie-api &
cie-worker &

# Import CLZ collection (with Core ComicID column)
cie-import-clz /path/to/clz_export.csv

# Verbose mode (shows errors)
cie-import-clz /path/to/clz_export.csv --verbose

# Fire-and-forget mode
cie-import-clz /path/to/clz_export.csv --no-wait
```

## Expected Output

```
╭──────────────────────────────────────────────╮
│           CLZ Import Results                 │
├────────────────────┬─────────────────────────┤
│ Metric             │ Value                   │
├────────────────────┼─────────────────────────┤
│ Total Rows         │ 5200                    │
│ Processed          │ 5200                    │
│ Resolved           │ 5185                    │
│ Failed             │ 15                      │
│ Success Rate       │ 99.7%                   │
╰────────────────────┴─────────────────────────╯

Processed 5200 CLZ rows: 5185 resolved, 15 failed. 15 errors.
```

## Files Modified

1. **comic_identity_engine/adapters/clz.py**
   - `fetch_issue_from_csv_row()`: Extracts Core ComicID from CSV row

2. **comic_identity_engine/jobs/tasks.py**
   - `import_clz_task()`: Redesigned to use IdentityResolver

3. **comic_identity_engine/cli/commands/import_clz.py**
   - Updated for new response format (processed, resolved, failed, success rate)

## Key Differences from Original Design

### Before (Wrong):
```python
# Used row index as source_issue_id
source_issue_id = str(idx)  # "0", "1", "2"...

# Direct DB writes, no identity resolution
series = await series_repo.create(...)
issue = await issue_repo.create(...)

# No CLZ external mappings created
# No cross-platform search
# Each user's data isolated
```

### After (Correct):
```python
# Extract Core ComicID from CSV
core_comic_id = row.get("Core ComicID")  # "60070", "60069"...

# Use IdentityResolver
result = await resolver.resolve_issue(parsed_url, upc, series_title, ...)

# Create CLZ external mapping
await mapping_repo.create_mapping(
    issue_id=result.issue_id,
    source="clz",
    source_issue_id=core_comic_id,  # Universal identifier
)

# Run cross-platform search
await searcher.search_all_platforms(...)

# Build shared identity graph
```

## Testing

To verify the implementation:

1. **Test CLZAdapter:**
```python
adapter = CLZAdapter()
rows = adapter.load_csv_from_file("test.csv")
candidate = adapter.fetch_issue_from_csv_row(rows[0])
assert candidate.source_issue_id == "60070"  # Core ComicID
```

2. **Test import_clz_task:**
```bash
cie-import-clz test_small.csv --verbose
```

3. **Test cross-user resolution:**
   - User A imports CSV → Creates mappings
   - User B imports same CSV → Hits cache, instant resolution

## Future Enhancements

Not included but could be added:
- `--limit` flag to process only N rows (for testing)
- `--dry-run` flag to validate CSV without importing
- Progress resumption for interrupted imports
- Parallel row processing (with concurrency limits)
- Web UI for monitoring import operations

## Conclusion

The CLZ import pipeline is now fully integrated with the identity resolution system. Each CLZ CSV import:
1. Creates external mappings using universal Core ComicID identifiers
2. Resolves issues through the canonical identity system
3. Runs cross-platform search to find same issues on GCD, LoCG, CCL, etc.
4. Builds a shared knowledge base that benefits all users

This transforms CLZ from a simple data import format into a powerful tool for building a comprehensive cross-platform comic identity graph.
