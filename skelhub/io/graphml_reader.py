"""GraphML reading and voxel-geometry parsing shared by postprocessing and viewers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import warnings
import xml.etree.ElementTree as ElementTree

import igraph as ig
import numpy as np


CENTERLINE_VOXEL_POINTS = "centerline_voxel_points"
CENTERLINE_WORLD_POINTS = "centerline_world_points"
NODE_GEOMETRY_ATTRIBUTES = frozenset({"id", "voxel_pos", "X", "Y", "Z", "x", "y", "z"})
EDGE_GEOMETRY_ATTRIBUTES = frozenset({CENTERLINE_VOXEL_POINTS, CENTERLINE_WORLD_POINTS})


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


@dataclass(slots=True)
class _GeometryTables:
    """GraphML node and edge attributes needed for voxel geometry, in file order."""

    node_ids: list[str]
    node_values: dict[str, list[object]]
    edge_ends: list[tuple[str, str]]
    edge_values: dict[str, list[object]]


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _read_geometry_tables(path: Path) -> _GeometryTables:
    """Stream the first GraphML graph with the standard-library XML parser.

    igraph's C GraphML reader keeps its warning and error handlers per thread.
    On any thread other than the one that imported igraph it prints warnings
    straight to the terminal and aborts the process on malformed files, so the
    GUI's worker threads read geometry here instead. Conventions follow igraph:
    file order, key defaults for missing data, missing values as None, and a
    node data attribute named ``id`` taking the place of the ``<node id>``.
    """
    keys: dict[str, tuple[str, str, object]] = {}
    declared = {"node": set(), "edge": set()}
    node_ids: list[str] = []
    raw_nodes: list[dict[str, object]] = []
    edge_ends: list[tuple[str, str]] = []
    raw_edges: list[dict[str, object]] = []
    depth = 0
    finished = False
    root_checked = False
    context = ElementTree.iterparse(str(path), events=("start", "end"))
    for event, element in context:
        tag = _local_tag(element.tag)
        if not root_checked:
            if tag != "graphml":
                raise ValueError(f"root element is <{tag}>, not <graphml>")
            root_checked = True
        if finished:
            continue
        if event == "start":
            if tag == "graph":
                depth += 1
                if depth > 1:
                    raise ValueError("nested graphs are not supported")
            continue
        if tag == "key":
            domain, name, key_id = element.get("for", "all"), element.get("attr.name"), element.get("id")
            if key_id and name:
                default = next((child.text for child in element if _local_tag(child.tag) == "default"), None)
                keys[key_id] = (domain, name, default)
                for kind in ("node", "edge"):
                    if domain in (kind, "all"):
                        declared[kind].add(name)
        elif tag in ("node", "edge") and depth == 1:
            values = {}
            for child in element:
                if _local_tag(child.tag) == "data" and child.get("key") in keys:
                    domain, name, _default = keys[child.get("key")]
                    if domain in (tag, "all"):
                        values[name] = child.text if child.text is not None else ""
            if tag == "node":
                node_id = element.get("id")
                if node_id is None:
                    raise ValueError(f"node {len(node_ids)} has no id")
                node_ids.append(node_id)
                raw_nodes.append(values)
            else:
                source, target = element.get("source"), element.get("target")
                if source is None or target is None:
                    raise ValueError(f"edge {len(edge_ends)} needs both source and target")
                edge_ends.append((source, target))
                raw_edges.append(values)
            element.clear()
        elif tag == "graph":
            depth -= 1
            finished = depth == 0
    if not root_checked:
        raise ValueError("file is empty")

    def column(kind: str, name: str, rows: list[dict[str, object]]) -> list[object]:
        default = next((d for domain, n, d in keys.values() if n == name and domain in (kind, "all")), None)
        return [row.get(name, default) for row in rows]

    node_values = {name: column("node", name, raw_nodes) for name in declared["node"] & NODE_GEOMETRY_ATTRIBUTES}
    edge_values = {name: column("edge", name, raw_edges) for name in declared["edge"] & EDGE_GEOMETRY_ATTRIBUTES}
    if len(set(node_ids)) != len(node_ids):
        raise ValueError("node ids are not unique")
    known = set(node_ids)
    for index, (source, target) in enumerate(edge_ends):
        missing = [end for end in (source, target) if end not in known]
        if missing:
            raise ValueError(f"edge {index} refers to unknown node '{missing[0]}'")
    return _GeometryTables(node_ids, node_values, edge_ends, edge_values)


def _optional_world_positions(names: set[str], values: dict[str, list[object]]) -> np.ndarray | None:
    for axes in (("X", "Y", "Z"), ("x", "y", "z")):
        present = [axis for axis in axes if axis in names]
        if not present:
            continue
        if len(present) != 3:
            raise ValueError(f"GraphML node coordinates are incomplete: found {present}, expected {list(axes)}")
        try:
            positions = np.column_stack([
                np.asarray([np.nan if value is None else value for value in values[axis]], dtype=float) for axis in axes
            ])
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

    Parsed with the standard-library XML parser rather than igraph, so it is
    safe on worker threads; node IDs follow ``graph_node_ids``.
    """
    path = Path(input_path)
    if not path.is_file():
        raise ValueError(f"GraphML input does not exist: {path}")
    try:
        tables = _read_geometry_tables(path)
    except (ElementTree.ParseError, ValueError) as exc:
        raise ValueError(f"Failed to load GraphML file '{path}': {exc}") from exc
    if not tables.node_ids:
        raise ValueError("GraphML file does not contain any nodes.")
    if "voxel_pos" not in tables.node_values:
        raise ValueError("GraphML nodes must provide 'voxel_pos'.")
    # As in igraph, a node data attribute named "id" replaces the <node id>.
    node_ids = (
        tuple(str(value) for value in tables.node_values["id"]) if "id" in tables.node_values
        else tuple(tables.node_ids)
    )
    voxel_positions = np.vstack([
        parse_graphml_point(value, label=f"node '{node_ids[index]}' voxel_pos")
        for index, value in enumerate(tables.node_values["voxel_pos"])
    ])
    world_positions = _optional_world_positions(set(tables.node_values), tables.node_values)

    index_of = {node_id: index for index, node_id in enumerate(tables.node_ids)}
    edge_indices = (
        np.asarray([(index_of[source], index_of[target]) for source, target in tables.edge_ends], dtype=int)
        if tables.edge_ends else np.empty((0, 2), dtype=int)
    )
    edge_voxel_paths: tuple[np.ndarray, ...] = ()
    edge_world_paths: tuple[np.ndarray, ...] | None = None
    if tables.edge_ends:
        if CENTERLINE_VOXEL_POINTS not in tables.edge_values:
            raise ValueError(f"GraphML edges must provide '{CENTERLINE_VOXEL_POINTS}' for curved edge rendering.")
        edge_voxel_paths = tuple(
            parse_graphml_path(value, label=f"edge {index} {CENTERLINE_VOXEL_POINTS}")
            for index, value in enumerate(tables.edge_values[CENTERLINE_VOXEL_POINTS])
        )
        if CENTERLINE_WORLD_POINTS in tables.edge_values:
            edge_world_paths = tuple(
                parse_graphml_path(value, label=f"edge {index} {CENTERLINE_WORLD_POINTS}")
                for index, value in enumerate(tables.edge_values[CENTERLINE_WORLD_POINTS])
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
