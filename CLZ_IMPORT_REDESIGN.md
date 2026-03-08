# CLZ Import Pipeline Redesign - Implementation Plan

## Problem Statement

The current `import_clz_task` in `comic_identity_engine/jobs/tasks.py` **bypasses the identity resolution pipeline**:

- ❌ Uses row index (`"0"`, `"1"`, `"2"`) as source_issue_id
- ❌ Directly creates Series/Issue/Variant entities in database
- ❌ Does NOT create CLZ external mappings
- ❌ Does NOT run cross-platform search
- ❌ Each user's imports are isolated - no shared identity graph

**Result:** CLZ Core ComicID (a universal identifier) is wasted, and the big win of cross-user identity resolution is lost.

## Solution

Redesign `import_clz_task` to use the **identity resolution pipeline**:

- ✅ Extract CLZ Core ComicID from CSV (`"60070"`, `"60069"`, etc.)
- ✅ Create IssueCandidate for each row
- ✅ Call `IdentityResolver.resolve_issue()` to find/create canonical issue
- ✅ Create external mapping: `source="clz"`, `source_issue_id="60070"` → canonical UUID
- ✅ Run cross-platform search (GCD, LoCG, CCL, AA, CPG, HIP)
- ✅ Store all platform mappings in shared identity graph

**The Big Win:**
When User A imports CLZ Core ComicID `"60070"`, the system resolves it and finds:
- GCD issue `125295`
- LoCG issue `1169529`
- CCL issue `98ab98c9-a87a-4cd2-b49a-ee5232abc0ad`

When User B imports the **same** Core ComicID `"60070"`:
- System finds existing CLZ external mapping
- **Immediately returns all cross-platform URLs** - no re-search needed
- Shared identity graph grows with every import!

## Architecture Changes

### Current (Wrong) Flow

```
CLI → API → import_clz_task → Direct DB writes
         ↓
    No identity resolution
    No external mappings
    No cross-platform search
```

### New (Correct) Flow

```
CLI → API → import_clz_task → IdentityResolver
                              ↓
                         Create canonical issue
                         Create CLZ external mapping
                         Run cross-platform search
                         Store all platform mappings
```

## Implementation Tasks

### Task 1: Fix CLZAdapter to Extract Core ComicID

**File:** `comic_identity_engine/adapters/clz.py`

**Problem:**
- `fetch_issue_from_csv_row()` accepts `source_issue_id` as parameter
- Should extract it from the CSV row instead

**Solution:**
```python
def fetch_issue_from_csv_row(self, row: dict[str, str]) -> IssueCandidate:
    """Parse issue from CLZ CSV row.

    Args:
        row: Single CSV row as dictionary

    Returns:
        IssueCandidate with validated metadata

    Raises:
        ValidationError: Required fields missing or issue number invalid
    """
    # Extract Core ComicID from row
    core_comic_id = row.get("Core ComicID")
    if not core_comic_id:
        raise ValidationError("CLZ issue missing required field: Core ComicID")

    # Use Core ComicID as source_issue_id
    source_issue_id = str(core_comic_id).strip()

    # Rest of existing parsing logic...
    # Return IssueCandidate with source_issue_id=core_comic_id
```

**Acceptance Criteria:**
- `fetch_issue_from_csv_row()` no longer requires `source_issue_id` parameter
- Extracts `Core ComicID` from CSV row
- Uses it as the `source_issue_id` in returned IssueCandidate
- Raises ValidationError if Core ComicID missing

---

### Task 2: Redesign import_clz_task to Use Identity Resolution Pipeline

**File:** `comic_identity_engine/jobs/tasks.py`

**Problem:**
- Currently does direct DB writes
- Bypasses IdentityResolver
- No external mappings created

