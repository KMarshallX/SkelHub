"""Rasterize Laplacian graphs into 26-connected skeleton volumes."""

from __future__ import annotations

import numpy as np


def _clip_voxel(voxel: np.ndarray, shape: tuple[int, int, int]) -> tuple[int, int, int]:
    clipped = np.clip(np.asarray(voxel, dtype=int), 0, np.asarray(shape, dtype=int) - 1)
    return (int(clipped[0]), int(clipped[1]), int(clipped[2]))


def _edge_voxels(start, end, shape: tuple[int, int, int]) -> list[tuple[int, int, int]]:
    """Return a rounded line whose consecutive voxels are 26-connected."""
    start = np.round(np.asarray(start, dtype=float)).astype(int)
    end = np.round(np.asarray(end, dtype=float)).astype(int)
    delta = end - start
    steps = int(np.max(np.abs(delta)))
    if steps == 0:
        return [_clip_voxel(start, shape)]
    points = []
    for idx in range(steps + 1):
        point = np.round(start + (delta * (idx / steps))).astype(int)
        voxel = _clip_voxel(point, shape)
        if not points or points[-1] != voxel:
            points.append(voxel)
    return points


def _bezier_points(start, middle, end) -> list[np.ndarray]:
    """Sample a quadratic Bezier curve that passes through a degree-2 node."""
    start = np.asarray(start, dtype=float)
    middle = np.asarray(middle, dtype=float)
    end = np.asarray(end, dtype=float)
    control = (2.0 * middle) - (0.5 * start) - (0.5 * end)
    span = max(np.max(np.abs(middle - start)), np.max(np.abs(end - middle)))
    steps = max(int(np.ceil(span)) * 4, 2)
    points = []
    for idx in range(steps + 1):
        t = idx / steps
        point = ((1.0 - t) ** 2 * start) + (2.0 * (1.0 - t) * t * control) + (t**2 * end)
        points.append(point)
    return points


def _mark_connected_points(
    skeleton: np.ndarray,
    points: list[np.ndarray],
) -> None:
    """Mark sampled points and connect consecutive rounded samples with 26-connected lines."""
    if not points:
        return
    for point in points:
        skeleton[_clip_voxel(np.round(point).astype(int), skeleton.shape)] = 1
    for start, end in zip(points[:-1], points[1:]):
        for voxel in _edge_voxels(start, end, skeleton.shape):
            skeleton[voxel] = 1


def rasterize_graph_26conn(graph, shape: tuple[int, int, int]) -> np.ndarray:
    """Rasterize graph nodes and edges into a binary 3D skeleton volume."""
    skeleton = np.zeros(tuple(int(v) for v in shape), dtype=np.uint8)
    if graph is None:
        return skeleton

    for node in graph.GetNodes():
        voxel = _clip_voxel(np.round(graph.nodes[node]["pos"]).astype(int), skeleton.shape)
        skeleton[voxel] = 1

    covered_edges: set[frozenset] = set()
    for node in graph.GetNodes():
        neighbors = graph.GetNeighbors(node)
        if len(neighbors) != 2:
            continue
        start_node, end_node = neighbors
        start = graph.nodes[start_node]["pos"]
        middle = graph.nodes[node]["pos"]
        end = graph.nodes[end_node]["pos"]
        _mark_connected_points(skeleton, _bezier_points(start, middle, end))
        covered_edges.add(frozenset((start_node, node)))
        covered_edges.add(frozenset((node, end_node)))

    for u, v in graph.GetEdges():
        if frozenset((u, v)) in covered_edges:
            continue
        start = graph.nodes[u]["pos"]
        end = graph.nodes[v]["pos"]
        for voxel in _edge_voxels(start, end, skeleton.shape):
            skeleton[voxel] = 1
    return skeleton
