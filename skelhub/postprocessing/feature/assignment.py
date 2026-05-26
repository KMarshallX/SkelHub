"""Voreen-style assignment of segmented foreground to vessel graph edges."""

from __future__ import annotations

import heapq

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from .models import FeatureGraph

BACKGROUND = -1
UNLABELED = -2
_FULL_26 = np.ones((3, 3, 3), dtype=np.uint8)
_SIX_OFFSETS = (
    (-1, 0, 0),
    (1, 0, 0),
    (0, -1, 0),
    (0, 1, 0),
    (0, 0, -1),
    (0, 0, 1),
)


def _inside(pos: tuple[int, int, int], shape: tuple[int, int, int]) -> bool:
    return all(0 <= pos[axis] < shape[axis] for axis in range(3))


def _nearest_labels(foreground: np.ndarray, graph: FeatureGraph, scale: np.ndarray) -> np.ndarray:
    labels = np.full(foreground.shape, BACKGROUND, dtype=np.int64)
    coordinates: list[np.ndarray] = []
    edge_indices: list[int] = []
    raw_voxels: list[tuple[int, int, int]] = []
    for edge_index, edge in enumerate(graph.edges):
        for voxel in edge.centerline_voxels:
            raw = tuple(int(value) for value in voxel)
            coordinates.append(np.asarray(voxel, dtype=float) * scale)
            edge_indices.append(edge_index)
            raw_voxels.append(raw)
    if not coordinates:
        labels[foreground] = UNLABELED
        return labels

    points = np.asarray(coordinates, dtype=float)
    tree = cKDTree(points)
    for voxel in np.argwhere(foreground):
        point = np.asarray(voxel, dtype=float) * scale
        distance, _ = tree.query(point)
        candidate_indices = tree.query_ball_point(point, float(distance) + 1e-10)
        nearest = [
            index
            for index in candidate_indices
            if np.isclose(np.linalg.norm(points[index] - point), distance, rtol=0.0, atol=1e-9)
        ]
        chosen = min(nearest, key=lambda index: (raw_voxels[index], graph.edges[edge_indices[index]].id))
        labels[tuple(voxel)] = edge_indices[chosen]
    return labels


def _keep_skeleton_anchored_components(labels: np.ndarray, graph: FeatureGraph) -> np.ndarray:
    output = labels.copy()
    for edge_index, edge in enumerate(graph.edges):
        mask = labels == edge_index
        if not np.any(mask):
            continue
        components, _ = ndimage.label(mask, structure=_FULL_26)
        anchors: set[int] = set()
        for voxel in edge.centerline_voxels:
            position = tuple(int(value) for value in voxel)
            if labels[position] == edge_index:
                anchors.add(int(components[position]))
        if anchors:
            keep = np.isin(components, list(anchors))
            output[mask & ~keep] = UNLABELED
        else:
            output[mask] = UNLABELED
    return output


def _flood_unlabeled_regions(labels: np.ndarray, graph: FeatureGraph) -> np.ndarray:
    output = labels.copy()
    regions, count = ndimage.label(output == UNLABELED, structure=_FULL_26)
    shape = tuple(int(value) for value in labels.shape)
    edge_index_by_id = {edge.id: index for index, edge in enumerate(graph.edges)}
    for region_id in range(1, count + 1):
        region_mask = regions == region_id
        queue: list[tuple[int, int, int, int, int]] = []
        best: dict[tuple[int, int, int], tuple[int, int]] = {}
        for coordinate in np.argwhere(region_mask):
            pos = tuple(int(value) for value in coordinate)
            for offset in _SIX_OFFSETS:
                neighbor = tuple(pos[axis] + offset[axis] for axis in range(3))
                if _inside(neighbor, shape) and output[neighbor] >= 0:
                    edge_index = int(output[neighbor])
                    heapq.heappush(queue, (1, graph.edges[edge_index].id, *pos))
        while queue:
            distance, edge_id, x, y, z = heapq.heappop(queue)
            pos = (x, y, z)
            edge_index = edge_index_by_id[edge_id]
            candidate = (distance, edge_id)
            if pos in best and best[pos] <= candidate:
                continue
            best[pos] = candidate
            output[pos] = edge_index
            for offset in _SIX_OFFSETS:
                neighbor = tuple(pos[axis] + offset[axis] for axis in range(3))
                if _inside(neighbor, shape) and region_mask[neighbor]:
                    heapq.heappush(queue, (distance + 1, edge_id, *neighbor))
    return output


def assign_foreground_to_edges(foreground: np.ndarray, graph: FeatureGraph, scale: np.ndarray) -> np.ndarray:
    """Assign foreground to GraphML edge paths in one measurement space."""
    initial = _nearest_labels(foreground, graph, np.asarray(scale, dtype=float))
    anchored = _keep_skeleton_anchored_components(initial, graph)
    return _flood_unlabeled_regions(anchored, graph)
