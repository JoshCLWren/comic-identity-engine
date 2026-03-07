#!/usr/bin/env bash

# Source this file and call cie_ensure_local_venv <project_root> to guarantee
# that the current shell is using the project's own .venv instead of any
# inherited container or unrelated virtualenv.

_cie_remove_path_entry() {
    local target="$1"
    export PATH="$(
        python3 - "$PATH" "$target" <<'PY'
import sys

path, target = sys.argv[1], sys.argv[2]
parts = [part for part in path.split(":") if part and part != target]
print(":".join(parts))
PY
    )"
}


cie_ensure_local_venv() {
    local project_root="${1:-$PWD}"
    local project_venv=""

    project_root="$(cd "$project_root" && pwd)"
    project_venv="${project_root}/.venv"

    if [[ -n "${VIRTUAL_ENV:-}" && "${VIRTUAL_ENV}" != "${project_venv}" ]]; then
        _cie_remove_path_entry "${VIRTUAL_ENV}/bin"
        unset VIRTUAL_ENV
    fi

    _cie_remove_path_entry "/app/.venv/bin"
    export UV_PROJECT_ENVIRONMENT="${project_venv}"

    if [[ ! -x "${project_venv}/bin/python" ]] || \
        ! "${project_venv}/bin/python" -c "import sys" >/dev/null 2>&1; then
        (
            cd "$project_root" &&
                uv sync --quiet
        ) || return 1
    fi

    export VIRTUAL_ENV="${project_venv}"
    _cie_remove_path_entry "${project_venv}/bin"
    export PATH="${project_venv}/bin:${PATH}"
}
