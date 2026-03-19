#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

MODE="--all"
if [ $# -ge 1 ]; then
    case "$1" in
        --all|--staged)
            MODE="$1"
            ;;
        *)
            echo "Usage: bash scripts/lint.sh [--all|--staged]"
            exit 2
            ;;
    esac
fi

echo "Running code quality checks..."

# Ensure we're running at repo root
if [ ! -f "pyproject.toml" ]; then
    echo "${RED}ERROR: Run from repository root.${NC}"
    exit 1
fi


# Activate venv if not already active
if [ -z "$VIRTUAL_ENV" ]; then
    VENV_PATH=".venv/bin/activate"
    # Handle git worktrees: check if venv exists in main repo
    if [ ! -f "$VENV_PATH" ] && [ -f .git ]; then
        GIT_COMMON_DIR=$(git rev-parse --git-common-dir 2>/dev/null)
        if [ -n "$GIT_COMMON_DIR" ]; then
            MAIN_REPO_DIR=$(dirname "$GIT_COMMON_DIR")
            if [ -f "$MAIN_REPO_DIR/.venv/bin/activate" ]; then
                VENV_PATH="$MAIN_REPO_DIR/.venv/bin/activate"
                echo "Activating venv from main repo: $MAIN_REPO_DIR"
            fi
        fi
    fi

    if [ -f "$VENV_PATH" ]; then
        source "$VENV_PATH"
    else
        # In CI, tools may already be in PATH (e.g., from Docker image)
        if [ -n "${CI:-}" ]; then
            # Verify required tools are available
            if ! command -v ruff >/dev/null 2>&1; then
                echo "ERROR: ruff not found in PATH (CI environment)"
                echo "Current PATH: $PATH"
                exit 1
            fi
            if ! command -v python >/dev/null 2>&1; then
                echo "ERROR: python not found in PATH (CI environment)"
                echo "Current PATH: $PATH"
                exit 1
            fi
            echo "CI environment: Using tools from PATH"
        else
            echo "No virtual environment found. Please run 'uv venv && uv sync' first."
            exit 1
        fi
    fi
fi

STAGED_FILES=""
STAGED_PYTHON_FILES=""

if [ "$MODE" = "--staged" ]; then
    STAGED_FILES=$(git diff --name-only --cached --diff-filter=ACMRT || true)
    if [ -z "$STAGED_FILES" ]; then
        echo -e "${YELLOW}No staged files found.${NC}"
        exit 0
    fi

    # Filter for Python files only
    STAGED_PYTHON_FILES=$(echo "$STAGED_FILES" | grep -E '\.py$' || true)
    if [ -z "$STAGED_PYTHON_FILES" ]; then
        echo -e "${GREEN}No Python files staged.${NC}"
        exit 0
    fi

    echo "Checking ${STAGED_PYTHON_FILES}"
fi

# Check for type/linter ignores in staged files
if [ "$MODE" = "--staged" ]; then
    echo "Checking for type/linter ignores..."
    IGNORES_FOUND=0

    for file in $STAGED_PYTHON_FILES; do
        if [ -f "$file" ]; then
            # Check for various ignore patterns
            if grep -q '# type: ignore' "$file" 2>/dev/null; then
                echo -e "${RED}ERROR: Type ignore found in $file${NC}"
                IGNORES_FOUND=1
            fi
            if grep -q '# noqa' "$file" 2>/dev/null; then
                echo -e "${RED}ERROR: Linter ignore found in $file${NC}"
                IGNORES_FOUND=1
            fi
            if grep -q '# ruff: ignore' "$file" 2>/dev/null; then
                echo -e "${RED}ERROR: Ruff ignore found in $file${NC}"
                IGNORES_FOUND=1
            fi
            if grep -q '# pylint: ignore' "$file" 2>/dev/null; then
                echo -e "${RED}ERROR: Pylint ignore found in $file${NC}"
                IGNORES_FOUND=1
            fi
        fi
    done

    if [ $IGNORES_FOUND -eq 1 ]; then
        echo -e "${RED}ERROR: Type/linter ignores are not allowed in commits.${NC}"
        echo "Remove the ignores or use --no-verify to bypass (not recommended)."
        exit 1
    fi
fi

# Python compilation check
echo "Checking Python syntax..."
if [ "$MODE" = "--staged" ] && [ -n "$STAGED_PYTHON_FILES" ]; then
    # Check only staged Python files
    for file in $STAGED_PYTHON_FILES; do
        if [ -f "$file" ]; then
            python -m py_compile "$file"
        fi
    done
else
    # Check all Python files
    python -m compileall comic_identity_engine tests -q
fi

# Ruff linting
echo "Running ruff..."
if ! uv run ruff check .; then
    echo -e "${RED}ERROR: Ruff linting failed${NC}"
    echo "Run 'uv run ruff check --fix .' to auto-fix issues."
    exit 1
fi

# Check for Any types (ANN401 rule)
echo "Checking for Any type usage..."
if uv run ruff check . --select ANN401; then
    echo -e "${RED}ERROR: Any type found${NC}"
    echo "Use specific types instead of Any."
    exit 1
fi

# Type checking with ty (if available)
if command -v ty >/dev/null 2>&1; then
    echo "Running type checker..."
    if ! uv run ty check --error-on-warning comic_identity_engine tests; then
        echo -e "${RED}ERROR: Type checking failed${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}WARNING: ty not found, skipping type checking${NC}"
    echo "Install with: uv add --dev ty"
fi

# Format check
echo "Checking code formatting..."
if ! uv run ruff format --check .; then
    echo -e "${RED}ERROR: Code formatting issues found${NC}"
    echo "Run 'uv run ruff format .' to fix formatting."
    exit 1
fi

echo -e "${GREEN}All checks passed!${NC}"
