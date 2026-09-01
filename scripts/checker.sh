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

python - "${FOREGROUND}" "${SKELETON}" "${CONNECTIVITY}" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

try:
    import nibabel as nib
    import numpy as np
    from scipy import ndimage
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


def load_graphml(path: Path):
    try:
        import igraph as ig
    except ImportError as exc:
        print("Error: missing Python dependency: igraph", file=sys.stderr)
        raise SystemExit(2) from exc
    try:
        return ig.Graph.Read_GraphML(str(path))
    except Exception as exc:
        print(f"Error: unable to read skeleton GraphML '{path}': {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def parse_points(value: object, label: str, *, single: bool = False) -> np.ndarray:
    import json

    try:
        points = np.asarray(json.loads(str(value)), dtype=float)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {label} must contain JSON coordinates.", file=sys.stderr)
        raise SystemExit(2) from exc
    expected_shape = (3,) if single else None
    if single:
        valid_shape = points.shape == expected_shape
    else:
        valid_shape = points.ndim == 2 and points.shape[1:] == (3,)
    if not valid_shape or not np.isfinite(points).all():
        description = "three" if single else "a list of"
        print(
            f"Error: {label} must contain {description} finite 3D coordinates.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return points.reshape((-1, 3))


def points_are_confined(points: np.ndarray, foreground: np.ndarray) -> bool:
    """Test points against half-open voxel cells without changing the points."""
    if len(points) == 0:
        return True
    containing_voxels = np.floor(points + 0.5).astype(np.int64)
    in_bounds = np.all(
        (containing_voxels >= 0) & (containing_voxels < np.asarray(foreground.shape)),
        axis=1,
    )
    if not np.all(in_bounds):
        return False
    return bool(np.all(foreground[tuple(containing_voxels.T)] != 0))


def report_graphml(graph, foreground: np.ndarray, foreground_affine: np.ndarray) -> None:
    vertex_attributes = set(graph.vs.attributes())
    if graph.vcount() and "voxel_pos" not in vertex_attributes:
        print("Error: GraphML nodes must provide 'voxel_pos'.", file=sys.stderr)
        raise SystemExit(2)

    node_points = np.vstack(
        [
            parse_points(vertex["voxel_pos"], f"node {vertex.index} voxel_pos", single=True)
            for vertex in graph.vs
        ]
    ) if graph.vcount() else np.empty((0, 3), dtype=float)
    nodes_contained = "Yes" if points_are_confined(node_points, foreground) else "No"
    print(f"Are all graph node voxel_pos points contained within foreground: {nodes_contained}")

    edge_coordinate_fields = (
        ("centerline_voxels", False),
        ("centerline_voxel_points", False),
        ("centerline_world_points", True),
    )
    edge_attributes = set(graph.es.attributes())
    available_edge_fields = [
        field for field, _ in edge_coordinate_fields if field in edge_attributes
    ]
    if graph.ecount() and not available_edge_fields:
        supported = ", ".join(field for field, _ in edge_coordinate_fields)
        print(
            "Error: GraphML edges must provide at least one supported coordinate "
            f"field: {supported}.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    for field, is_world_coordinates in edge_coordinate_fields:
        if field not in edge_attributes:
            continue
        field_points = np.vstack(
            [parse_points(edge[field], f"edge {edge.index} {field}") for edge in graph.es]
        ) if graph.ecount() else np.empty((0, 3), dtype=float)
        if is_world_coordinates and len(field_points):
            try:
                world_to_voxel = np.linalg.inv(foreground_affine)
            except np.linalg.LinAlgError as exc:
                print("Error: foreground affine is singular.", file=sys.stderr)
                raise SystemExit(2) from exc
            field_points = nib.affines.apply_affine(world_to_voxel, field_points)
        contained = "Yes" if points_are_confined(field_points, foreground) else "No"
        print(f"Are all graph edge {field} points contained within foreground: {contained}")

    graph_component_count = len(graph.connected_components(mode="weak"))
    print(f"Graph connected-components number: {graph_component_count}")


foreground_path = Path(sys.argv[1])
skeleton_path = Path(sys.argv[2])
connectivity = int(sys.argv[3])
try:
    foreground_image = nib.load(str(foreground_path))
    foreground = np.asanyarray(foreground_image.dataobj)
except Exception as exc:
    print(f"Error: unable to read foreground NIfTI '{foreground_path}': {exc}", file=sys.stderr)
    raise SystemExit(2) from exc

if foreground.ndim != 3:
    print(
        f"Error: foreground must be a 3D volume, got {foreground.ndim}D.",
        file=sys.stderr,
    )
    raise SystemExit(2)

report_nonbinary(foreground, "Foreground")

connectivity_rank = {6: 1, 18: 2, 26: 3}[connectivity]
structure = ndimage.generate_binary_structure(rank=3, connectivity=connectivity_rank)
_, foreground_component_count = ndimage.label(foreground != 0, structure=structure)

if skeleton_path.suffix.lower() == ".graphml":
    graph = load_graphml(skeleton_path)
    report_graphml(graph, foreground, foreground_image.affine)
    print(f"Foreground connected-components number: {foreground_component_count}")
    raise SystemExit(0)

skeleton = load_voxels(skeleton_path, "skeleton")
if foreground.shape != skeleton.shape:
    print(
        "Error: foreground and skeleton shapes differ: "
        f"{foreground.shape} != {skeleton.shape}",
        file=sys.stderr,
    )
    raise SystemExit(2)
if skeleton.ndim != 3:
    print(
        f"Error: foreground and skeleton must be 3D volumes, got {skeleton.ndim}D.",
        file=sys.stderr,
    )
    raise SystemExit(2)

report_nonbinary(skeleton, "Skeleton")
_, skeleton_component_count = ndimage.label(skeleton != 0, structure=structure)

escaping_voxels = (skeleton != 0) & (foreground == 0)
contained = "No" if np.any(escaping_voxels) else "Yes"
print(f"Are all skeleton voxels contained within foreground: {contained}")
print(f"Foreground connected-components number: {foreground_component_count}")
print(f"Skeleton connected-components number: {skeleton_component_count}")
PY
