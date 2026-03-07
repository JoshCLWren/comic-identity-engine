#!/usr/bin/env bash
set -euo pipefail

source "$PWD/scripts/ensure-local-venv.sh"
cie_ensure_local_venv "$PWD"

"$PWD/.venv/bin/ruff" check .
"$PWD/.venv/bin/ruff" format --check .
