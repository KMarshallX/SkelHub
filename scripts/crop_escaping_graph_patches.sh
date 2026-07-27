#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "${CONDA_PREFIX:-}" ]]; then
    echo "Error: no active conda environment detected." >&2
    echo "Activate the conda environment containing the crop-patch dependencies and retry." >&2
    exit 1
fi

if ! command -v python >/dev/null 2>&1; then
    echo "Error: 'python' is not available in the active conda environment:" >&2
    echo "${CONDA_DEFAULT_ENV:-${CONDA_PREFIX}}" >&2
    exit 1
fi

if ! missing_packages="$(
    python - <<'PY'
import importlib.util

required_packages = {
    "igraph": "igraph",
    "nibabel": "nibabel",
    "networkx": "networkx",
    "numpy": "numpy",
    "scipy": "scipy",
    "skelhub": "skelhub",
}

missing = [
    package_name
    for module_name, package_name in required_packages.items()
    if importlib.util.find_spec(module_name) is None
]
if missing:
    print(", ".join(missing))
    raise SystemExit(1)
PY
)"; then
    echo "Error: active conda environment is missing required package(s): ${missing_packages}" >&2
    echo "Environment: ${CONDA_DEFAULT_ENV:-${CONDA_PREFIX}}" >&2
    exit 1
fi

python "${SCRIPT_DIR}/crop_escaping_graph_patches.py" "$@"
