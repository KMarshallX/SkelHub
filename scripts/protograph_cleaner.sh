#!/usr/bin/env bash

set -euo pipefail

if ! command -v python >/dev/null 2>&1; then
    echo "Error: 'python' is not available in the active environment." >&2
    exit 1
fi

if ! missing_packages="$(
    python - <<'PY'
import importlib.util

required_packages = {
    "igraph": "igraph",
    "numpy": "numpy",
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
    echo "Error: active Python environment is missing required package(s): ${missing_packages}" >&2
    exit 1
fi

exec python -m skelhub.postprocessing.protograph_cleaner "$@"
