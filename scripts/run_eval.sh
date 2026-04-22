#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  run_eval.sh --pred-dir PRED_DIR --ref-dir REF_DIR --buffer-radius RADIUS [options] [-- extra skelhub flags]

Required arguments:
  -p, --pred-dir         Directory to search recursively for prediction .nii and .nii.gz files
  -r, --ref-dir          Directory to search recursively for reference .nii and .nii.gz files
  -b, --buffer-radius    Buffer radius passed to skelhub evaluate

Options:
      --buffer-radius-unit  Unit for buffer radius: voxels or um (default: voxels)
      --no-verbose         Do not pass --verbose to skelhub evaluate
  -h, --help              Show this help message

Any arguments after -- are forwarded to:
  skelhub evaluate ...

Reference matching:
  For each prediction, the script extracts the basename stem without the NIfTI extension
  and looks for reference files under REF_DIR whose basename shares the same Lnet_i... prefix.
  Exact stem matches are preferred, then prefix matches such as:
    pred: Lnet_i4_0_tort_centreline.nii.gz
    ref:  Lnet_i4_0_tort_centreline_26conn.nii.gz

Example:
  ./scripts/run_eval.sh \
    --pred-dir ./test_outputs \
    --ref-dir ./test_data/lsys_gt \
    --buffer-radius 1 \
    -- --buffer-radius-unit voxels
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

pred_stem() {
    local filename="$1"
    if [[ "${filename}" == *.nii.gz ]]; then
        printf '%s\n' "${filename%.nii.gz}"
    elif [[ "${filename}" == *.nii ]]; then
        printf '%s\n' "${filename%.nii}"
    else
        return 1
    fi
}

extract_lnet_prefix() {
    local stem="$1"
    if [[ "${stem}" =~ ^(Lnet_i[^.]+) ]]; then
        printf '%s\n' "${BASH_REMATCH[1]}"
        return 0
    fi
    return 1
}

