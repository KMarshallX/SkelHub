#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  checker.sh --foreground FOREGROUND_NIFTI --skeleton SKELETON [--connectivity {6,18,26}]

Required arguments:
  -f, --foreground         Foreground volume (.nii or .nii.gz)
  -s, --skeleton           Skeleton volume (.nii or .nii.gz) or graph (.graphml)

Options:
  -c, --connectivity       Connected-component connectivity: 6, 18, or 26
                           (default: 26)
  -h, --help               Show this help message

Every nonzero NIfTI voxel is treated as foreground or skeleton. Non-binary
values are reported to stderr. For GraphML skeletons, node voxel_pos and each
available centerline coordinate field are checked against occupied foreground
voxel cells. Connected-component counts are printed to stdout.
EOF
}

FOREGROUND=""
SKELETON=""
CONNECTIVITY=26

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
        -c|--connectivity)
            if (($# < 2)); then
                echo "Error: $1 requires one of: 6, 18, 26." >&2
                usage >&2
                exit 2
            fi
            CONNECTIVITY="$2"
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

case "${CONNECTIVITY}" in
    6|18|26) ;;
    *)
        echo "Error: --connectivity must be one of: 6, 18, 26." >&2
        usage >&2
        exit 2
        ;;
esac

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
if [[ "${SKELETON}" != *.graphml ]]; then
    validate_nifti "skeleton" "${SKELETON}"
elif [[ ! -f "${SKELETON}" ]]; then
    echo "Error: skeleton file does not exist: ${SKELETON}" >&2
    exit 2
fi

if ! command -v python >/dev/null 2>&1; then
    echo "Error: 'python' is not available in the active environment." >&2
    exit 2
fi

python -m skelhub.postprocessing.checker "${FOREGROUND}" "${SKELETON}" "${CONNECTIVITY}"
