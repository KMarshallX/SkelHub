"""Parsing and validation for supported vessel GraphML files."""

from __future__ import annotations

import json
from pathlib import Path

import igraph as ig
import numpy as np

from .models import FeatureGraph, FeatureGraphEdge, FeatureGraphNode


def _load_point(value: object, *, label: str) -> np.ndarray:
    try:
        raw = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must contain JSON coordinates.") from exc
    point = np.asarray(raw, dtype=float)
    if point.shape != (3,) or not np.isfinite(point).all():
        raise ValueError(f"{label} must contain three finite coordinates.")
    return point


def _load_path(value: object, *, label: str) -> np.ndarray:
    try:
        raw = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must contain JSON coordinates.") from exc
    path = np.asarray(raw, dtype=float)
    if path.size == 0:
        return np.empty((0, 3), dtype=int)
    if path.ndim != 2 or path.shape[1] != 3 or not np.isfinite(path).all():
        raise ValueError(f"{label} must contain a list of finite 3D voxels.")
    rounded = np.round(path)
    if not np.allclose(path, rounded, rtol=0.0, atol=1e-8):
        raise ValueError(f"{label} must contain integer voxel indices.")
    return rounded.astype(int)


def _integer_id(value: object, *, label: str) -> int:
    number = float(value)
    if not np.isfinite(number) or not number.is_integer():
        raise ValueError(f"{label} must be an integer.")
    return int(number)


def load_feature_graph(path: str | Path, shape: tuple[int, int, int]) -> FeatureGraph:
    """Read graphgen or Laplacian GraphML geometry for feature extraction."""
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input graph does not exist: {input_path}")
    graph = ig.Graph.Read_GraphML(str(input_path))
    if graph.vcount() == 0 or graph.ecount() == 0:
        raise ValueError("Feature extraction expects a graph containing nodes and edges.")

    vertex_attrs = set(graph.vs.attributes())
    edge_attrs = set(graph.es.attributes())
    required_vertex_geometry = {"voxel_pos", "X", "Y", "Z"}
    if {"proto_id", *required_vertex_geometry}.issubset(vertex_attrs) and "proto_edge_id" in edge_attrs:
        source = "graphgen"
        node_id_attr = "proto_id"
        edge_id_attr = "proto_edge_id"
    elif {"laplacian_id", *required_vertex_geometry}.issubset(vertex_attrs) and "laplacian_edge_id" in edge_attrs:
        source = "laplacian"
        node_id_attr = "laplacian_id"
        edge_id_attr = "laplacian_edge_id"
    else:
        raise ValueError(
            "Unsupported GraphML schema. Expected graphgen or Laplacian IDs with voxel_pos and X/Y/Z."
        )
    if "centerline_voxels" not in edge_attrs:
        raise ValueError("GraphML edges must provide centerline_voxels.")

    limits = np.asarray(shape, dtype=float) - 1.0
    nodes: list[FeatureGraphNode] = []
    ids: set[int] = set()
    vertex_to_id: dict[int, int] = {}
    for vertex in graph.vs:
        node_id = _integer_id(vertex[node_id_attr], label=node_id_attr)
        if node_id in ids:
            raise ValueError(f"Duplicate graph node id: {node_id}.")
        position = _load_point(vertex["voxel_pos"], label=f"node {node_id} voxel_pos")
        display_position = np.asarray([vertex["X"], vertex["Y"], vertex["Z"]], dtype=float)
        if display_position.shape != (3,) or not np.isfinite(display_position).all():
            raise ValueError(f"Graph node {node_id} must contain finite X/Y/Z coordinates.")
        if np.any(position < 0.0) or np.any(position > limits):
            raise ValueError(f"Graph node {node_id} lies outside the input volume.")
        ids.add(node_id)
        vertex_to_id[vertex.index] = node_id
        nodes.append(FeatureGraphNode(node_id, position))

    edge_ids: set[int] = set()
    edges: list[FeatureGraphEdge] = []
    integer_limits = np.asarray(shape, dtype=int)
    for edge in graph.es:
        edge_id = _integer_id(edge[edge_id_attr], label=edge_id_attr)
        if edge_id in edge_ids:
            raise ValueError(f"Duplicate graph edge id: {edge_id}.")
        path_points = _load_path(edge["centerline_voxels"], label=f"edge {edge_id} centerline_voxels")
        if path_points.size and (np.any(path_points < 0) or np.any(path_points >= integer_limits)):
            raise ValueError(f"Graph edge {edge_id} contains an out-of-bounds centerline voxel.")
        edge_ids.add(edge_id)
        edges.append(
            FeatureGraphEdge(
                edge_id,
                vertex_to_id[edge.source],
                vertex_to_id[edge.target],
                path_points,
            )
        )

    return FeatureGraph(
        source=source,
        nodes=tuple(sorted(nodes, key=lambda node: node.id)),
        edges=tuple(sorted(edges, key=lambda edge: edge.id)),
    )