find_reference_match() {
    local prediction_file="$1"
    local prediction_name prediction_stem prediction_prefix
    local exact_matches=()
    local prefix_matches=()
    local ref_file ref_name ref_stem

    prediction_name="$(basename "${prediction_file}")"
    prediction_stem="$(pred_stem "${prediction_name}")"

    if ! prediction_prefix="$(extract_lnet_prefix "${prediction_stem}")"; then
        echo "Error: prediction filename does not contain an Lnet_i-style prefix: ${prediction_file}" >&2
        return 1
    fi

    for ref_file in "${REF_FILES[@]}"; do
        ref_name="$(basename "${ref_file}")"
        ref_stem="$(pred_stem "${ref_name}")" || continue

        if [[ "${ref_stem}" == "${prediction_stem}" ]]; then
            exact_matches+=("${ref_file}")
            continue
        fi

        if [[ "${ref_stem}" == "${prediction_stem}"* || "${prediction_stem}" == "${ref_stem}"* ]]; then
            prefix_matches+=("${ref_file}")
            continue
        fi

        if [[ "${ref_stem}" == "${prediction_prefix}"* ]]; then
            prefix_matches+=("${ref_file}")
        fi
    done

    if [[ ${#exact_matches[@]} -eq 1 ]]; then
        printf '%s\n' "${exact_matches[0]}"
        return 0
    fi

    if [[ ${#exact_matches[@]} -gt 1 ]]; then
        echo "Error: multiple exact reference matches found for ${prediction_file}" >&2
        printf '  %s\n' "${exact_matches[@]}" >&2
        return 1
    fi

    if [[ ${#prefix_matches[@]} -eq 1 ]]; then
        printf '%s\n' "${prefix_matches[0]}"
        return 0
    fi

    if [[ ${#prefix_matches[@]} -eq 0 ]]; then
        echo "Error: no reference match found for ${prediction_file}" >&2
        return 1
    fi

    echo "Error: multiple reference matches found for ${prediction_file}" >&2
    printf '  %s\n' "${prefix_matches[@]}" >&2
    return 1
}

PRED_DIR=""
REF_DIR=""
BUFFER_RADIUS=""
BUFFER_RADIUS_UNIT="voxels"
VERBOSE=1
EXTRA_ARGS=()

while (($# > 0)); do
    case "$1" in
        -p|--pred-dir)
            PRED_DIR="${2:-}"
            shift 2
            ;;
        -r|--ref-dir)
            REF_DIR="${2:-}"
            shift 2
            ;;
        -b|--buffer-radius)
            BUFFER_RADIUS="${2:-}"
            shift 2
            ;;
        --buffer-radius-unit)
            BUFFER_RADIUS_UNIT="${2:-}"
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

if [[ -z "${PRED_DIR}" || -z "${REF_DIR}" || -z "${BUFFER_RADIUS}" ]]; then
    echo "Error: --pred-dir, --ref-dir, and --buffer-radius are required." >&2
    usage >&2
    exit 1
fi

if [[ ! -d "${PRED_DIR}" ]]; then
    echo "Error: prediction directory does not exist: ${PRED_DIR}" >&2
    exit 1
fi

if [[ ! -d "${REF_DIR}" ]]; then
    echo "Error: reference directory does not exist: ${REF_DIR}" >&2
    exit 1
fi

if [[ "${BUFFER_RADIUS_UNIT}" != "voxels" && "${BUFFER_RADIUS_UNIT}" != "um" ]]; then
    echo "Error: --buffer-radius-unit must be either 'voxels' or 'um'." >&2
    exit 1
fi

PRED_DIR="$(cd "${PRED_DIR}" && pwd)"
REF_DIR="$(cd "${REF_DIR}" && pwd)"

mapfile -d '' PRED_FILES < <(
    find "${PRED_DIR}" -type f \( -name '*.nii' -o -name '*.nii.gz' \) -print0 | sort -z
)

mapfile -d '' REF_FILES < <(
    find "${REF_DIR}" -type f \( -name '*.nii' -o -name '*.nii.gz' \) -print0 | sort -z
)

if [[ ${#PRED_FILES[@]} -eq 0 ]]; then
    echo "Error: no .nii or .nii.gz files found under ${PRED_DIR}" >&2
    exit 1
fi

if [[ ${#REF_FILES[@]} -eq 0 ]]; then
    echo "Error: no .nii or .nii.gz files found under ${REF_DIR}" >&2
    exit 1
fi

echo "Found ${#PRED_FILES[@]} prediction NIfTI file(s) under ${PRED_DIR}"
echo "Found ${#REF_FILES[@]} reference NIfTI file(s) under ${REF_DIR}"
echo "Using buffer radius ${BUFFER_RADIUS} (${BUFFER_RADIUS_UNIT})"

processed_count=0

for pred_file in "${PRED_FILES[@]}"; do
    pred_name="$(basename "${pred_file}")"
    pred_base="$(pred_stem "${pred_name}")"
    json_output="$(dirname "${pred_file}")/${pred_base}_eval.json"
    ref_file="$(find_reference_match "${pred_file}")"

    echo "Prediction: ${pred_file}"
    echo "Reference:  ${ref_file}"
    echo "JSON:       ${json_output}"

    cmd=(
        skelhub evaluate
        --pred "${pred_file}"
        --ref "${ref_file}"
        --buffer-radius "${BUFFER_RADIUS}"
        --buffer-radius-unit "${BUFFER_RADIUS_UNIT}"
        --json-output "${json_output}"
    )

    if [[ ${VERBOSE} -eq 1 ]]; then
        cmd+=(--verbose)
    fi

    if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
        cmd+=("${EXTRA_ARGS[@]}")
    fi

    "${cmd[@]}"
    processed_count=$((processed_count + 1))
done

echo "Completed ${processed_count} evaluation(s). JSON reports written beside prediction files."
