# CLZ Batch Import Implementation

## Summary

This implementation adds batch CLZ CSV import functionality to the Comic Identity Engine through the existing queue + worker pipeline.

## Components Added

### 1. API Router (`comic_identity_engine/api/routers/import_router.py`)

**Endpoint:** `POST /api/v1/import/clz`

Accepts a CLZ CSV file path and enqueues an `import_clz_task` for background processing.

**Request:**
```json
{
  "file_path": "/path/to/collection.csv"
}
```

**Response:** Returns an operation ID for polling (follows AIP-151 LRO pattern)

**Status Endpoint:** `GET /api/v1/import/clz/{operation_id}`

### 2. CLI Command (`comic_identity_engine/cli/commands/import_clz.py`)

**Command:** `cie-import-clz <csv_path>`

**Features:**
- Validates CSV file exists before submission
- Submits to API for background processing
- Polls for completion with progress bar
- Displays results table showing:
  - Total rows processed
  - Series/issues/variants created
  - Errors encountered
- Supports `--no-wait` for fire-and-forget mode
- Supports `--verbose` for detailed output
- Supports `--api-url` for non-local deployments

## Usage

### Basic Import

```bash
cie-import-clz clz_export_all_columns.csv
```

This will:
1. Submit the CSV to the API
2. Wait for completion (up to 10 minutes)
3. Display results table

### Non-Wait Mode

```bash
cie-import-clz clz_export.csv --no-wait
```

Returns immediately with operation ID for manual polling.

### Custom API Endpoint

```bash
cie-import-clz clz_export.csv --api-url http://prod-server:8000
```

### Verbose Output

```bash
cie-import-clz clz_export.csv --verbose
```

Shows detailed progress and error information.

## Architecture Flow

```
CLI → API (POST /api/v1/import/clz)
    → OperationsManager creates operation
    → JobQueue.enqueue_import_clz()
    → Redis Queue
    → Worker (import_clz_task)
    → CLZAdapter.load_csv_from_file()
    → Parse rows with CLZAdapter.fetch_issue_from_csv_row()
    → Create SeriesRun/Issue/Variant in DB
    → OperationsManager.mark_completed()
    → CLI polls GET /api/v1/import/clz/{operation_id}
    → Display results
```

## Existing Components Used

1. **CLZAdapter** (`comic_identity_engine/adapters/clz.py`)
   - `load_csv_from_file()` - Reads CSV
   - `fetch_issue_from_csv_row()` - Parses rows into IssueCandidate

2. **JobQueue** (`comic_identity_engine/jobs/queue.py`)
   - `enqueue_import_clz()` - Queues the background job

3. **Tasks** (`comic_identity_engine/jobs/tasks.py`)
   - `import_clz_task` - Processes CSV in background worker
   - Creates series, issues, and variants in database
   - Updates operation progress

4. **OperationsManager** - Tracks long-running operation status

## Example Output

```
cie-import-clz clz_export.csv
╭──────────────────────────────────────────────────────────╮
│              CLZ Import Results                          │
├────────────────────┬─────────────────────────────────────┤
│ Metric             │ Value                               │
├────────────────────┼─────────────────────────────────────┤
│ Total Rows         │ 5200                                │
│ Series Created     │ 924                                 │
│ Issues Created     │ 5200                                │
│ Variants Created   │ 127                                 │
│ Errors             │ 3                                   │
╰────────────────────┴─────────────────────────────────────╯

Imported 5200 rows: 924 series, 5200 issues, 127 variants created. 3 errors.
```

## Files Modified

1. **Created:** `comic_identity_engine/api/routers/import_router.py`
   - New API endpoints for CLZ import

2. **Created:** `comic_identity_engine/cli/commands/import_clz.py`
   - CLI command implementation

3. **Modified:** `comic_identity_engine/api/routers/__init__.py`
   - Registered import_router in all_routers

## Testing

To test the implementation:

1. Start the infrastructure:
```bash
docker compose up -d postgres-app redis
```

2. Start the API:
```bash
uv run cie-api
```

3. Start the worker:
```bash
uv run cie-worker
```

4. Run the import:
```bash
cie-import-clz /mnt/extra/josh/code/clz_export_all_columns.csv --verbose
```

## Future Enhancements

Not included in this implementation but could be added later:

- `--limit` flag to process only N rows
- `--dry-run` flag to validate CSV without importing
- `--concurrency` flag to control worker parallelism
- Support for other CSV formats (not just CLZ)
- Progress resumption for interrupted imports
