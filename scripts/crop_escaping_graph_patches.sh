#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_ACTIVATE="${REPO_ROOT}/.venv/bin/activate"

if [[ ! -f "${VENV_ACTIVATE}" ]]; then
    echo "Error: virtual environment activation script not found at ${VENV_ACTIVATE}" >&2
    exit 1
fi

# shellcheck disable=SC1090
source "${VENV_ACTIVATE}"

python "${SCRIPT_DIR}/crop_escaping_graph_patches.py" "$@"
