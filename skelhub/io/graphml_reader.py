"""GraphML reading and voxel-geometry parsing shared by postprocessing and viewers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import warnings

import igraph as ig
import numpy as np


CENTERLINE_VOXEL_POINTS = "centerline_voxel_points"
CENTERLINE_WORLD_POINTS = "centerline_world_points"


def parse_graphml_point(value: object, *, label: str) -> np.ndarray:
    """Parse one JSON-encoded three-dimensional GraphML point."""
    try:
        point = np.asarray(json.loads(str(value)), dtype=float)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be a JSON 3D point") from exc
    if point.shape != (3,) or not np.isfinite(point).all():
        raise ValueError(f"{label} must contain three finite coordinates")
    return point


def parse_graphml_path(value: object, *, label: str) -> np.ndarray:
    """Parse one JSON-encoded GraphML polyline."""
    try:
        points = np.asarray(json.loads(str(value)), dtype=float)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be a JSON list of 3D points") from exc
    if points.ndim != 2 or points.shape[1:] != (3,) or len(points) == 0:
        raise ValueError(f"{label} must contain at least one 3D point")
    if not np.isfinite(points).all():
        raise ValueError(f"{label} must contain only finite coordinates")
    return points


def graph_node_ids(graph: ig.Graph) -> tuple[str, ...]:
    """Return GraphML node IDs, falling back to names and then vertex indices."""
    if "id" in graph.vs.attribute_names():
        return tuple(str(value) for value in graph.vs["id"])
    if "name" in graph.vs.attribute_names():
        return tuple(str(value) for value in graph.vs["name"])
    return tuple(str(index) for index in range(graph.vcount()))


def read_graphml(input_path: str | Path) -> ig.Graph:
    """Read a GraphML file with igraph, raising ``ValueError`` on failure."""
    path = Path(input_path)
    if not path.is_file():
        raise ValueError(f"GraphML input does not exist: {path}")
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Could not add vertex ids, there is already an 'id' vertex attribute",
                category=RuntimeWarning,
            )
            return ig.Graph.Read_GraphML(str(path))
    except Exception as exc:  # igraph raises several concrete types
        raise ValueError(f"Failed to load GraphML file '{path}': {exc}") from exc


@dataclass(slots=True)
class GraphVoxelGeometry:
    """Graph nodes and edge paths expressed in voxel-index coordinates.

    World coordinates are kept only as stored in the file, so callers can check
    them against a paired image instead of trusting them.
    """

    source_path: str
    node_ids: tuple[str, ...]
    voxel_positions: np.ndarray
    edge_indices: np.ndarray
    edge_voxel_paths: tuple[np.ndarray, ...]
    world_positions: np.ndarray | None = None
    edge_world_paths: tuple[np.ndarray, ...] | None = None


def _optional_world_positions(graph: ig.Graph) -> np.ndarray | None:
    names = set(graph.vs.attribute_names())
    for axes in (("X", "Y", "Z"), ("x", "y", "z")):
        present = [axis for axis in axes if axis in names]
        if not present:
            continue
        if len(present) != 3:
            raise ValueError(f"GraphML node coordinates are incomplete: found {present}, expected {list(axes)}")
        try:
            positions = np.column_stack([np.asarray(graph.vs[axis], dtype=float) for axis in axes])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"GraphML node attributes {list(axes)} must be numeric") from exc
        if not np.isfinite(positions).all():
            raise ValueError(f"GraphML node attributes {list(axes)} must be finite for every node")
        return positions
    return None


def read_graph_voxel_geometry(input_path: str | Path) -> GraphVoxelGeometry:
    """Load node ``voxel_pos`` values and ``centerline_voxel_points`` edge paths.

    Every node must provide ``voxel_pos``. When the graph has edges, every edge
    must provide ``centerline_voxel_points``. ``X/Y/Z`` and
    ``centerline_world_points`` are optional and returned unchanged.
    """
    graph = read_graphml(input_path)
    if graph.vcount() == 0:
        raise ValueError("GraphML file does not contain any nodes.")
    if "voxel_pos" not in graph.vs.attribute_names():
        raise ValueError("GraphML nodes must provide 'voxel_pos'.")
    node_ids = graph_node_ids(graph)
    voxel_positions = np.vstack([
        parse_graphml_point(value, label=f"node '{node_ids[index]}' voxel_pos")
        for index, value in enumerate(graph.vs["voxel_pos"])
    ])
    world_positions = _optional_world_positions(graph)

    edge_indices = (
        np.asarray([edge.tuple for edge in graph.es], dtype=int)
        if graph.ecount() else np.empty((0, 2), dtype=int)
    )
    edge_attributes = set(graph.es.attribute_names())
    edge_voxel_paths: tuple[np.ndarray, ...] = ()
    edge_world_paths: tuple[np.ndarray, ...] | None = None
    if graph.ecount():
        if CENTERLINE_VOXEL_POINTS not in edge_attributes:
            raise ValueError(f"GraphML edges must provide '{CENTERLINE_VOXEL_POINTS}' for curved edge rendering.")
        edge_voxel_paths = tuple(
            parse_graphml_path(edge[CENTERLINE_VOXEL_POINTS], label=f"edge {edge.index} {CENTERLINE_VOXEL_POINTS}")
            for edge in graph.es
        )
        if CENTERLINE_WORLD_POINTS in edge_attributes:
            edge_world_paths = tuple(
                parse_graphml_path(edge[CENTERLINE_WORLD_POINTS], label=f"edge {edge.index} {CENTERLINE_WORLD_POINTS}")
                for edge in graph.es
            )
            for index, (voxel_path, world_path) in enumerate(zip(edge_voxel_paths, edge_world_paths)):
                if len(voxel_path) != len(world_path):
                    raise ValueError(
                        f"edge {index} has {len(voxel_path)} {CENTERLINE_VOXEL_POINTS} but "
                        f"{len(world_path)} {CENTERLINE_WORLD_POINTS}"
                    )

    return GraphVoxelGeometry(
        source_path=str(input_path),
        node_ids=node_ids,
        voxel_positions=voxel_positions,
        edge_indices=edge_indices,
        edge_voxel_paths=edge_voxel_paths,
        world_positions=world_positions,
        edge_world_paths=edge_world_paths,
    )
