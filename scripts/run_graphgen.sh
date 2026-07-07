#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  run_graphgen.sh --input INPUT_DIR --output OUTPUT_DIR [options]

Required arguments:
  -i, --input      Directory to search recursively for skeleton .nii and .nii.gz files
  -o, --output     Directory where generated GraphML files will be written

Options:
  -v, --verbose    Pass --verbose to skelhub graphgen
  -h, --help       Show this help message

Example:
  ./scripts/run_graphgen.sh \
    --input ./test_outputs/exvivo/mcp/selected \
    --output ./test_outputs/exvivo/mcp/graphs \
    --verbose
EOF
}

nifti_stem() {
    local filename="$1"
    if [[ "${filename}" == *.nii.gz ]]; then
        printf '%s\n' "${filename%.nii.gz}"
    elif [[ "${filename}" == *.nii ]]; then
        printf '%s\n' "${filename%.nii}"
    else
        return 1
    fi
}

INPUT_DIR=""
OUTPUT_DIR=""
VERBOSE=0

while (($# > 0)); do
    case "$1" in
        -i|--input)
            INPUT_DIR="${2:-}"
            shift 2
            ;;
        -o|--output)
            OUTPUT_DIR="${2:-}"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Error: unknown argument '$1'" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [[ -z "${INPUT_DIR}" || -z "${OUTPUT_DIR}" ]]; then
    echo "Error: --input and --output are required." >&2
    usage >&2
    exit 1
fi

if [[ -z "${CONDA_PREFIX:-}" ]]; then
    echo "Warning: no active conda environment detected. Activate the conda environment containing SkelHub dependencies and retry." >&2
    exit 1
fi

if ! command -v python >/dev/null 2>&1; then
    echo "Warning: 'python' is not available in the active conda environment: ${CONDA_DEFAULT_ENV:-${CONDA_PREFIX}}" >&2
    exit 1
fi

if ! command -v skelhub >/dev/null 2>&1; then
    echo "Warning: 'skelhub' is not available in the active conda environment: ${CONDA_DEFAULT_ENV:-${CONDA_PREFIX}}" >&2
    exit 1
fi

if ! python - <<'PY'
import importlib.util
import sys

required_modules = (
    "skelhub",
    "igraph",
    "nibabel",
    "numpy",
    "scipy",
)

missing = [module for module in required_modules if importlib.util.find_spec(module) is None]
if missing:
    print(", ".join(missing), file=sys.stderr)
    raise SystemExit(1)
PY
then
    echo "Warning: active conda environment is missing required graphgen dependencies: ${CONDA_DEFAULT_ENV:-${CONDA_PREFIX}}" >&2
    exit 1
fi

if [[ ! -d "${INPUT_DIR}" ]]; then
    echo "Error: input directory does not exist: ${INPUT_DIR}" >&2
    exit 1
fi

INPUT_DIR="$(cd "${INPUT_DIR}" && pwd)"
if [[ -e "${OUTPUT_DIR}" && ! -d "${OUTPUT_DIR}" ]]; then
    echo "Warning: --output exists but is not a directory: ${OUTPUT_DIR}" >&2
    exit 1
fi

if [[ ! -d "${OUTPUT_DIR}" ]]; then
    echo "Notice: --output does not exist; creating: ${OUTPUT_DIR}" >&2
    if ! mkdir -p "${OUTPUT_DIR}"; then
        echo "Warning: unable to create --output: ${OUTPUT_DIR}" >&2
        exit 1
    fi
fi

if [[ ! -d "${OUTPUT_DIR}" ]]; then
    echo "Warning: --output is not a valid directory after creation: ${OUTPUT_DIR}" >&2
    exit 1
fi

if ! OUTPUT_DIR="$(cd "${OUTPUT_DIR}" && pwd)"; then
    echo "Warning: unable to resolve --output: ${OUTPUT_DIR}" >&2
    exit 1
fi

mapfile -d '' NIFTI_FILES < <(
    find "${INPUT_DIR}" -type f \( -name '*.nii' -o -name '*.nii.gz' \) -print0 | sort -z
)

if [[ ${#NIFTI_FILES[@]} -eq 0 ]]; then
    echo "Error: no .nii or .nii.gz files found under ${INPUT_DIR}" >&2
    exit 1
fi

echo "Found ${#NIFTI_FILES[@]} skeleton NIfTI file(s) under ${INPUT_DIR}"

for input_file in "${NIFTI_FILES[@]}"; do
    relative_path="${input_file#${INPUT_DIR}/}"
    relative_dir="$(dirname "${relative_path}")"
    filename="$(basename "${input_file}")"
    stem="$(nifti_stem "${filename}")"

    output_subdir="${OUTPUT_DIR}"
    if [[ "${relative_dir}" != "." ]]; then
        output_subdir="${OUTPUT_DIR}/${relative_dir}"
    fi
    mkdir -p "${output_subdir}"

    output_file="${output_subdir}/${stem}.graphml"

    echo "Processing: ${input_file}"
    echo "Output: ${output_file}"

    cmd=(
        skelhub graphgen
        --input "${input_file}"
        --output "${output_file}"
    )

    if [[ ${VERBOSE} -eq 1 ]]; then
        cmd+=(--verbose)
    fi

    "${cmd[@]}"
done

echo "Completed ${#NIFTI_FILES[@]} file(s). GraphML outputs written under ${OUTPUT_DIR}"
