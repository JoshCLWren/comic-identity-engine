#!/usr/bin/env bash
set -euo pipefail

source "$PWD/scripts/ensure-local-venv.sh"
cie_ensure_local_venv "$PWD"

"$PWD/.venv/bin/pytest" --cov=comic_identity_engine --cov-report=xml --cov-report=term-missing
