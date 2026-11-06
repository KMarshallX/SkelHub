"""GraphML evaluation inputs: the coordinate image and graphs normalized to micrometre segments.

Both graphs store node ``voxel_pos`` and edge ``centerline_voxel_points`` in
the voxel-index frame of one coordinate image. This module reads that image's
header (never its voxels), validates each graph against it and converts the
stored polylines to straight segments in micrometres. Nothing is rasterized,
smoothed, snapped, pruned or reconnected.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from skelhub.core import BettiNumbers, CoordinateImageInfo, GraphInputSummary
from skelhub.io.graphml_reader import GraphVoxelGeometry, read_graph_voxel_geometry

from .validation import AFFINE_MATCH_FRACTION, SpatialFrame, header_spatial_unit, prepare_spatial_frame


COORDINATE_LABEL = "Coordinate image"
# Largest per-axis gap, in voxel-index units, between a path end and its incident node's voxel_pos.
ENDPOINT_TOLERANCE_VOXELS = 1e-6
# Stored world coordinates may differ from affine @ voxel_pos by this fraction of the smallest stored spacing.
WORLD_MATCH_FRACTION = AFFINE_MATCH_FRACTION
# A point is outside the image when an index lies beyond the outer voxel faces (-0.5 or shape - 0.5).
OUTSIDE_IMAGE_MARGIN_VOXELS = 0.5

STATE_CURVE_GEOMETRY = "curve_geometry"
STATE_NO_CURVE_GEOMETRY = "no_curve_geometry"
STATE_NO_NODES = "no_nodes"
EDGE_PATHS_STORED = "stored"
EDGE_PATHS_STRAIGHT = "straight_node_segments"
EDGE_PATHS_NONE = "none"


@dataclass(slots=True)
class CoordinateFrame:
    """The coordinate image's voxel-to-world transform, as stored and in micrometres."""

    path: str
    shape: tuple[int, int, int]
    stored_affine: np.ndarray
    frame: SpatialFrame

    @property
    def affine_um(self) -> np.ndarray:
        return self.frame.affine_um

    @property
    def spacing_um(self) -> tuple[float, float, float]:
        return self.frame.spacing_um

    def to_um(self, voxel_points: np.ndarray) -> np.ndarray:
        """Map voxel-index points (N, 3) to world micrometres."""
        return _apply_affine(self.frame.affine_um, voxel_points)

    def to_stored_world(self, voxel_points: np.ndarray) -> np.ndarray:
        """Map voxel-index points (N, 3) to world coordinates in the image's stored unit."""
        return _apply_affine(self.stored_affine, voxel_points)

    def info(self) -> CoordinateImageInfo:
        units = self.frame.units
        return CoordinateImageInfo(
            path=self.path,
            shape=[int(value) for value in self.shape],
            header_spatial_unit=units.header_unit,
            effective_spatial_unit=units.effective_unit,
            spatial_unit_source=units.source,
            spacing_um=[float(value) for value in self.spacing_um],
            affine_um=self.affine_um.tolist(),
        )


