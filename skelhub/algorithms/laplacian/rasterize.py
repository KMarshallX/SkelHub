"""Rasterize cleaned Laplacian graphs into 26-connected skeleton volumes."""

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


def rasterize_graph_26conn(graph, shape: tuple[int, int, int]) -> np.ndarray:
    """Rasterize graph nodes and edges into a binary 3D skeleton volume."""
    skeleton = np.zeros(tuple(int(v) for v in shape), dtype=np.uint8)
    if graph is None:
        return skeleton

    for node in graph.GetNodes():
        voxel = _clip_voxel(np.round(graph.nodes[node]["pos"]).astype(int), skeleton.shape)
        skeleton[voxel] = 1

    for u, v in graph.GetEdges():
        start = graph.nodes[u]["pos"]
        end = graph.nodes[v]["pos"]
        for voxel in _edge_voxels(start, end, skeleton.shape):
            skeleton[voxel] = 1
    return skeleton
