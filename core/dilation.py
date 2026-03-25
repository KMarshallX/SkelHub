"""Local scale-adaptive dilation module."""

from __future__ import annotations

import heapq

import numpy as np

from core.maximal_balls import NEIGHBOUR_DISTANCES, NEIGHBOUR_OFFSETS


def local_scale_adaptive_dilation(
    object_mask: np.ndarray,
    branch_coords: list[tuple],
    fdt: np.ndarray,
) -> np.ndarray:
    """Return the branch dilated support within the object volume.

    The propagation follows the Milestone 5 update rule
    `DS(p) = max_{q in N*(p)} DS(q) - |p-q|`, seeded with `2 * FDT(p)` on the
    branch and `-inf` elsewhere. Voxels with final `DS >= 0` are marked.
    """
    object_support = np.asarray(object_mask, dtype=bool)
    fdt_values = np.asarray(fdt, dtype=np.float32)

    if object_support.ndim != 3 or fdt_values.ndim != 3:
        raise ValueError("local_scale_adaptive_dilation expects 3D inputs.")
    if object_support.shape != fdt_values.shape:
        raise ValueError("object_mask and fdt must have the same shape.")
    if not branch_coords:
        return np.zeros_like(object_support, dtype=bool)

    ds = np.full(object_support.shape, -np.inf, dtype=np.float64)
    heap: list[tuple[float, int, int, int]] = []
    shape = object_support.shape

    for coord in branch_coords:
        voxel = tuple(int(value) for value in coord)
        if len(voxel) != 3:
            raise ValueError("branch_coords must contain 3D coordinates.")
        if any(index < 0 or index >= limit for index, limit in zip(voxel, shape, strict=True)):
            raise ValueError("branch_coords contains a coordinate outside the volume bounds.")
        if not object_support[voxel]:
            continue

        initial_scale = 2.0 * float(fdt_values[voxel])
        if initial_scale > ds[voxel]:
            ds[voxel] = initial_scale
            heapq.heappush(heap, (-initial_scale, voxel[0], voxel[1], voxel[2]))

    if not heap:
        return np.zeros_like(object_support, dtype=bool)

    convergence_tolerance = 1e-6
    while heap:
        neg_score, z, y, x = heapq.heappop(heap)
        current_score = -neg_score
        if current_score + convergence_tolerance < float(ds[z, y, x]):
            continue

        for offset, step_distance in zip(NEIGHBOUR_OFFSETS, NEIGHBOUR_DISTANCES, strict=True):
            nz = z + int(offset[0])
            ny = y + int(offset[1])
            nx = x + int(offset[2])

            if nz < 0 or ny < 0 or nx < 0 or nz >= shape[0] or ny >= shape[1] or nx >= shape[2]:
                continue
            if not object_support[nz, ny, nx]:
                continue

            candidate_score = current_score - float(step_distance)
            if candidate_score > float(ds[nz, ny, nx]) + convergence_tolerance:
                ds[nz, ny, nx] = candidate_score
                heapq.heappush(heap, (-candidate_score, nz, ny, nx))

    dilated = np.zeros_like(object_support, dtype=bool)
    dilated[object_support] = ds[object_support] >= -convergence_tolerance
    return dilated
