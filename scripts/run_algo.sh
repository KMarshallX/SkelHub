#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  run_alog.sh --algorithm ALGORITHM --input-dir INPUT_DIR --output-dir OUTPUT_DIR [options] [-- extra skelhub flags]

Required arguments:
  -a, --algorithm     SkelHub backend name, for example: mcp or lee94
  -i, --input-dir     Directory to search recursively for .nii and .nii.gz files
  -o, --output-dir    Directory where processed outputs will be written

Options:
  -s, --suffix        Suffix inserted before the NIfTI extension (default: _centreline)
      --no-verbose    Do not pass --verbose to skelhub run
  -h, --help          Show this help message

Any arguments after -- are forwarded to:
  skelhub run --algorithm ...

Example:
  ./scripts/run_alog.sh \
    --algorithm mcp \
    --input-dir ./test_data \
    --output-dir ./test_outputs/batch \
    -- --threshold-scale 1.2 --max-iterations 150
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_ACTIVATE="${REPO_ROOT}/.venv/bin/activate"

if [[ ! -f "${VENV_ACTIVATE}" ]]; then
    echo "Error: virtual environment activation script not found at ${VENV_ACTIVATE}" >&2
    exit 1
fi

# shellcheck disable=SC1090
source "${VENV_ACTIVATE}"

if ! command -v skelhub >/dev/null 2>&1; then
    echo "Error: 'skelhub' is not available after activating ${VENV_ACTIVATE}" >&2
    exit 1
fi

ALGORITHM=""
INPUT_DIR=""
OUTPUT_DIR=""
SUFFIX="_centreline"
VERBOSE=1
EXTRA_ARGS=()

while (($# > 0)); do
    case "$1" in
        -a|--algorithm)
            ALGORITHM="${2:-}"
            shift 2
            ;;
        -i|--input-dir)
            INPUT_DIR="${2:-}"
            shift 2
            ;;
        -o|--output-dir)
            OUTPUT_DIR="${2:-}"
            shift 2
            ;;
        -s|--suffix)
            SUFFIX="${2:-}"
            shift 2
            ;;
        --no-verbose)
            VERBOSE=0
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            EXTRA_ARGS=("$@")
            break
            ;;
        *)
            echo "Error: unknown argument '$1'" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [[ -z "${ALGORITHM}" || -z "${INPUT_DIR}" || -z "${OUTPUT_DIR}" ]]; then
    echo "Error: --algorithm, --input-dir, and --output-dir are required." >&2
    usage >&2
    exit 1
fi

if [[ ! -d "${INPUT_DIR}" ]]; then
    echo "Error: input directory does not exist: ${INPUT_DIR}" >&2
    exit 1
fi

INPUT_DIR="$(cd "${INPUT_DIR}" && pwd)"
mkdir -p "${OUTPUT_DIR}"
OUTPUT_DIR="$(cd "${OUTPUT_DIR}" && pwd)"

mapfile -d '' NIFTI_FILES < <(
    find "${INPUT_DIR}" -type f \( -name '*.nii' -o -name '*.nii.gz' \) -print0 | sort -z
)

if [[ ${#NIFTI_FILES[@]} -eq 0 ]]; then
    echo "Error: no .nii or .nii.gz files found under ${INPUT_DIR}" >&2
    exit 1
fi

echo "Found ${#NIFTI_FILES[@]} NIfTI file(s) under ${INPUT_DIR}"
echo "Running algorithm '${ALGORITHM}'"

for input_file in "${NIFTI_FILES[@]}"; do
    relative_path="${input_file#${INPUT_DIR}/}"
    relative_dir="$(dirname "${relative_path}")"
    filename="$(basename "${input_file}")"

    if [[ "${filename}" == *.nii.gz ]]; then
        stem="${filename%.nii.gz}"
        extension=".nii.gz"
    elif [[ "${filename}" == *.nii ]]; then
        stem="${filename%.nii}"
        extension=".nii"
    else
        echo "Skipping unsupported file: ${input_file}" >&2
        continue
    fi

    output_subdir="${OUTPUT_DIR}"
    if [[ "${relative_dir}" != "." ]]; then
        output_subdir="${OUTPUT_DIR}/${relative_dir}"
    fi
    mkdir -p "${output_subdir}"

    output_file="${output_subdir}/${stem}${SUFFIX}${extension}"

    echo "Processing: ${input_file}"
    echo "Output: ${output_file}"

    cmd=(
        skelhub run
        --algorithm "${ALGORITHM}"
        --input "${input_file}"
        --output "${output_file}"
    )

    if [[ ${VERBOSE} -eq 1 ]]; then
        cmd+=(--verbose)
    fi

    if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
        cmd+=("${EXTRA_ARGS[@]}")
    fi

    "${cmd[@]}"
done

echo "Completed ${#NIFTI_FILES[@]} file(s). Outputs written under ${OUTPUT_DIR}"