**Solution:**
```python
async def import_clz_task(
    ctx: dict[str, Any],
    csv_path: str,
    operation_id: str,
) -> dict[str, Any]:
    """Import comic data from CLZ CSV export through identity resolution.

    This task loads a CLZ CSV file and resolves each row through the
    identity resolution pipeline, creating external mappings and running
    cross-platform search for each issue.

    Args:
        ctx: ARQ context dictionary
        csv_path: Path to the CLZ CSV export file
        operation_id: UUID of the operation to track

    Returns:
        Dictionary with import results:
        - total_rows: Total number of rows in CSV
        - processed: Number of rows processed
        - resolved: Number of issues successfully resolved
        - failed: Number of rows that failed to resolve
        - errors: List of any errors encountered
        - summary: Brief text summary of the import
    """
    async with AsyncSessionLocal() as session:
        try:
            operation_uuid = uuid.UUID(operation_id)
            operations_manager = OperationsManager(session)

            await operations_manager.mark_running(operation_uuid)

            adapter = CLZAdapter()
            rows = adapter.load_csv_from_file(csv_path)

            mapping_repo = ExternalMappingRepository(session)
            errors = []
            processed = 0
            resolved = 0
            failed = 0

            for idx, row in enumerate(rows):
                try:
                    # Create IssueCandidate from CSV row (with Core ComicID)
                    candidate = adapter.fetch_issue_from_csv_row(row)

                    # Check for existing CLZ mapping
                    existing = await mapping_repo.find_by_source(
                        "clz", candidate.source_issue_id
                    )

                    if existing:
                        logger.info(
                            "Found existing CLZ mapping",
                            operation_id=operation_id,
                            source_issue_id=candidate.source_issue_id,
                            issue_id=str(existing.issue_id),
                        )
                        resolved += 1
                    else:
                        # Resolve through IdentityResolver
                        resolver = IdentityResolver(session)

                        # Create ParsedUrl-like object for CLZ
                        # (We don't have a real URL, but we can mock the structure)
                        from comic_identity_engine.services.url_parser import ParsedUrl

                        parsed_url = ParsedUrl(
                            platform="clz",
                            source_issue_id=candidate.source_issue_id,
                            source_series_id=candidate.source_series_id,
                        )

                        # Resolve the issue
                        result = await resolver.resolve_issue(
                            parsed_url=parsed_url,
                            upc=candidate.upc,
                            series_title=candidate.series_title,
                            series_start_year=candidate.series_start_year,
                            issue_number=candidate.issue_number,
                            cover_date=candidate.cover_date,
                        )

                        # Create external mapping if resolution succeeded
                        if result.issue_id:
                            await _ensure_source_mapping(
                                mapping_repo=mapping_repo,
                                issue_id=result.issue_id,
                                source="clz",
                                source_issue_id=candidate.source_issue_id,
                                source_series_id=candidate.source_series_id,
                            )

                            # Run cross-platform search
                            # (Reuse logic from resolve_identity_task)
                            # ...

                            resolved += 1
                        else:
                            failed += 1
                            errors.append({
                                "row": idx + 1,
                                "source_issue_id": candidate.source_issue_id,
                                "error": "Identity resolution failed",
                            })

                    processed += 1

                    # Update progress every 10 rows
                    if processed % 10 == 0:
                        progress_update = {
                            "total_rows": len(rows),
                            "processed": processed,
                            "resolved": resolved,
                            "failed": failed,
                        }
                        await operations_manager.update_operation(
                            operation_uuid, "running", result=progress_update
                        )

                except Exception as e:
                    failed += 1
                    processed += 1
                    error_msg = f"Row {idx + 1} error: {e}"
                    logger.error(error_msg)
                    errors.append({
                        "row": idx + 1,
                        "error": error_msg,
                    })

            result_dict = {
                "total_rows": len(rows),
                "processed": processed,
                "resolved": resolved,
                "failed": failed,
                "errors": errors,
                "summary": (
                    f"Processed {len(rows)} CLZ rows: {resolved} resolved, "
                    f"{failed} failed. {len(errors)} errors."
                ),
            }

            await operations_manager.mark_completed(operation_uuid, result_dict)

            return result_dict

        except Exception as e:
            # Error handling...
            pass
```

