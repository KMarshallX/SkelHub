#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  run_featext.sh --foreground-dir DIR --skel-dir DIR --graph-dir DIR \
    --edge-op-dir DIR --node-op-dir DIR [options]

Required arguments:
  -fd, --foreground-dir  Directory searched recursively for foreground NIfTI files
  -sd, --skel-dir        Directory searched recursively for skeleton NIfTI files
  -gd, --graph-dir       Directory searched recursively for GraphML files
  -eo, --edge-op-dir     Directory for <foreground-stem>_edge.csv outputs
  -no, --node-op-dir     Directory for <foreground-stem>_node.csv outputs

Options:
  -v, --verbose          Show batch progress and pass --verbose to skelhub feature
  -h, --help             Show this help message

Matching:
  An exact foreground/skeleton stem match is preferred. Otherwise, exactly one
  skeleton stem must contain the foreground stem. The GraphML stem must exactly
  match the selected skeleton stem. Matching is global across each directory tree.
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

require_value() {
    local option="$1"
    local value="${2:-}"
    if [[ -z "${value}" ]]; then
        echo "Error: ${option} requires a value." >&2
        usage >&2
        exit 1
    fi
}

resolve_input_dir() {
    local option="$1"
    local directory="$2"
    if [[ ! -d "${directory}" ]]; then
        echo "Error: ${option} directory does not exist: ${directory}" >&2
        exit 1
    fi
    (cd "${directory}" && pwd)
}

prepare_output_dir() {
    local option="$1"
    local directory="$2"
    if [[ -e "${directory}" && ! -d "${directory}" ]]; then
        echo "Error: ${option} exists but is not a directory: ${directory}" >&2
        exit 1
    fi
    if [[ ! -d "${directory}" ]]; then
        mkdir -p "${directory}"
    fi
    if [[ ! -d "${directory}" ]]; then
        echo "Error: unable to create ${option} directory: ${directory}" >&2
        exit 1
    fi
    (cd "${directory}" && pwd)
}

print_candidates() {
    local candidate
    for candidate in "$@"; do
        printf '  %s\n' "${candidate}" >&2
    done
}

print_progress() {
    local completed="$1"
    local total="$2"
    local width=30
    local filled=$((completed * width / total))
    local empty=$((width - filled))
    local filled_bar empty_bar

    printf -v filled_bar '%*s' "${filled}" ''
    printf -v empty_bar '%*s' "${empty}" ''
    filled_bar="${filled_bar// /#}"
    empty_bar="${empty_bar// /-}"
    printf 'Progress: [%s%s] %d/%d\n' "${filled_bar}" "${empty_bar}" "${completed}" "${total}"
}

FOREGROUND_DIR=""
SKEL_DIR=""
GRAPH_DIR=""
EDGE_OP_DIR=""
NODE_OP_DIR=""
VERBOSE=0

while (($# > 0)); do
    case "$1" in
        -fd|--foreground-dir)
            require_value "$1" "${2:-}"
            FOREGROUND_DIR="$2"
            shift 2
            ;;
        -sd|--skel-dir)
            require_value "$1" "${2:-}"
            SKEL_DIR="$2"
            shift 2
            ;;
        -gd|--graph-dir)
            require_value "$1" "${2:-}"
            GRAPH_DIR="$2"
            shift 2
            ;;
        -eo|--edge-op-dir)
            require_value "$1" "${2:-}"
            EDGE_OP_DIR="$2"
            shift 2
            ;;
        -no|--node-op-dir)
            require_value "$1" "${2:-}"
            NODE_OP_DIR="$2"
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

if [[ -z "${FOREGROUND_DIR}" || -z "${SKEL_DIR}" || -z "${GRAPH_DIR}" || \
      -z "${EDGE_OP_DIR}" || -z "${NODE_OP_DIR}" ]]; then
    echo "Error: all foreground, skeleton, graph, edge output, and node output directories are required." >&2
    usage >&2
    exit 1
fi

if [[ -z "${CONDA_PREFIX:-}" && -z "${VIRTUAL_ENV:-}" ]]; then
    echo "Error: no active conda or Python virtual environment detected." >&2
    echo "Activate the environment containing SkelHub and retry." >&2
    exit 1
fi

if ! command -v skelhub >/dev/null 2>&1; then
    echo "Error: 'skelhub' is not available in the active environment." >&2
    exit 1
fi

FOREGROUND_DIR="$(resolve_input_dir --foreground-dir "${FOREGROUND_DIR}")"
SKEL_DIR="$(resolve_input_dir --skel-dir "${SKEL_DIR}")"
GRAPH_DIR="$(resolve_input_dir --graph-dir "${GRAPH_DIR}")"
EDGE_OP_DIR="$(prepare_output_dir --edge-op-dir "${EDGE_OP_DIR}")"
NODE_OP_DIR="$(prepare_output_dir --node-op-dir "${NODE_OP_DIR}")"

mapfile -d '' FOREGROUND_FILES < <(
    find "${FOREGROUND_DIR}" -type f \( -name '*.nii' -o -name '*.nii.gz' \) -print0 | sort -z
)
mapfile -d '' SKEL_FILES < <(
    find "${SKEL_DIR}" -type f \( -name '*.nii' -o -name '*.nii.gz' \) -print0 | sort -z
)
mapfile -d '' GRAPH_FILES < <(
    find "${GRAPH_DIR}" -type f -name '*.graphml' -print0 | sort -z
)