@dataclass(slots=True)
class GraphCurveInput:
    """One validated graph: connectivity for topology and nonzero segments in micrometres."""

    label: str
    path: str
    node_count: int
    edge_count: int
    degrees: np.ndarray
    component_count: int
    self_loops: int
    parallel_edges: int
    segment_starts_um: np.ndarray
    segment_ends_um: np.ndarray
    edge_paths: str
    reversed_edge_paths: int
    repeated_points_skipped: int
    points_outside_image: int
    warnings: list[str] = field(default_factory=list)

    @property
    def isolated_nodes(self) -> int:
        return int(np.count_nonzero(self.degrees == 0))

    @property
    def endpoints(self) -> int:
        """Nodes of degree 1; a self-loop adds 2 to its node's degree."""
        return int(np.count_nonzero(self.degrees == 1))

    @property
    def segment_lengths_um(self) -> np.ndarray:
        return np.linalg.norm(self.segment_ends_um - self.segment_starts_um, axis=1)

    @property
    def total_length_um(self) -> float:
        return float(np.sum(self.segment_lengths_um, dtype=np.float64))

    @property
    def state(self) -> str:
        if self.node_count == 0:
            return STATE_NO_NODES
        return STATE_CURVE_GEOMETRY if self.segment_starts_um.shape[0] else STATE_NO_CURVE_GEOMETRY

    def betti_numbers(self) -> BettiNumbers:
        """beta_0 = components, beta_1 = E - V + beta_0, beta_2 = 0 (structural), chi = V - E."""
        beta_0 = self.component_count
        return BettiNumbers(
            beta_0=beta_0,
            beta_1=self.edge_count - self.node_count + beta_0,
            beta_2=0,
            euler_characteristic=self.node_count - self.edge_count,
        )

    def summary(self, length_samples: int = 0) -> GraphInputSummary:
        return GraphInputSummary(
            path=self.path,
            state=self.state,
            nodes=self.node_count,
            edges=self.edge_count,
            isolated_nodes=self.isolated_nodes,
            self_loops=self.self_loops,
            parallel_edges=self.parallel_edges,
            total_length_um=self.total_length_um,
            segments=int(self.segment_starts_um.shape[0]),
            edge_paths=self.edge_paths,
            reversed_edge_paths=self.reversed_edge_paths,
            repeated_points_skipped=self.repeated_points_skipped,
            points_outside_image=self.points_outside_image,
            length_samples=int(length_samples),
        )


def read_coordinate_image(path: str | Path, *, supplied_unit: str | None = None) -> CoordinateFrame:
    """Read and validate a coordinate image's header; its voxel data are not loaded.

    The image must be a 3D ``.nii`` / ``.nii.gz`` with an orthogonal affine.
    Units follow the NIfTI rules: a known header unit is used as is and
    ``supplied_unit`` (``--coordinate-spatial-unit``) only labels an unknown one.
    """
    image_path = Path(path)
    if not image_path.exists():
        raise FileNotFoundError(f"{COORDINATE_LABEL} does not exist: {image_path}")
    if not str(image_path).lower().endswith((".nii", ".nii.gz")):
        raise ValueError(f"{COORDINATE_LABEL} must be a .nii or .nii.gz file. Got: {image_path}")
    try:
        image = nib.load(str(image_path))
    except Exception as exc:  # nibabel raises several concrete types for unreadable files
        raise ValueError(f"Failed to read {COORDINATE_LABEL.lower()} header '{image_path}': {exc}") from exc
    shape = tuple(int(size) for size in image.shape)
    if len(shape) != 3:
        raise ValueError(f"{COORDINATE_LABEL} must be a 3D volume. Got shape {shape}.")
    if any(size <= 0 for size in shape):
        raise ValueError(f"{COORDINATE_LABEL} has no voxels (shape {shape}).")
    stored_affine = np.array(image.affine, dtype=float)
    frame = prepare_spatial_frame(
        stored_affine,
        header_spatial_unit(image.header),
        label=COORDINATE_LABEL,
        supplied_unit=supplied_unit,
        role="coordinate",
        header_spacing=tuple(float(value) for value in image.header.get_zooms()[:3]),
    )
    return CoordinateFrame(path=str(image_path), shape=shape, stored_affine=stored_affine, frame=frame)  # type: ignore[arg-type]


