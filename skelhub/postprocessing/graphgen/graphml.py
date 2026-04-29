"""GraphML export for SkelHub proto-graphs."""

from __future__ import annotations

import json
from pathlib import Path

import igraph as ig

from .protograph import ProtoGraph, voxel_to_world


def _json_points(points: list[tuple[float, float, float]] | list[tuple[int, int, int]]) -> str:
    return json.dumps([list(point) for point in points], separators=(",", ":"))


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
        centerline_points = [voxel_to_world(graph.affine, voxel) for voxel in edge.voxels]
        ig_edge["proto_edge_id"] = int(edge.id)
        ig_edge["centerline_voxels"] = _json_points(edge.voxels)
        ig_edge["centerline_points"] = _json_points(centerline_points)
        ig_edge["num_centerline_voxels"] = len(edge.voxels)

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