**Acceptance Criteria:**
- Uses `IdentityResolver.resolve_issue()` for each row
- Creates CLZ external mappings using Core ComicID
- Runs cross-platform search for each resolved issue
- Returns accurate counts: processed, resolved, failed
- Updates progress every 10 rows
- Handles errors gracefully per-row (doesn't abort entire import)

---

### Task 3: Update CLI Command to Match New Response Format

**File:** `comic_identity_engine/cli/commands/import_clz.py`

**Problem:**
- Expects old response format with `series_created`, `issues_created`, `variants_created`
- New response will have `processed`, `resolved`, `failed`

**Solution:**
Update `_display_import_result()` to handle new format:

```python
def _display_import_result(data: dict, console: Console, *, verbose: bool = False) -> None:
    """Display import results in a table format.

    Args:
        data: The operation response data containing the result
        console: Rich console for output
        verbose: Whether to show verbose output
    """
    result = data.get("response") or {}

    if not result:
        console.print("[red]No results found[/red]")
        return

    table = Table(title="CLZ Import Results")
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")

    total_rows = result.get("total_rows", 0)
    processed = result.get("processed", 0)
    resolved = result.get("resolved", 0)
    failed = result.get("failed", 0)
    errors = result.get("errors", [])
    summary = result.get("summary", "")

    table.add_row("Total Rows", str(total_rows))
    table.add_row("Processed", str(processed))
    table.add_row("Resolved", str(resolved))
    table.add_row("Failed", str(failed))

    if processed > 0 and resolved > 0:
        success_rate = (resolved / processed) * 100
        table.add_row("Success Rate", f"{success_rate:.1f}%")

    console.print(table)

    if summary:
        console.print(f"\n[dim]{summary}[/dim]")

    # Verbose error display...
```

**Acceptance Criteria:**
- Displays new metrics: total_rows, processed, resolved, failed
- Calculates and displays success rate
- Shows errors in verbose mode
- Handles missing fields gracefully

---

### Task 4: Add Helper Function for CLZ ParsedUrl Creation

**File:** `comic_identity_engine/services/url_parser.py` (or new utility module)

**Problem:**
- IdentityResolver expects a ParsedUrl object
- CLZ imports don't have real URLs
- Need to create ParsedUrl from IssueCandidate

**Solution:**
```python
def create_clz_parsed_url(candidate: IssueCandidate) -> ParsedUrl:
    """Create a ParsedUrl for CLZ CSV import.

    Args:
        candidate: IssueCandidate from CLZ CSV row

    Returns:
        ParsedUrl with platform="clz" and source IDs from candidate
    """
    return ParsedUrl(
        platform="clz",
        source_issue_id=candidate.source_issue_id,
        source_series_id=candidate.source_series_id,
    )
```

**Acceptance Criteria:**
- Creates valid ParsedUrl for CLZ imports
- Uses Core ComicID from IssueCandidate
- Can be imported and used in import_clz_task

---

### Task 5: Testing and Validation

**Test Cases:**

1. **Unit Test: CLZAdapter.fetch_issue_from_csv_row()**
   - Verify Core ComicID extraction
   - Verify ValidationError when Core ComicID missing
   - Verify returned IssueCandidate has correct source_issue_id

2. **Integration Test: import_clz_task**
   - Load small CSV (10 rows)
   - Verify all rows processed
   - Verify external mappings created for resolved issues
   - Verify cross-platform mappings created
   - Verify progress updates every 10 rows

3. **End-to-End Test: CLI**
   - Run `cie-import-clz test.csv`
   - Verify CLI displays correct metrics
   - Verify success rate calculated correctly
   - Test with `--verbose` flag

4. **Cross-User Test: Shared Identity Graph**
   - User A imports CSV with Core ComicID "60070"
   - Verify CLZ external mapping created
   - Verify cross-platform mappings found
   - User B imports CSV with same Core ComicID "60070"
   - Verify existing mapping found immediately
   - Verify no redundant cross-platform searches

---

## Rollout Plan

1. **Phase 1: Core Changes**
   - Modify CLZAdapter to extract Core ComicID
   - Redesign import_clz_task
   - Add helper function for ParsedUrl creation

2. **Phase 2: CLI Updates**
   - Update CLI to match new response format
   - Update progress display logic

3. **Phase 3: Testing**
   - Unit tests for CLZAdapter
   - Integration tests for import_clz_task
   - End-to-end tests for CLI
   - Cross-user identity graph validation

4. **Phase 4: Documentation**
   - Update IMPLEMENTATION_SUMMARY.md
   - Add CLI usage examples
   - Document the shared identity graph behavior

---

## Success Criteria

✅ CLZ CSV imports create external mappings using Core ComicID
✅ Each row goes through identity resolution pipeline
✅ Cross-platform search runs for each resolved issue
✅ External mappings are shared across users
✅ Subsequent imports of same Core ComicID hit cache
✅ CLI displays accurate metrics (processed, resolved, failed, success rate)
✅ Error handling is graceful (per-row, not abort entire import)

---

## Files to Modify

1. `comic_identity_engine/adapters/clz.py` - Extract Core ComicID
2. `comic_identity_engine/jobs/tasks.py` - Redesign import_clz_task
3. `comic_identity_engine/cli/commands/import_clz.py` - Update display logic
4. `comic_identity_engine/services/url_parser.py` - Add helper function (optional)

---

## Backwards Compatibility

⚠️ **Breaking Change:** The response format from `import_clz_task` will change from:
- Old: `{series_created, issues_created, variants_created}`
- New: `{processed, resolved, failed}`

This requires updating the CLI command. No API contract changes since this is an internal task.
