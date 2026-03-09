#!/usr/bin/env bash
# Import remediation loop. Runs each remediation step through Codex CLI and
# verifies the repo after every step to keep broken state from propagating.
# Usage: bash scripts/import-remediation-loop.sh
# Requires: codex CLI installed, authenticated (codex login)
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

TRACKER="IMPORT_REMEDIATION_TODO.md"
BRANCH="import-remediation/complete-import-hardening"
STEP_CHECK_SCRIPT="scripts/import-remediation-check.sh"
FINAL_VERIFY_SCRIPT="scripts/import-remediation-verify.sh"
BASE_HEAD_FILE=".git/import-remediation-base-head"
LOG_DIR="${CIE_IMPORT_REMEDIATION_LOG_DIR:-/tmp}"
MAX_REPAIR_ATTEMPTS="${CIE_IMPORT_REMEDIATION_MAX_REPAIR_ATTEMPTS:-3}"

if git checkout -b "${BRANCH}" 2>/dev/null; then
  git rev-parse HEAD > "${BASE_HEAD_FILE}"
else
  git checkout "${BRANCH}"
fi

if [ ! -f "${BASE_HEAD_FILE}" ]; then
  if git rev-parse --verify main >/dev/null 2>&1; then
    git merge-base HEAD main > "${BASE_HEAD_FILE}"
  else
    git rev-parse HEAD > "${BASE_HEAD_FILE}"
  fi
fi

repo_status() {
  git status --porcelain=v1
}

step_output_file() {
  local step_name="$1"
  echo "${LOG_DIR}/import-remediation-${step_name}.md"
}

step_check_log_file() {
  local step_name="$1"
  echo "${LOG_DIR}/import-remediation-${step_name}-check.log"
}

step_repair_output_file() {
  local step_name="$1"
  local attempt="$2"
  echo "${LOG_DIR}/import-remediation-${step_name}-repair-${attempt}.md"
}

base_head() {
  cat "${BASE_HEAD_FILE}"
}

find_step_commit() {
  local expected_commit="$1"

  git log --format='%H%x09%s' "$(base_head)"..HEAD | awk -F'\t' -v msg="${expected_commit}" '$2 == msg { print $1; exit }'
}

verify_step_commit() {
  local step_name="$1"
  local expected_commit="$2"
  local previous_head="$3"
  local baseline_status="$4"
  local current_head
  local current_subject
  local current_status

  current_head="$(git rev-parse HEAD)"
  if [ "${current_head}" = "${previous_head}" ]; then
    echo "Step ${step_name} did not create a new commit"
    exit 1
  fi

  current_subject="$(git log -1 --pretty=%s)"
  if [ "${current_subject}" != "${expected_commit}" ]; then
    echo "Step ${step_name} produced unexpected commit message"
    echo "Expected: ${expected_commit}"
    echo "Actual:   ${current_subject}"
    exit 1
  fi

  if ! git show --name-only --format= "${current_head}" | rg -Fxq "${TRACKER}"; then
    echo "Step ${step_name} commit did not update ${TRACKER}"
    exit 1
  fi

  current_status="$(repo_status)"
  if [ "${current_status}" != "${baseline_status}" ]; then
    echo "Step ${step_name} left unexpected worktree changes"
    echo "Baseline status:"
    printf '%s\n' "${baseline_status}"
    echo "Current status:"
    printf '%s\n' "${current_status}"
    exit 1
  fi
}

run_step_check() {
  local step_name="$1"
  local step_commit="$2"
  local check_log

  check_log="$(step_check_log_file "${step_name}")"
  bash "${STEP_CHECK_SCRIPT}" "${step_name}" "${step_commit}" 2>&1 | tee "${check_log}"
}

attempt_step_repair() {
  local step_name="$1"
  local expected_commit="$2"
  local step_prompt="$3"
  local step_commit="$4"
  local attempt="$5"
  local failure_mode="$6"
  local failure_log="$7"
  local repair_output
  local verification_command

  repair_output="$(step_repair_output_file "${step_name}" "${attempt}")"

  if [ -n "${step_commit}" ]; then
    verification_command="bash ${STEP_CHECK_SCRIPT} ${step_name} ${step_commit}"
  else
    verification_command="bash ${STEP_CHECK_SCRIPT} ${step_name}"
  fi

  codex exec \
    --full-auto \
    -o "${repair_output}" \
    "Repair ${step_name} after ${failure_mode} failure. Read AGENTS.md, ${TRACKER}, ${failure_log}, and the current branch state first. The original step prompt was: ${step_prompt} The required primary commit subject for this step is '${expected_commit}'. Do not move on to later steps. Make the smallest focused fix needed so ${verification_command} passes. If the primary commit does not exist yet, create it with the required subject. If you need a follow-up commit, use subject 'Repair ${step_name} verification'. Leave the worktree clean."
}

