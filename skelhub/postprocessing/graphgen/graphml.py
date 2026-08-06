"""GraphML export for SkelHub proto-graphs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import igraph as ig
import numpy as np

from .protograph import ProtoGraph, voxel_to_world


def _json_points(points: list[tuple[float, float, float]] | list[tuple[int, int, int]]) -> str:
    return json.dumps([list(point) for point in points], separators=(",", ":"))


def _float_point(point: Sequence[float | int]) -> tuple[float, float, float]:
    return (float(point[0]), float(point[1]), float(point[2]))


def _endpoint_inclusive_float_path(
    source: Sequence[float],
    interior: Sequence[Sequence[float | int]],
    target: Sequence[float],
) -> list[tuple[float, float, float]]:
    """Return an oriented float path containing both incident node positions."""
    points = [
        _float_point(source),
        *(_float_point(point) for point in interior),
        _float_point(target),
    ]
    deduplicated: list[tuple[float, float, float]] = []
    for point in points:
        if not deduplicated or point != deduplicated[-1]:
            deduplicated.append(point)
    return deduplicated


def _rounded_segment(
    start: Sequence[float | int],
    end: Sequence[float | int],
) -> list[tuple[int, int, int]]:
    """Return a 26-connected line between two rounded voxel positions."""
    start_voxel = np.rint(np.asarray(start, dtype=float)).astype(int)
    end_voxel = np.rint(np.asarray(end, dtype=float)).astype(int)
    delta = end_voxel - start_voxel
    steps = int(np.max(np.abs(delta)))
    if steps == 0:
        return [tuple(int(value) for value in start_voxel)]
    points: list[tuple[int, int, int]] = []
    for index in range(steps + 1):
        point = np.rint(start_voxel + delta * (index / steps)).astype(int)
        voxel = tuple(int(value) for value in point)
        if not points or voxel != points[-1]:
            points.append(voxel)
    return points


def _endpoint_inclusive_voxel_path(
    source: Sequence[float],
    interior: Sequence[tuple[int, int, int]],
    target: Sequence[float],
) -> list[tuple[int, int, int]]:
    """Preserve interior voxels and connect both rounded incident positions."""
    if not interior:
        return _rounded_segment(source, target)
    points = _rounded_segment(source, interior[0])
    for voxel in interior[1:]:
        if voxel != points[-1]:
            points.append(voxel)
    for voxel in _rounded_segment(interior[-1], target)[1:]:
        if voxel != points[-1]:
            points.append(voxel)
    return points


def protograph_to_igraph(graph: ProtoGraph) -> ig.Graph:
    """Convert a proto-graph to an igraph object ready for GraphML export."""
    if not graph.nodes:
        raise ValueError("Generated proto-graph is empty; no GraphML can be written.")

    output = ig.Graph(directed=False)
    output.add_vertices(len(graph.nodes))

    for node in graph.nodes:
        vertex = output.vs[node.id]
        voxel_pos = node.voxel_pos
        world_pos = voxel_to_world(graph.affine, voxel_pos)
        vertex["proto_id"] = int(node.id)
        vertex["name"] = str(node.id)
        vertex["X"] = world_pos[0]
        vertex["Y"] = world_pos[1]
        vertex["Z"] = world_pos[2]
        vertex["voxel_pos"] = json.dumps(list(voxel_pos), separators=(",", ":"))
        vertex["voxels"] = _json_points(node.voxels)
        vertex["kind"] = node.kind
        vertex["at_sample_border"] = bool(node.at_sample_border)

    output.add_edges([(edge.node1, edge.node2) for edge in graph.edges])

    for edge, ig_edge in zip(graph.edges, output.es):
        if ig_edge.source == edge.node1 and ig_edge.target == edge.node2:
            interior_voxels = list(edge.voxels)
        elif ig_edge.source == edge.node2 and ig_edge.target == edge.node1:
            interior_voxels = list(reversed(edge.voxels))
        else:
            raise ValueError(f"Edge {edge.id} endpoints do not match its GraphML edge.")
        source_voxel_pos = graph.nodes[ig_edge.source].voxel_pos
        target_voxel_pos = graph.nodes[ig_edge.target].voxel_pos
        centerline_voxel_points = _endpoint_inclusive_float_path(
            source_voxel_pos,
            interior_voxels,
            target_voxel_pos,
        )
        centerline_voxels = _endpoint_inclusive_voxel_path(
            source_voxel_pos,
            interior_voxels,
            target_voxel_pos,
        )
        centerline_world_points = [
            voxel_to_world(graph.affine, voxel)
            for voxel in centerline_voxel_points
        ]
        ig_edge["proto_edge_id"] = int(edge.id)
        ig_edge["centerline_voxels"] = _json_points(centerline_voxels)
        ig_edge["centerline_voxel_points"] = _json_points(centerline_voxel_points)
        ig_edge["centerline_world_points"] = _json_points(centerline_world_points)
        ig_edge["num_centerline_voxels"] = len(centerline_voxels)

    return output


def write_graphml(graph: ProtoGraph, output_path: str | Path) -> ig.Graph:
    """Write a proto-graph to GraphML and return the igraph representation."""
    output = protograph_to_igraph(graph)
    if output.ecount() == 0:
        raise ValueError("Generated proto-graph has no edges; no GraphML can be written.")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    output.write_graphml(str(path))
    return output
