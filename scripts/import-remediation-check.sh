#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

CACHE_ROOT="$PWD/.cache/import-remediation"
export UV_CACHE_DIR="${CACHE_ROOT}/uv"
export RUFF_CACHE_DIR="${CACHE_ROOT}/ruff"
mkdir -p "${UV_CACHE_DIR}" "${RUFF_CACHE_DIR}"

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
  echo "Usage: bash scripts/import-remediation-check.sh <step> [commit]"
  exit 2
fi

step="$1"
commit_ref="${2:-HEAD}"

run() {
  echo "+ $*"
  "$@"
}

commit_python_files() {
  git show --name-only --format= "${commit_ref}" -- '*.py' | sed '/^$/d'
}

lint_commit_python_files() {
  mapfile -t python_files < <(commit_python_files)

  if [ "${#python_files[@]}" -eq 0 ]; then
    echo "+ no Python files changed in ${commit_ref}"
    return 0
  fi

  run uv run ruff check "${python_files[@]}"
  run uv run ruff format --check "${python_files[@]}"
}

common_checks() {
  run git diff --check
  lint_commit_python_files
}

case "${step}" in
  step1)
    common_checks
    run uv run pytest tests/test_config.py tests/test_jobs/test_worker.py -q
    ;;
  step2)
    common_checks
    run uv run pytest tests/test_api/test_import_router.py tests/test_api/test_jobs_router.py tests/test_services/test_operations.py -q
    ;;
  step3)
    common_checks
    run uv run pytest tests/test_cli/test_import_clz.py tests/test_integration/test_clz_import.py -q
    ;;
  step4)
    common_checks
    run uv run pytest tests/test_database_models.py tests/test_jobs/test_tasks.py -q
    ;;
  step5)
    common_checks
    run uv run pytest tests/test_jobs/test_tasks.py -q
    ;;
  step6)
    common_checks
    run uv run pytest tests/test_config.py tests/test_jobs/test_worker.py tests/test_api/test_import_router.py tests/test_api/test_jobs_router.py tests/test_services/test_operations.py tests/test_cli/test_import_clz.py tests/test_integration/test_clz_import.py tests/test_database_models.py tests/test_jobs/test_tasks.py -q
    ;;
  *)
    echo "Unknown remediation step: ${step}"
    exit 2
    ;;
esac
