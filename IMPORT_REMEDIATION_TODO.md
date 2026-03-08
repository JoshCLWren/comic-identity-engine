# Import Remediation Todo

Status markers:
- `[ ]` not started
- `[-]` in progress
- `[x]` completed
- `[!]` blocked or needs investigation

## Current State
- `external_mappings` are protected against duplicate `(source, source_issue_id)` rows.
- Canonical `series_runs` and `issues` are not protected by database uniqueness today.
- The live database already contains duplicate canonical rows.
- Multi-worker imports are overrunning the SQLAlchemy pool and producing `QueuePool limit` timeouts.
- Import submission currently lacks useful resume semantics for same-file retries.

## Priority 0: Stop Active Data Damage
- [x] Cap worker concurrency to the database pool.
  Success criteria:
  No `QueuePool limit of size 10 overflow 20 reached` errors during a multi-worker import.
- [x] Make database pool sizing configurable in application settings and engine setup.
  Success criteria:
  `pool_size`, `max_overflow`, and `pool_timeout` are controlled by env/config instead of hardcoded values.

## Priority 1: Restore Import Idempotency
- [ ] Replace `force=True` import submission with checksum-based import identity.
  Success criteria:
  Re-submitting the same file returns or resumes the same logical import operation.
- [ ] Persist import fingerprints and row manifests on the operation.
  Success criteria:
  Operation state includes file checksum, total row count, and stable per-row source identifiers.
- [ ] Add explicit resume semantics for incomplete imports.
  Success criteria:
  A stuck or interrupted same-file import can be resumed without creating a fresh operation id.
- [ ] Add retry-failed-only semantics.
  Success criteria:
  Same-file retry can requeue failed rows without resubmitting already-resolved work.
- [ ] Add CLI attach/resume support.
  Success criteria:
  CLI can monitor an existing operation id without re-posting the file.

## Priority 2: Make Canonical Creation Race-Safe
- [ ] Add database uniqueness for `series_runs(title, start_year)`.
  Success criteria:
  DB rejects duplicate canonical series rows for the same title/year.
- [ ] Add database uniqueness for `issues(series_run_id, issue_number)`.
  Success criteria:
  DB rejects duplicate canonical issue rows within the same canonical series.
- [ ] Make series creation race-safe.
  Success criteria:
  Concurrent imports refetch the winner instead of creating sibling `series_runs`.
- [ ] Make issue creation race-safe.
  Success criteria:
  Concurrent imports refetch the winner instead of creating sibling `issues`.

## Priority 3: Improve Matching Quality
- [ ] Revisit fallback canonical creation for `"Unknown Series"` and year `2000`.
  Success criteria:
  Weak matches no longer silently create garbage canonicals with default metadata.
- [ ] Distinguish true issue duplicates from unmodeled variants.
  Success criteria:
  Rows with different UPCs but same canonical issue identity are either modeled as variants or rejected for review.

## Priority 4: Repair Existing Damage
- [ ] Add duplicate-audit tooling for `series_runs` and `issues`.
  Success criteria:
  Tool reports duplicate groups, mappings, and proposed merge targets.
- [ ] Add dedupe/merge tooling to re-point mappings and remove loser rows.
  Success criteria:
  Existing duplicate canonicals can be merged safely in a repeatable way.

## Priority 5: Test and Operations Hardening
- [ ] Add tests for concurrent import races.
  Success criteria:
  Tests reproduce and then prevent duplicate series/issue creation under parallel workers.
- [ ] Add tests for resume and retry flows.
  Success criteria:
  Same-file resume and retry-failed-only flows are covered end-to-end.
- [ ] Add import health visibility.
  Success criteria:
  Logs or status endpoints expose queue depth, active row count, failed row count, and retry state.

## Completed Already
- [x] Parent import operation progress is updated by row tasks.
- [x] CLI progress reads API operation state instead of scraping Redis job results.
- [x] Import routes have regression coverage for the current submission behavior.
- [x] Remediation workflow has per-step and final verification scripts plus commit enforcement to catch regressions early.
