# Safety Guardrails TODO
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


## Problem
No automated guardrails to prevent accidental data destruction in production database.

## Priority Items

### 1. Environment Separation [HIGH]
- [ ] Create `.env.test`, `.env.development`, `.env.production`
- [ ] Add `docker-compose.override.yml` for different environments
- [ ] Add environment name to all prompts/logs
- [ ] Add color-coded terminal prompts (red for prod, green for test)
- [ ] Create `scripts/env-check.sh` - fail if connecting to prod without explicit flag

### 2. Makefile with Safe Commands [HIGH]
- [ ] Create `Makefile` with environment-aware targets:
  ```makefile
  make db-shell-test    # Only test database
  make db-shell-dev     # Only dev database
  make db-reset-test    # Safe - only test DB
  make import-test      # Use test CSV file
  make import-prod      # Require --force flag
  make db-backup        # Automatic backup before destructive ops
  ```
- [ ] Add confirmation prompts for all destructive operations
- [ ] Add `DRY_RUN` flag support

### 3. Pre-commit Hooks [MEDIUM]
- [ ] Install pre-commit hooks: `pre-commit install`
- [ ] Add hook to check for production DB access
- [ ] Add hook to run linters (ruff, mypy)
- [ ] Add hook to prevent direct DB commits in code
- [ ] Add hook to validate no hardcoded prod credentials

### 4. Integration Tests [HIGH]
- [ ] Create `tests/integration/` directory
- [ ] Add test database fixture using `comic_identity_test`
- [ ] Add test for bulk_find_by_series_issue with real DB
- [ ] Add test for CLZ import with real DB
- [ ] Add test that production DB is never touched in tests
- [ ] Run integration tests in CI with test database

### 5. Destructive Operation Safeguards [HIGH]
- [ ] Add `--force` flag requirement for:
  - `DELETE` operations on production database
  - `DROP` operations on production database
  - `TRUNCATE` operations
- [ ] Add backup requirement:
  ```python
  if not recent_backup_exists():
      raise Error("Cannot delete: no backup in 24 hours. Run make db-backup first.")
  ```
- [ ] Add database name checks in repository methods:
  ```python
  def delete(self, id):
      if "comic_identity_test" not in self.database_url:
          raise Error("DELETE only allowed on test database")
  ```

### 6. CI/CD Pipeline Protections [MEDIUM]
- [ ] Add `.github/workflows/safety-checks.yml`
- [ ] Fail PR if production DB credentials detected
- [ ] Fail PR if direct SQL DELETE statements added
- [ ] Run integration tests on every PR
- [ ] Add database migration review required

### 7. Database Backup Automation [MEDIUM]
- [ ] Add `make db-backup` command
- [ ] Automatic backup before schema changes
- [ ] Automatic backup before bulk DELETE
- [ ] Backup retention policy (keep 7 daily, 4 weekly)
- [ ] Backup restoration test

### 8. Documentation [LOW]
- [ ] Add `DEVELOPMENT.md` - how to safely develop
- [ ] Add `DATABASE_SAFETY.md` - rules for DB operations
- [ ] Add `ENVIRONMENTS.md` - explain dev/test/prod separation
- [ ] Add warning signs to README about production database
- [ ] Document how to recover from accidental deletion

### 9. Code Review Checklists [LOW]
- [ ] Add PR template with safety checklist
- [ ] Checklist item: "Does this touch production database?"
- [ ] Checklist item: "Are integration tests updated?"
- [ ] Checklist item: "Is backup available?"

### 10. Monitoring and Alerts [LOW]
- [ ] Add alert for production database DELETE operations
- [ ] Add alert for bulk data modifications
- [ ] Add operation logging to separate audit file
- [ ] Add notification for schema changes

## Implementation Order

1. **Week 1**: Environment separation + Makefile (stop bleeding)
2. **Week 2**: Integration tests + Destructive operation guards (prevent future issues)
3. **Week 3**: Pre-commit hooks + CI protections (automated enforcement)
4. **Week 4**: Documentation + Monitoring + Backups (process & safety net)

## Success Criteria
- [ ] No accidental production database modifications
- [ ] All destructive ops require explicit `--force` flag
- [ ] Integration tests catch real DB issues
- [ ] Pre-commit hooks prevent dangerous code
- [ ] Clear visual indicators of current environment
- [ ] Automatic backups before any destructive operation
