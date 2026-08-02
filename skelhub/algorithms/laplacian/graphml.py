"""GraphML export for cleaned Laplacian geometric graphs."""

from __future__ import annotations

import json
from pathlib import Path

import igraph as ig
import numpy as np

from skelhub.postprocessing.graphgen.protograph import voxel_to_world

from .rasterize import _edge_voxels


def _json_value(value) -> str:
    if isinstance(value, np.ndarray):
        value = value.tolist()
    return json.dumps(value, separators=(",", ":"))


def _continuous_edge_points(start, end) -> list[tuple[float, float, float]]:
    """Sample a straight edge in voxel space without rounding or clipping."""
    start_point = np.asarray(start, dtype=float)
    end_point = np.asarray(end, dtype=float)
    delta = end_point - start_point
    span = float(np.max(np.abs(delta)))
    if span == 0.0:
        return [tuple(float(value) for value in start_point)]

    steps = max(1, int(np.ceil(span)))
    points = [
        start_point + delta * (step / steps)
        for step in range(steps + 1)
    ]
    points[-1] = end_point
    return [tuple(float(value) for value in point) for point in points]


def write_laplacian_graphml(
    graph,
    output_path: str | Path,
    affine: np.ndarray,
    shape: tuple[int, int, int],
    *,
    include_centerline_voxel_points: bool = False,
) -> ig.Graph:
    """Write a Laplacian graph with world coordinates and voxel metadata."""
    if graph.number_of_nodes() == 0:
        raise ValueError("Cannot write GraphML for an empty Laplacian graph.")

    output = ig.Graph(directed=False)
    nodes = graph.GetNodes()
    node_to_index = {node: index for index, node in enumerate(nodes)}
    output.add_vertices(len(nodes))

    for node in nodes:
        vertex = output.vs[node_to_index[node]]
        voxel_pos = tuple(float(v) for v in graph.nodes[node]["pos"])
        world_pos = voxel_to_world(affine, voxel_pos)
        vertex["name"] = str(node)
        vertex["laplacian_id"] = int(node)
        vertex["X"] = world_pos[0]
        vertex["Y"] = world_pos[1]
        vertex["Z"] = world_pos[2]
        vertex["voxel_pos"] = _json_value(voxel_pos)
        if "r" in graph.nodes[node]:
            vertex["r"] = float(graph.nodes[node]["r"])
        if "component_index" in graph.nodes[node]:
            vertex["component_index"] = int(graph.nodes[node]["component_index"])
        if "component_label" in graph.nodes[node]:
            vertex["component_label"] = int(graph.nodes[node]["component_label"])

    edges = [(node_to_index[u], node_to_index[v]) for u, v in graph.GetEdges()]
    if edges:
        output.add_edges(edges)
        for edge_id, ((u, v), edge) in enumerate(zip(graph.GetEdges(), output.es)):
            voxels = _edge_voxels(graph.nodes[u]["pos"], graph.nodes[v]["pos"], shape)
            if include_centerline_voxel_points:
                points = _continuous_edge_points(graph.nodes[u]["pos"], graph.nodes[v]["pos"])
                edge["centerline_voxel_points"] = _json_value(points)
            edge["laplacian_edge_id"] = int(edge_id)
            edge["source_laplacian_id"] = int(u)
            edge["target_laplacian_id"] = int(v)
            edge["centerline_voxels"] = _json_value(voxels)
            edge["num_centerline_voxels"] = int(len(voxels))
            edge_attrs = graph.edges[u, v]
            if "component_index" in edge_attrs:
                edge["component_index"] = int(edge_attrs["component_index"])
            if "component_label" in edge_attrs:
                edge["component_label"] = int(edge_attrs["component_label"])
            if "component_edge_index" in edge_attrs:
                edge["component_edge_index"] = int(edge_attrs["component_edge_index"])

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    output.write_graphml(str(path))
    return output