if [[ ${#FOREGROUND_FILES[@]} -eq 0 ]]; then
    echo "Error: no .nii or .nii.gz foreground files found under ${FOREGROUND_DIR}" >&2
    exit 1
fi
if [[ ${#SKEL_FILES[@]} -eq 0 ]]; then
    echo "Error: no .nii or .nii.gz skeleton files found under ${SKEL_DIR}" >&2
    exit 1
fi
if [[ ${#GRAPH_FILES[@]} -eq 0 ]]; then
    echo "Error: no .graphml files found under ${GRAPH_DIR}" >&2
    exit 1
fi

# Flat output directories require foreground stems to be unique across the batch.
SEEN_STEMS=()
SEEN_FILES=()
for foreground_file in "${FOREGROUND_FILES[@]}"; do
    foreground_stem="$(nifti_stem "$(basename "${foreground_file}")")"
    for index in "${!SEEN_STEMS[@]}"; do
        if [[ "${SEEN_STEMS[index]}" == "${foreground_stem}" ]]; then
            echo "Error: duplicate foreground stem '${foreground_stem}' would create conflicting outputs:" >&2
            print_candidates "${SEEN_FILES[index]}" "${foreground_file}"
            exit 1
        fi
    done
    SEEN_STEMS+=("${foreground_stem}")
    SEEN_FILES+=("${foreground_file}")
done

total=${#FOREGROUND_FILES[@]}
completed=0
echo "Found ${total} foreground NIfTI file(s) under ${FOREGROUND_DIR}"
if [[ ${VERBOSE} -eq 1 ]]; then
    print_progress 0 "${total}"
fi

for foreground_file in "${FOREGROUND_FILES[@]}"; do
    foreground_stem="$(nifti_stem "$(basename "${foreground_file}")")"
    exact_skeletons=()
    containing_skeletons=()

    for skeleton_file in "${SKEL_FILES[@]}"; do
        skeleton_stem="$(nifti_stem "$(basename "${skeleton_file}")")"
        if [[ "${skeleton_stem}" == "${foreground_stem}" ]]; then
            exact_skeletons+=("${skeleton_file}")
        elif [[ "${skeleton_stem}" == *"${foreground_stem}"* ]]; then
            containing_skeletons+=("${skeleton_file}")
        fi
    done

    if [[ ${#exact_skeletons[@]} -eq 1 ]]; then
        skeleton_file="${exact_skeletons[0]}"
    elif [[ ${#exact_skeletons[@]} -gt 1 ]]; then
        echo "Error: multiple exact skeleton matches found for ${foreground_file}:" >&2
        print_candidates "${exact_skeletons[@]}"
        exit 1
    elif [[ ${#containing_skeletons[@]} -eq 1 ]]; then
        skeleton_file="${containing_skeletons[0]}"
    elif [[ ${#containing_skeletons[@]} -eq 0 ]]; then
        echo "Error: no skeleton filename contains foreground stem '${foreground_stem}': ${foreground_file}" >&2
        exit 1
    else
        echo "Error: multiple containing skeleton matches found for ${foreground_file}:" >&2
        print_candidates "${containing_skeletons[@]}"
        exit 1
    fi

    skeleton_stem="$(nifti_stem "$(basename "${skeleton_file}")")"
    graph_matches=()
    for graph_file in "${GRAPH_FILES[@]}"; do
        graph_stem="$(basename "${graph_file}" .graphml)"
        if [[ "${graph_stem}" == "${skeleton_stem}" ]]; then
            graph_matches+=("${graph_file}")
        fi
    done

    if [[ ${#graph_matches[@]} -eq 0 ]]; then
        echo "Error: no GraphML stem matches skeleton stem '${skeleton_stem}': ${skeleton_file}" >&2
        exit 1
    elif [[ ${#graph_matches[@]} -gt 1 ]]; then
        echo "Error: multiple GraphML matches found for ${skeleton_file}:" >&2
        print_candidates "${graph_matches[@]}"
        exit 1
    fi
    graph_file="${graph_matches[0]}"

    edge_output="${EDGE_OP_DIR}/${foreground_stem}_edge.csv"
    node_output="${NODE_OP_DIR}/${foreground_stem}_node.csv"

    if [[ ${VERBOSE} -eq 1 ]]; then
        echo "Foreground: ${foreground_file}"
        echo "Skeleton:   ${skeleton_file}"
        echo "Graph:      ${graph_file}"
        echo "Edge CSV:   ${edge_output}"
        echo "Node CSV:   ${node_output}"
    fi

    cmd=(
        skelhub feature
        --foreground "${foreground_file}"
        --skeleton "${skeleton_file}"
        --graph "${graph_file}"
        --edge-output "${edge_output}"
        --node-output "${node_output}"
    )
    if [[ ${VERBOSE} -eq 1 ]]; then
        cmd+=(--verbose)
    fi

    if "${cmd[@]}"; then
        :
    else
        status=$?
        echo "Error: skelhub feature failed for ${foreground_file} with status ${status}." >&2
        exit "${status}"
    fi

    completed=$((completed + 1))
    if [[ ${VERBOSE} -eq 1 ]]; then
        print_progress "${completed}" "${total}"
    fi
done

echo "Completed ${completed} image set(s)."
echo "Edge CSV outputs: ${EDGE_OP_DIR}"
echo "Node CSV outputs: ${NODE_OP_DIR}"