def prepare_graph_input(path: str | Path, coordinates: CoordinateFrame, *, label: str) -> GraphCurveInput:
    """Read one GraphML and validate it against the coordinate image.

    - Directed graphs are rejected; self-loops and parallel edges are kept.
    - Stored world coordinates (node X/Y/Z, ``centerline_world_points``) must
      match the coordinate image's affine applied to the voxel positions.
    - Each path must start and end at its incident nodes, in either order;
      reversed paths are flipped without changing geometry.
    - Exact consecutive repeats are skipped; an edge with no length is rejected.
    - A file that declares no edge paths uses each edge's straight node segment.
    """
    graph_path = Path(path)
    if not graph_path.exists():
        raise FileNotFoundError(f"{label} does not exist: {graph_path}")
    try:
        geometry = read_graph_voxel_geometry(graph_path, allow_empty=True, allow_missing_edge_paths=True)
    except ValueError as exc:
        raise ValueError(f"{label}: {exc}") from exc
    if geometry.directed:
        raise ValueError(
            f"{label} is a directed graph ({graph_path}). GraphML evaluation needs undirected graphs; "
            "direction would otherwise be silently ignored."
        )

    _check_world_positions(geometry, coordinates, label=label)
    node_count = len(geometry.node_ids)
    edges = geometry.edge_indices
    degrees = np.bincount(edges.reshape(-1), minlength=node_count) if node_count else np.zeros(0, dtype=int)
    self_loops = int(np.count_nonzero(edges[:, 0] == edges[:, 1])) if len(edges) else 0
    pair_counts = Counter(tuple(sorted((int(a), int(b)))) for a, b in edges)
    parallel_edges = int(sum(count - 1 for count in pair_counts.values()))

    starts, ends, reversed_paths, skipped, outside_paths = _edge_segments(geometry, coordinates, label=label)
    outside = outside_paths + _count_outside(geometry.voxel_positions, coordinates.shape)
    edge_paths = (
        EDGE_PATHS_NONE if not len(edges) else EDGE_PATHS_STORED if geometry.edge_paths_stored else EDGE_PATHS_STRAIGHT
    )

    result = GraphCurveInput(
        label=label,
        path=str(graph_path),
        node_count=node_count,
        edge_count=int(len(edges)),
        degrees=degrees,
        component_count=_component_count(node_count, edges),
        self_loops=self_loops,
        parallel_edges=parallel_edges,
        segment_starts_um=starts,
        segment_ends_um=ends,
        edge_paths=edge_paths,
        reversed_edge_paths=reversed_paths,
        repeated_points_skipped=skipped,
        points_outside_image=outside,
    )
    result.warnings.extend(_input_warnings(result, coordinates))
    return result


def _input_warnings(graph: GraphCurveInput, coordinates: CoordinateFrame) -> list[str]:
    warnings = []
    if graph.isolated_nodes:
        warnings.append(
            f"{graph.label} has {graph.isolated_nodes} isolated node(s). They count in topology "
            "(components, Euler characteristic) but carry no curve geometry."
        )
    if graph.edge_paths == EDGE_PATHS_STRAIGHT:
        warnings.append(
            f"{graph.label} declares no 'centerline_voxel_points'; each edge is evaluated as the straight "
            "segment between its two nodes."
        )
    if graph.points_outside_image:
        shape = " x ".join(str(size) for size in coordinates.shape)
        warnings.append(
            f"{graph.label} has {graph.points_outside_image} node or path point(s) outside the coordinate "
            f"image's voxel extent (shape {shape}). Evaluation continued; check that the coordinate image "
            "is the one the graph was built on."
        )
    return warnings


def _edge_segments(
    geometry: GraphVoxelGeometry, coordinates: CoordinateFrame, *, label: str
) -> tuple[np.ndarray, np.ndarray, int, int, int]:
    """Oriented, de-duplicated edge paths as micrometre segments, plus diagnostics counts."""
    positions = geometry.voxel_positions
    starts: list[np.ndarray] = []
    ends: list[np.ndarray] = []
    reversed_paths = skipped = outside = 0
    world_paths = geometry.edge_world_paths
    tolerance = WORLD_MATCH_FRACTION * _min_stored_spacing(coordinates)
    for index, (source, target) in enumerate(geometry.edge_indices):
        name = _edge_name(geometry, index)
        source_pos, target_pos = positions[source], positions[target]
        if geometry.edge_paths_stored:
            path = geometry.edge_voxel_paths[index]
            outside += _count_outside(path, coordinates.shape)
            if world_paths is not None:
                difference = _max_difference(coordinates.to_stored_world(path), world_paths[index])
                if difference > tolerance:
                    raise ValueError(
                        f"{label} {name}: stored centerline_world_points differ from the coordinate image's "
                        f"affine applied to centerline_voxel_points by up to {difference:.6g} (stored image "
                        f"units; tolerance {tolerance:.3g}). The graph was probably built on another image."
                    )
            if _ends_match(path, source_pos, target_pos):
                pass
            elif _ends_match(path, target_pos, source_pos):
                path = path[::-1]
                reversed_paths += 1
            else:
                raise ValueError(
                    f"{label} {name}: centerline_voxel_points run from {path[0].tolist()} to "
                    f"{path[-1].tolist()}, but the incident nodes are at {source_pos.tolist()} and "
                    f"{target_pos.tolist()} (tolerance {ENDPOINT_TOLERANCE_VOXELS:g} voxel per axis)."
                )
        else:
            path = np.vstack([source_pos, target_pos])
        keep = np.ones(len(path), dtype=bool)
        keep[1:] = np.any(path[1:] != path[:-1], axis=1)
        skipped += int(np.count_nonzero(~keep))
        path = path[keep]
        if len(path) < 2:
            raise ValueError(
                f"{label} {name} has zero length: every stored point is the same position "
                f"{path[0].tolist()}. Remove the edge or store its geometry."
            )
        path_um = coordinates.to_um(path)
        starts.append(path_um[:-1])
        ends.append(path_um[1:])
    if not starts:
        empty = np.empty((0, 3), dtype=float)
        return empty, empty.copy(), reversed_paths, skipped, outside
    return np.vstack(starts), np.vstack(ends), reversed_paths, skipped, outside


