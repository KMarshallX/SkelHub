"""Fuzzy distance transform module."""

from __future__ import annotations

import heapq
import itertools

import numpy as np
from scipy import ndimage


NEIGHBOUR_OFFSETS = np.array(
    [offset for offset in itertools.product((-1, 0, 1), repeat=3) if offset != (0, 0, 0)],
    dtype=np.int8,
)
NEIGHBOUR_DISTANCES = np.linalg.norm(NEIGHBOUR_OFFSETS, axis=1).astype(np.float64)


def _coerce_membership_volume(volume: np.ndarray) -> np.ndarray:
    """Return a float32 membership volume clipped to [0, 1]."""
    memberships = np.asarray(volume, dtype=np.float32)
    return np.clip(memberships, 0.0, 1.0)


def _is_binary_membership(volume: np.ndarray) -> bool:
    """Return True when the membership volume is exactly binary."""
    unique_values = np.unique(volume)
    return np.array_equal(unique_values, np.array([0.0], dtype=np.float32)) or np.array_equal(
        unique_values, np.array([0.0, 1.0], dtype=np.float32)
    )


def _compute_binary_fdt(volume: np.ndarray) -> np.ndarray:
    """Compute the EDT-backed FDT for a binary object."""
    object_mask = volume > 0.0
    fdt = ndimage.distance_transform_edt(object_mask)
    return fdt.astype(np.float32, copy=False)


def _shifted_mask_view(padded_mask: np.ndarray, offset: np.ndarray) -> np.ndarray:
    """Return the mask view shifted by one neighbour offset."""
    z0 = 1 + int(offset[0])
    y0 = 1 + int(offset[1])
    x0 = 1 + int(offset[2])
    return padded_mask[
        z0 : z0 + padded_mask.shape[0] - 2,
        y0 : y0 + padded_mask.shape[1] - 2,
        x0 : x0 + padded_mask.shape[2] - 2,
    ]


def _initialize_fuzzy_boundary_distances(memberships: np.ndarray) -> tuple[np.ndarray, list[tuple[float, int, int, int]]]:
    """Create the initial frontier for fuzzy boundary propagation.

    Eq. 1 can be interpreted as the minimum weighted path length from an object
    voxel to the boundary, using local step weights
    `0.5 * (mu(p) + mu(q)) * |p - q|`. For the final half-step to an exterior
    point where `mu = 0`, the seed cost becomes `0.5 * mu(p) * |p - b|`.
    """
    object_mask = memberships > 0.0
    distance = np.full(memberships.shape, np.inf, dtype=np.float64)
    heap: list[tuple[float, int, int, int]] = []

    padded_mask = np.pad(object_mask, 1, mode="constant", constant_values=False)

    boundary_mask = np.zeros_like(object_mask, dtype=bool)
    boundary_cost = np.full(memberships.shape, np.inf, dtype=np.float64)
    for offset, neighbour_distance in zip(NEIGHBOUR_OFFSETS, NEIGHBOUR_DISTANCES, strict=True):
        shifted_mask = _shifted_mask_view(padded_mask, offset)
        touches_exterior = object_mask & ~shifted_mask
        candidate_cost = 0.5 * memberships.astype(np.float64) * neighbour_distance
        boundary_mask |= touches_exterior
        boundary_cost = np.minimum(boundary_cost, np.where(touches_exterior, candidate_cost, np.inf))

    seed_coords = np.argwhere(boundary_mask)
    for z, y, x in seed_coords:
        seed_distance = float(boundary_cost[z, y, x])
        distance[z, y, x] = seed_distance
        heapq.heappush(heap, (seed_distance, int(z), int(y), int(x)))

    return distance, heap


def _compute_fuzzy_fdt(memberships: np.ndarray) -> np.ndarray:
    """Compute fuzzy FDT by explicit weighted-path propagation from the boundary."""
    object_mask = memberships > 0.0
    if not np.any(object_mask):
        return np.zeros_like(memberships, dtype=np.float32)

    distance, heap = _initialize_fuzzy_boundary_distances(memberships)
    shape = memberships.shape
    memberships64 = memberships.astype(np.float64, copy=False)

    while heap:
        current_distance, z, y, x = heapq.heappop(heap)
        if current_distance > distance[z, y, x]:
            continue

        current_membership = memberships64[z, y, x]
        for offset, neighbour_distance in zip(NEIGHBOUR_OFFSETS, NEIGHBOUR_DISTANCES, strict=True):
            nz = z + int(offset[0])
            ny = y + int(offset[1])
            nx = x + int(offset[2])

            if nz < 0 or ny < 0 or nx < 0 or nz >= shape[0] or ny >= shape[1] or nx >= shape[2]:
                continue
            if not object_mask[nz, ny, nx]:
                continue

            edge_cost = 0.5 * (current_membership + memberships64[nz, ny, nx]) * neighbour_distance
            candidate_distance = current_distance + edge_cost
            if candidate_distance + 1e-12 < distance[nz, ny, nx]:
                distance[nz, ny, nx] = candidate_distance
                heapq.heappush(heap, (candidate_distance, nz, ny, nx))

    result = np.zeros_like(memberships, dtype=np.float32)
    result[object_mask] = distance[object_mask].astype(np.float32, copy=False)
    return result


def compute_fdt(volume: np.ndarray) -> np.ndarray:
    """Return the FDT for a 3D binary or fuzzy membership volume."""
    memberships = _coerce_membership_volume(volume)
    if memberships.ndim != 3:
        raise ValueError("compute_fdt expects a 3D volume.")

    if _is_binary_membership(memberships):
        return _compute_binary_fdt(memberships)

    return _compute_fuzzy_fdt(memberships)
