#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

if [ $# -ne 1 ]; then
  echo "Usage: bash scripts/import-remediation-check.sh <step>"
  exit 2
fi

step="$1"

run() {
  echo "+ $*"
  "$@"
}

head_python_files() {
  git show --name-only --format= HEAD -- '*.py' | sed '/^$/d'
}

lint_head_python_files() {
  mapfile -t python_files < <(head_python_files)

  if [ "${#python_files[@]}" -eq 0 ]; then
    echo "+ no Python files changed in HEAD"
    return 0
  fi

  run uv run ruff check "${python_files[@]}"
  run uv run ruff format --check "${python_files[@]}"
}

common_checks() {
  run git diff --check
  lint_head_python_files
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
