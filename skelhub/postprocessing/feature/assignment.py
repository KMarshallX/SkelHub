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


def _touching_cells(points: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
    """Return in-volume voxels whose closed cell contains any of ``points``.

    Uses the checker's rule: voxel ``(i, j, k)`` spans ``[i - 0.5, i + 0.5]`` per
    axis. An integer point touches only its own voxel.
    """
    # Imported here, not at module level: skelhub.postprocessing imports this package, and an
    # eager import would preload the checker and break `python -m skelhub.postprocessing.checker`.
    from skelhub.postprocessing.checker import FOREGROUND_CELL_TOLERANCE

    points = np.asarray(points, dtype=float).reshape((-1, 3))
    if len(points) == 0:
        return np.empty((0, 3), dtype=np.int64)
    radius = 0.5 + FOREGROUND_CELL_TOLERANCE
    lowest = np.ceil(points - radius).astype(np.int64)
    highest = np.floor(points + radius).astype(np.int64)
    limits = np.asarray(shape, dtype=np.int64)
    cells = []
    for offset in np.ndindex(2, 2, 2):
        candidates = lowest + np.asarray(offset, dtype=np.int64)
        valid = np.all((candidates <= highest) & (candidates >= 0) & (candidates < limits), axis=1)
        cells.append(candidates[valid])
    return np.unique(np.vstack(cells), axis=0)


def _nearest_labels(
    foreground: np.ndarray,
    graph: FeatureGraph,
    samples: list[np.ndarray],
    scale: np.ndarray,
) -> np.ndarray:
    labels = np.full(foreground.shape, BACKGROUND, dtype=np.int64)
    coordinates: list[np.ndarray] = []
    edge_indices: list[int] = []
    raw_samples: list[tuple[float, float, float]] = []
    for edge_index, edge_samples in enumerate(samples):
        for sample in edge_samples:
            coordinates.append(np.asarray(sample, dtype=float) * scale)
            edge_indices.append(edge_index)
            raw_samples.append(tuple(float(value) for value in sample))
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
        chosen = min(nearest, key=lambda index: (raw_samples[index], graph.edges[edge_indices[index]].id))
        labels[tuple(voxel)] = edge_indices[chosen]
    return labels


def edge_label_boxes(labels: np.ndarray, edge_count: int) -> list[tuple[slice, ...] | None]:
    """Return, per edge index, the bounding box of voxels labelled with it (``None`` if none).

    One pass over the volume; lets per-edge steps work on a small crop instead
    of the whole volume.
    """
    positive = np.where(labels >= 0, labels + 1, 0)
    boxes: list[tuple[slice, ...] | None] = list(ndimage.find_objects(positive, max_label=edge_count))
    return boxes + [None] * (edge_count - len(boxes))


def _keep_skeleton_anchored_components(labels: np.ndarray, samples: list[np.ndarray]) -> np.ndarray:
    output = labels.copy()
    for edge_index, (edge_samples, box) in enumerate(zip(samples, edge_label_boxes(labels, len(samples)))):
        if box is None:
            continue
        # Every voxel with this label lies inside ``box``, so its 26-connected
        # components are the same as in the whole volume.
        origin = np.asarray([axis.start for axis in box], dtype=np.int64)
        mask = labels[box] == edge_index
        components, _ = ndimage.label(mask, structure=_FULL_26)
        anchors: set[int] = set()
        for voxel in _touching_cells(edge_samples, labels.shape):
            position = tuple(int(value) for value in voxel)
            if labels[position] == edge_index:
                anchors.add(int(components[tuple(voxel - origin)]))
        cropped_output = output[box]
        if anchors:
            keep = np.isin(components, list(anchors))
            cropped_output[mask & ~keep] = UNLABELED
        else:
            cropped_output[mask] = UNLABELED
    return output


def _flood_unlabeled_regions(labels: np.ndarray, graph: FeatureGraph) -> np.ndarray:
    output = labels.copy()
    regions, _ = ndimage.label(output == UNLABELED, structure=_FULL_26)
    shape = tuple(int(value) for value in labels.shape)
    edge_index_by_id = {edge.id: index for index, edge in enumerate(graph.edges)}
    for region_id, box in enumerate(ndimage.find_objects(regions), start=1):
        if box is None:
            continue
        origin = np.asarray([axis.start for axis in box], dtype=np.int64)
        queue: list[tuple[int, int, int, int, int]] = []
        best: dict[tuple[int, int, int], tuple[int, int]] = {}
        for coordinate in np.argwhere(regions[box] == region_id) + origin:
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
                if _inside(neighbor, shape) and regions[neighbor] == region_id:
                    heapq.heappush(queue, (distance + 1, edge_id, *neighbor))
    return output


def assign_foreground_to_edges(
    foreground: np.ndarray,
    graph: FeatureGraph,
    samples: list[np.ndarray],
    scale: np.ndarray,
) -> np.ndarray:
    """Assign foreground to edges by nearest centreline sample in one measurement space.

    ``samples`` holds each edge's voxel-space samples in ``graph.edges`` order.
    """
    initial = _nearest_labels(foreground, graph, samples, np.asarray(scale, dtype=float))
    anchored = _keep_skeleton_anchored_components(initial, samples)
    return _flood_unlabeled_regions(anchored, graph)