STEPS=(
  "step1|Cap import worker concurrency and configure DB pool|Fix Priority 0 in ${TRACKER}. Cap worker concurrency to fit the SQLAlchemy pool and make DB pool sizing configurable. Update the tracker status markers as you go. Add tests where appropriate. Run: uv run pytest tests/test_config.py tests/test_jobs/test_worker.py -q. Commit with message 'Cap import worker concurrency and configure DB pool'. Read AGENTS.md and ${TRACKER} first."

  "step2|Add resumable checksum-based CLZ import idempotency|Fix the checksum-based idempotency work in Priority 1 of ${TRACKER}. Replace force-new import submission with resumable same-file identity, persist import fingerprint metadata, and update tracker markers. Add or update tests for import routes and operations manager. Run: uv run pytest tests/test_api/test_import_router.py tests/test_api/test_jobs_router.py tests/test_services/test_operations.py -q. Commit with message 'Add resumable checksum-based CLZ import idempotency'. Read AGENTS.md and ${TRACKER} first."

  "step3|Add CLZ import resume and retry-failed CLI flow|Implement retry-failed-only and CLI attach/resume support from Priority 1 of ${TRACKER}. The CLI must be able to monitor an existing operation without creating a new import. Update the tracker markers. Run: uv run pytest tests/test_cli/test_import_clz.py tests/test_integration/test_clz_import.py -q. Commit with message 'Add CLZ import resume and retry-failed CLI flow'. Read AGENTS.md and ${TRACKER} first."

  "step4|Harden canonical series and issue creation against races|Fix Priority 2 in ${TRACKER}. Add DB uniqueness for canonical series and issues, create the migration, and make series/issue creation race-safe. Update the tracker markers. Add regression coverage. Run: uv run pytest tests/test_database_models.py tests/test_jobs/test_tasks.py -q. Commit with message 'Harden canonical series and issue creation against races'. Read AGENTS.md and ${TRACKER} first."

  "step5|Add duplicate audit and repair tooling for canonical imports|Fix Priorities 3 and 4 in ${TRACKER}. Tighten fallback canonical creation, add duplicate audit tooling, and add merge/repair tooling for existing bad canonicals. Update the tracker markers. Run: uv run pytest tests/test_jobs/test_tasks.py -q. Commit with message 'Add duplicate audit and repair tooling for canonical imports'. Read AGENTS.md and ${TRACKER} first."

  "step6|Complete import remediation hardening coverage|Finish Priority 5 in ${TRACKER}. Add concurrency/resume tests and operational visibility for imports. Update tracker markers and run the relevant focused test suite for this step. Leave final full verification to ${FINAL_VERIFY_SCRIPT}. Commit with message 'Complete import remediation hardening coverage'. Read AGENTS.md and ${TRACKER} first."
)

echo "=== Import Remediation Loop ==="
echo "Tracker: ${TRACKER}"
echo "Steps: ${#STEPS[@]}"
echo "Max repair attempts per step: ${MAX_REPAIR_ATTEMPTS}"
echo ""

for entry in "${STEPS[@]}"; do
  name="${entry%%|*}"
  remainder="${entry#*|}"
  expected_commit="${remainder%%|*}"
  prompt="${remainder#*|}"
  step_commit=""
  repair_attempt=0

  echo "=================================================="
  echo "Running: ${name}"
  echo "=================================================="

  while true; do
    step_commit="$(find_step_commit "${expected_commit}")"

    if [ -n "${step_commit}" ]; then
      echo "Found existing commit for ${name}: ${step_commit}"
    else
      previous_head="$(git rev-parse HEAD)"
      baseline_status="$(repo_status)"
      output_file="$(step_output_file "${name}")"

      if codex exec \
        --full-auto \
        -o "${output_file}" \
        "${prompt}"
      then
        echo "${name} completed"
        verify_step_commit "${name}" "${expected_commit}" "${previous_head}" "${baseline_status}"
        step_commit="$(find_step_commit "${expected_commit}")"
      else
        exit_code=$?
        repair_attempt=$((repair_attempt + 1))
        if [ "${repair_attempt}" -gt "${MAX_REPAIR_ATTEMPTS}" ]; then
          echo "${name} failed after ${MAX_REPAIR_ATTEMPTS} repair attempts"
          echo "   Check ${output_file} for details"
          exit "${exit_code}"
        fi

        echo "${name} execution failed; attempting automated repair (${repair_attempt}/${MAX_REPAIR_ATTEMPTS})"
        attempt_step_repair \
          "${name}" \
          "${expected_commit}" \
          "${prompt}" \
          "" \
          "${repair_attempt}" \
          "execution" \
          "${output_file}"
        continue
      fi
    fi

    echo "Running remediation check for ${name}"

    if run_step_check "${name}" "${step_commit}"; then
      echo "Verification passed for ${name}"
      echo ""
      break
    fi

    exit_code=$?
    repair_attempt=$((repair_attempt + 1))
    if [ "${repair_attempt}" -gt "${MAX_REPAIR_ATTEMPTS}" ]; then
      echo "Verification failed for ${name} after ${MAX_REPAIR_ATTEMPTS} repair attempts"
      echo "Fix the repo state before continuing to the next step"
      exit "${exit_code}"
    fi

    echo "Verification failed for ${name}; attempting automated repair (${repair_attempt}/${MAX_REPAIR_ATTEMPTS})"
    attempt_step_repair \
      "${name}" \
      "${expected_commit}" \
      "${prompt}" \
      "${step_commit}" \
      "${repair_attempt}" \
      "verification" \
      "$(step_check_log_file "${name}")"
  done
done

echo ""
echo "=== All steps complete ==="
echo "Running final verification:"
bash "${FINAL_VERIFY_SCRIPT}"
