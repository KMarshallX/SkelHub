"""Geodesic distance module."""

from __future__ import annotations

import heapq

import numpy as np

from .maximal_balls import NEIGHBOUR_DISTANCES, NEIGHBOUR_OFFSETS


def compute_geodesic_distance(object_mask: np.ndarray, source_mask: np.ndarray) -> np.ndarray:
    """Return geometric geodesic distance from sources over object voxels only."""
    object_support = np.asarray(object_mask, dtype=bool)
    sources = np.asarray(source_mask, dtype=bool)

    if object_support.ndim != 3 or sources.ndim != 3:
        raise ValueError("compute_geodesic_distance expects 3D inputs.")
    if object_support.shape != sources.shape:
        raise ValueError("object_mask and source_mask must have the same shape.")

    distances = np.full(object_support.shape, np.inf, dtype=np.float32)
    active_sources = np.argwhere(object_support & sources)
    if active_sources.size == 0:
        return distances

    heap: list[tuple[float, int, int, int]] = []
    for z, y, x in active_sources:
        distances[z, y, x] = 0.0
        heapq.heappush(heap, (0.0, int(z), int(y), int(x)))
    shape = object_support.shape
    while heap:
        current_distance, z, y, x = heapq.heappop(heap)
        if current_distance > float(distances[z, y, x]):
            continue

        for offset, step_distance in zip(NEIGHBOUR_OFFSETS, NEIGHBOUR_DISTANCES, strict=True):
            nz = z + int(offset[0])
            ny = y + int(offset[1])
            nx = x + int(offset[2])

            if nz < 0 or ny < 0 or nx < 0 or nz >= shape[0] or ny >= shape[1] or nx >= shape[2]:
                continue
            if not object_support[nz, ny, nx]:
                continue

            candidate = np.float32(current_distance + float(step_distance))
            if candidate < distances[nz, ny, nx]:
                distances[nz, ny, nx] = candidate
                heapq.heappush(heap, (float(candidate), nz, ny, nx))
    return distances
