"""Minimum-cost path module."""

from __future__ import annotations

import heapq

import numpy as np

from .maximal_balls import NEIGHBOUR_DISTANCES, NEIGHBOUR_OFFSETS


def minimum_cost_path(
    object_mask: np.ndarray,
    lsf: np.ndarray,
    source_coords: list[tuple],
    target_coord: tuple,
    epsilon: float = 0.01,
) -> list[tuple]:
    """Return the ordered minimum-cost path from the target voxel to the source set."""
    object_support = np.asarray(object_mask, dtype=bool)
    lsf_values = np.asarray(lsf, dtype=np.float32)

    if object_support.ndim != 3 or lsf_values.ndim != 3:
        raise ValueError("minimum_cost_path expects 3D inputs.")
    if object_support.shape != lsf_values.shape:
        raise ValueError("object_mask and lsf must have the same shape.")
    if epsilon <= 0.0:
        raise ValueError("epsilon must be positive.")
    if not source_coords:
        raise ValueError("source_coords must contain at least one voxel.")

    shape = object_support.shape
    target = tuple(int(value) for value in target_coord)
    if len(target) != 3:
        raise ValueError("target_coord must be a 3D coordinate.")
    if any(index < 0 or index >= limit for index, limit in zip(target, shape, strict=True)):
        raise ValueError("target_coord lies outside the volume bounds.")
    if not object_support[target]:
        return []

    source_set: set[tuple[int, int, int]] = set()
    for coord in source_coords:
        source = tuple(int(value) for value in coord)
        if len(source) != 3:
            raise ValueError("source_coords must contain 3D coordinates.")
        if any(index < 0 or index >= limit for index, limit in zip(source, shape, strict=True)):
            raise ValueError("source_coords contains a coordinate outside the volume bounds.")
        if object_support[source]:
            source_set.add(source)

    if not source_set:
        return []
    if target in source_set:
        return [target]

    distances = np.full(shape, np.inf, dtype=np.float64)
    predecessors = np.full(shape + (3,), -1, dtype=np.int16)
    heap: list[tuple[float, int, int, int]] = []

    for z, y, x in source_set:
        distances[z, y, x] = 0.0
        heapq.heappush(heap, (0.0, z, y, x))

    while heap:
        current_cost, z, y, x = heapq.heappop(heap)
        if current_cost > float(distances[z, y, x]):
            continue
        if (z, y, x) == target:
            break

        current_lsf = float(lsf_values[z, y, x])
        for offset, step_distance in zip(NEIGHBOUR_OFFSETS, NEIGHBOUR_DISTANCES, strict=True):
            nz = z + int(offset[0])
            ny = y + int(offset[1])
            nx = x + int(offset[2])

            if nz < 0 or ny < 0 or nx < 0 or nz >= shape[0] or ny >= shape[1] or nx >= shape[2]:
                continue
            if not object_support[nz, ny, nx]:
                continue

            average_lsf = 0.5 * (current_lsf + float(lsf_values[nz, ny, nx]))
            step_cost = float(step_distance) / (epsilon + average_lsf) ** 2
            candidate_cost = current_cost + step_cost

            if candidate_cost + 1e-12 < float(distances[nz, ny, nx]):
                distances[nz, ny, nx] = candidate_cost
                predecessors[nz, ny, nx] = (z, y, x)
                heapq.heappush(heap, (candidate_cost, nz, ny, nx))

    if not np.isfinite(distances[target]):
        return []

    path: list[tuple[int, int, int]] = [target]
    cursor = target
    while cursor not in source_set:
        previous = tuple(int(value) for value in predecessors[cursor])
        if previous == (-1, -1, -1):
            return []
        path.append(previous)
        cursor = previous

    return path
