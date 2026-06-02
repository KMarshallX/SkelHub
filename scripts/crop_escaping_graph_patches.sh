#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_ACTIVATE="${REPO_ROOT}/.venv/bin/activate"

if [[ -n "${CONDA_PREFIX:-}" ]]; then
    echo "Using active conda environment: ${CONDA_PREFIX}" >&2
elif [[ -f "${VENV_ACTIVATE}" ]]; then
    # shellcheck disable=SC1090
    source "${VENV_ACTIVATE}"
else
    echo "Using current Python environment; ${VENV_ACTIVATE} was not found." >&2
fi

python - <<'PY'
import importlib.util
import sys

required = {
    "igraph": "python-igraph",
    "nibabel": "nibabel",
    "numpy": "numpy",
    "scipy": "scipy",
}
missing = [package for module, package in required.items() if importlib.util.find_spec(module) is None]
if missing:
    print(
        "Error: missing required Python libraries in the active environment: "
        + ", ".join(missing),
        file=sys.stderr,
    )
    print(f"Python executable: {sys.executable}", file=sys.stderr)
    sys.exit(1)
PY

python "${SCRIPT_DIR}/crop_escaping_graph_patches.py" "$@"