def _check_world_positions(geometry: GraphVoxelGeometry, coordinates: CoordinateFrame, *, label: str) -> None:
    if geometry.world_positions is None or not len(geometry.node_ids):
        return
    tolerance = WORLD_MATCH_FRACTION * _min_stored_spacing(coordinates)
    expected = coordinates.to_stored_world(geometry.voxel_positions)
    difference = np.max(np.abs(expected - geometry.world_positions), axis=1)
    worst = int(np.argmax(difference))
    if float(difference[worst]) > tolerance:
        raise ValueError(
            f"{label}: stored node world coordinates (X/Y/Z) differ from the coordinate image's affine applied "
            f"to voxel_pos by up to {float(difference[worst]):.6g} at node '{geometry.node_ids[worst]}' "
            f"(stored image units; tolerance {tolerance:.3g}). The graph was probably built on another image, "
            "or on the same grid stored in another unit. SkelHub does not choose between conflicting coordinates."
        )


def _component_count(node_count: int, edges: np.ndarray) -> int:
    if node_count == 0:
        return 0
    if not len(edges):
        return node_count
    data = np.ones(len(edges), dtype=np.int8)
    adjacency = coo_matrix((data, (edges[:, 0], edges[:, 1])), shape=(node_count, node_count))
    count, _labels = connected_components(adjacency, directed=False)
    return int(count)


def _ends_match(path: np.ndarray, first: np.ndarray, last: np.ndarray) -> bool:
    return bool(
        np.max(np.abs(path[0] - first)) <= ENDPOINT_TOLERANCE_VOXELS
        and np.max(np.abs(path[-1] - last)) <= ENDPOINT_TOLERANCE_VOXELS
    )


def _count_outside(points: np.ndarray, shape: tuple[int, int, int]) -> int:
    if not len(points):
        return 0
    upper = np.asarray(shape, dtype=float) - OUTSIDE_IMAGE_MARGIN_VOXELS
    outside = np.any((points < -OUTSIDE_IMAGE_MARGIN_VOXELS) | (points > upper), axis=1)
    return int(np.count_nonzero(outside))


def _edge_name(geometry: GraphVoxelGeometry, index: int) -> str:
    source, target = geometry.edge_indices[index]
    return f"edge {index} ('{geometry.node_ids[source]}' - '{geometry.node_ids[target]}')"


def _max_difference(first: np.ndarray, second: np.ndarray) -> float:
    return float(np.max(np.abs(first - second)))


def _min_stored_spacing(coordinates: CoordinateFrame) -> float:
    return float(np.min(np.linalg.norm(coordinates.stored_affine[:3, :3], axis=0)))


def _apply_affine(affine: np.ndarray, points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=float).reshape(-1, 3)
    return points @ affine[:3, :3].T + affine[:3, 3]
