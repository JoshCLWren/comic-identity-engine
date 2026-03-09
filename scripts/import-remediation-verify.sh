#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

CACHE_ROOT="$PWD/.cache/import-remediation"
export UV_CACHE_DIR="${CACHE_ROOT}/uv"
export RUFF_CACHE_DIR="${CACHE_ROOT}/ruff"
mkdir -p "${UV_CACHE_DIR}" "${RUFF_CACHE_DIR}"

BASE_HEAD_FILE=".git/import-remediation-base-head"

run() {
  echo "+ $*"
  "$@"
}

branch_python_files() {
  local base_head

  if [ -f "${BASE_HEAD_FILE}" ]; then
    base_head="$(cat "${BASE_HEAD_FILE}")"
    git diff --name-only "${base_head}..HEAD" -- '*.py' | sed '/^$/d'
    return 0
  fi

  git show --name-only --format= HEAD -- '*.py' | sed '/^$/d'
}

lint_branch_python_files() {
  mapfile -t python_files < <(branch_python_files)

  if [ "${#python_files[@]}" -eq 0 ]; then
    echo "+ no Python files changed in remediation branch"
    return 0
  fi

  run uv run ruff check "${python_files[@]}"
  run uv run ruff format --check "${python_files[@]}"
}

echo "=== Import remediation final verification ==="

echo "Running focused remediation verification"
bash scripts/import-remediation-check.sh step6

echo "Running branch-wide Python lint for remediation changes"
lint_branch_python_files

echo "Checking remediation tracker is fully complete"
if rg -n '^- \[\s\]|^- \[-\]|^- \[!\]' IMPORT_REMEDIATION_TODO.md; then
  echo "IMPORT_REMEDIATION_TODO.md still has unfinished items"
  exit 1
fi

echo "Running full repository CI checks"
bash scripts/ci.sh

echo "Import remediation verification completed successfully"
