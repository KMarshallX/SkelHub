#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  checker.sh --foreground FOREGROUND_NIFTI --skeleton SKELETON_NIFTI

Required arguments:
  -f, --foreground    Foreground volume (.nii or .nii.gz)
  -s, --skeleton      Skeleton volume (.nii or .nii.gz)

Options:
  -h, --help          Show this help message

Every nonzero voxel is treated as foreground or skeleton. Non-binary values
are reported to stderr. The final confinement result is printed to stdout:
"Yes" when every skeleton voxel is inside the foreground, otherwise "No".
EOF
}

FOREGROUND=""
SKELETON=""

while (($# > 0)); do
    case "$1" in
        -f|--foreground)
            if (($# < 2)); then
                echo "Error: $1 requires a file path." >&2
                usage >&2
                exit 2
            fi
            FOREGROUND="$2"
            shift 2
            ;;
        -s|--skeleton)
            if (($# < 2)); then
                echo "Error: $1 requires a file path." >&2
                usage >&2
                exit 2
            fi
            SKELETON="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Error: unknown argument '$1'." >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ -z "${FOREGROUND}" || -z "${SKELETON}" ]]; then
    echo "Error: --foreground and --skeleton are required." >&2
    usage >&2
    exit 2
fi

validate_nifti() {
    local label="$1"
    local path="$2"

    if [[ "${path}" != *.nii && "${path}" != *.nii.gz ]]; then
        echo "Error: ${label} must have a .nii or .nii.gz extension: ${path}" >&2
        exit 2
    fi
    if [[ ! -f "${path}" ]]; then
        echo "Error: ${label} file does not exist: ${path}" >&2
        exit 2
    fi
}

validate_nifti "foreground" "${FOREGROUND}"
validate_nifti "skeleton" "${SKELETON}"

if ! command -v python >/dev/null 2>&1; then
    echo "Error: 'python' is not available in the active environment." >&2
    exit 2
fi

python - "${FOREGROUND}" "${SKELETON}" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

try:
    import nibabel as nib
    import numpy as np
except ImportError as exc:
    print(f"Error: missing Python dependency: {exc.name}", file=sys.stderr)
    raise SystemExit(2) from exc


def load_voxels(path: Path, label: str) -> np.ndarray:
    try:
        image = nib.load(str(path))
        return np.asanyarray(image.dataobj)
    except Exception as exc:
        print(f"Error: unable to read {label} NIfTI '{path}': {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def report_nonbinary(values: np.ndarray, label: str) -> None:
    unique_values = np.unique(values)
    nonbinary = unique_values[(unique_values != 0) & (unique_values != 1)]
    if nonbinary.size:
        formatted = ", ".join(str(value.item()) for value in nonbinary)
        print(f"{label} non-binary values: [{formatted}]", file=sys.stderr)


foreground_path = Path(sys.argv[1])
skeleton_path = Path(sys.argv[2])
foreground = load_voxels(foreground_path, "foreground")
skeleton = load_voxels(skeleton_path, "skeleton")

if foreground.shape != skeleton.shape:
    print(
        "Error: foreground and skeleton shapes differ: "
        f"{foreground.shape} != {skeleton.shape}",
        file=sys.stderr,
    )
    raise SystemExit(2)

report_nonbinary(foreground, "Foreground")
report_nonbinary(skeleton, "Skeleton")

escaping_voxels = (skeleton != 0) & (foreground == 0)
print("No" if np.any(escaping_voxels) else "Yes")
PY
