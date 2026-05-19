"""Python-native flux-driven medial curve extraction.

This module follows the VMTK/EvoLib medial-curve filter behavior at the
algorithm level without copying VMTK source code: signed-distance driven
average outward flux is combined with topology-preserving thinning.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from itertools import count, product
from typing import Callable

import numpy as np
from scipy import ndimage as ndi

from .config import FluxConfig


NEIGHBOR_OFFSETS_26 = tuple(
    offset for offset in product((-1, 0, 1), repeat=3) if offset != (0, 0, 0)
)
NEIGHBOR_OFFSETS_6 = tuple(
    offset for offset in NEIGHBOR_OFFSETS_26 if sum(abs(value) for value in offset) == 1
)
NEIGHBOR_OFFSETS_18_WITH_CENTER = tuple(
    offset for offset in product((-1, 0, 1), repeat=3) if sum(abs(value) for value in offset) <= 2
)


@dataclass(slots=True)
class FluxRunStats:
    """Internal statistics recorded by the flux medial-curve routine."""

    input_foreground_voxels: int
    output_foreground_voxels: int
    queued_initial_voxels: int
    deleted_voxels: int
    preserved_endpoint_voxels: int
    aof_min: float
    aof_max: float
    sigma_voxels: tuple[float, float, float]


def extract_medial_curve(
    binary: np.ndarray,
    config: FluxConfig,
    *,
    spacing: tuple[float, float, float] | None = None,
    log: Callable[[str], None] | None = None,
) -> tuple[np.ndarray, FluxRunStats]:
    """Extract a binary medial curve from a validated 3D binary object."""
    binary = np.asarray(binary, dtype=bool)
    normalized_spacing = _normalize_spacing(spacing)
    distance = signed_distance(binary, normalized_spacing)
    sigma_voxels = _sigma_to_voxels(config.sigma, config.sigma_unit, normalized_spacing)

    if log:
        log("Computing signed distance, smoothed gradient, and average outward flux...")
    aof = average_outward_flux(distance, sigma_voxels, normalized_spacing)

    if log:
        log("Running topology-preserving flux-guided thinning...")
    skeleton, thinning_stats = thin_by_flux(binary, distance, aof, config.threshold)

    foreground_aof = aof[binary]
    stats = FluxRunStats(
        input_foreground_voxels=int(np.count_nonzero(binary)),
        output_foreground_voxels=int(np.count_nonzero(skeleton)),
        queued_initial_voxels=thinning_stats["queued_initial_voxels"],
        deleted_voxels=thinning_stats["deleted_voxels"],
        preserved_endpoint_voxels=thinning_stats["preserved_endpoint_voxels"],
        aof_min=float(np.min(foreground_aof)) if foreground_aof.size else 0.0,
        aof_max=float(np.max(foreground_aof)) if foreground_aof.size else 0.0,
        sigma_voxels=tuple(float(value) for value in sigma_voxels),
    )
    return skeleton.astype(np.uint8, copy=False), stats


def signed_distance(binary: np.ndarray, spacing: tuple[float, float, float]) -> np.ndarray:
    """Build a signed distance image with foreground at non-positive values."""
    inside_distance = ndi.distance_transform_edt(binary, sampling=spacing)
    outside_distance = ndi.distance_transform_edt(~binary, sampling=spacing)
    distance = outside_distance.astype(np.float64, copy=False)
    distance[binary] = -inside_distance[binary]
    return distance


def average_outward_flux(
    distance: np.ndarray,
    sigma_voxels: tuple[float, float, float],
    spacing: tuple[float, float, float],
) -> np.ndarray:
    """Compute 26-neighborhood average outward flux from signed-distance gradient."""
    if any(value > 0.0 for value in sigma_voxels):
        smoothed = ndi.gaussian_filter(distance, sigma=sigma_voxels, mode="nearest")
    else:
        smoothed = distance

    gradients = np.stack(np.gradient(smoothed, *spacing, edge_order=1), axis=0)
    padded = np.pad(gradients, ((0, 0), (1, 1), (1, 1), (1, 1)), mode="constant")
    aof = np.zeros(distance.shape, dtype=np.float64)

    for offset in NEIGHBOR_OFFSETS_26:
        normal = np.asarray(offset, dtype=np.float64)
        normal /= np.linalg.norm(normal)
        slices = tuple(slice(1 + offset[axis], 1 + offset[axis] + distance.shape[axis]) for axis in range(3))
        neighbor_gradient = padded[(slice(None),) + slices]
        aof -= np.tensordot(normal, neighbor_gradient, axes=(0, 0))

    aof[distance > 0.0] = 0.0
    return aof


def thin_by_flux(
    binary: np.ndarray,
    distance: np.ndarray,
    aof: np.ndarray,
    threshold: float,
) -> tuple[np.ndarray, dict[str, int]]:
    """Run priority thinning guided by distance depth and AOF endpoint retention."""
    skeleton = binary.astype(np.uint8, copy=True)
    queued = np.zeros_like(skeleton, dtype=bool)
    heap: list[tuple[float, int, tuple[int, int, int]]] = []
    sequence = count()

    for index_array in np.argwhere(skeleton):
        index = tuple(int(value) for value in index_array)
        if _is_boundary(skeleton, index) and _is_int_simple(skeleton, index) and _is_ext_simple(skeleton, index):
            heapq.heappush(heap, (-float(distance[index]), next(sequence), index))
            queued[index] = True

    queued_initial = len(heap)
    deleted = 0
    preserved_endpoints = 0

    while heap:
        _, _, index = heapq.heappop(heap)
        queued[index] = False
        if skeleton[index] == 0:
            continue

        if _is_int_simple(skeleton, index) and _is_ext_simple(skeleton, index):
            if aof[index] < threshold and _is_end(skeleton, index):
                preserved_endpoints += 1
                continue

            skeleton[index] = 0
            deleted += 1

            for neighbor in _valid_neighbors(index, skeleton.shape, NEIGHBOR_OFFSETS_26):
                if skeleton[neighbor] == 1 and not queued[neighbor]:
                    if _is_int_simple(skeleton, neighbor) and _is_ext_simple(skeleton, neighbor):
                        heapq.heappush(heap, (-float(distance[neighbor]), next(sequence), neighbor))
                        queued[neighbor] = True

    return skeleton, {
        "queued_initial_voxels": int(queued_initial),
        "deleted_voxels": int(deleted),
        "preserved_endpoint_voxels": int(preserved_endpoints),
    }


def _normalize_spacing(spacing: tuple[float, float, float] | None) -> tuple[float, float, float]:
    if spacing is None:
        return (1.0, 1.0, 1.0)
    normalized = tuple(float(value) for value in spacing)
    if len(normalized) != 3 or any(value <= 0.0 for value in normalized):
        return (1.0, 1.0, 1.0)
    return normalized


def _sigma_to_voxels(
    sigma: float,
    sigma_unit: str,
    spacing: tuple[float, float, float],
) -> tuple[float, float, float]:
    if sigma_unit == "voxels":
        return (float(sigma), float(sigma), float(sigma))
    return tuple(float(sigma) / axis_spacing for axis_spacing in spacing)


def _valid_neighbors(
    index: tuple[int, int, int],
    shape: tuple[int, int, int],
    offsets: tuple[tuple[int, int, int], ...],
) -> list[tuple[int, int, int]]:
    neighbors: list[tuple[int, int, int]] = []
    for offset in offsets:
        neighbor = tuple(index[axis] + offset[axis] for axis in range(3))
        if all(0 <= neighbor[axis] < shape[axis] for axis in range(3)):
            neighbors.append(neighbor)
    return neighbors


def _patch(skeleton: np.ndarray, index: tuple[int, int, int]) -> np.ndarray:
    patch = np.zeros((3, 3, 3), dtype=skeleton.dtype)
    source_slices = []
    target_slices = []
    for axis, center in enumerate(index):
        source_start = max(center - 1, 0)
        source_stop = min(center + 2, skeleton.shape[axis])
        target_start = source_start - (center - 1)
        target_stop = target_start + (source_stop - source_start)
        source_slices.append(slice(source_start, source_stop))
        target_slices.append(slice(target_start, target_stop))

    patch[tuple(target_slices)] = skeleton[tuple(source_slices)]
    return patch


def _is_boundary(skeleton: np.ndarray, index: tuple[int, int, int]) -> bool:
    if skeleton[index] == 0:
        return False
    return bool(np.any(_patch(skeleton, index) == 0))


def _is_end(skeleton: np.ndarray, index: tuple[int, int, int]) -> bool:
    patch = _patch(skeleton, index)
    return int(np.count_nonzero(patch)) - int(skeleton[index]) < 2


def _is_int_simple(skeleton: np.ndarray, index: tuple[int, int, int]) -> bool:
    patch = _patch(skeleton, index).astype(bool, copy=False)
    foreground_count = int(np.count_nonzero(patch))
    if foreground_count == 1 or foreground_count == 27:
        return False

    patch[1, 1, 1] = False
    connected = _component_size(patch, NEIGHBOR_OFFSETS_26)
    return connected == foreground_count - 1


def _is_ext_simple(skeleton: np.ndarray, index: tuple[int, int, int]) -> bool:
    patch = _patch(skeleton, index).astype(bool, copy=False)
    patch[1, 1, 1] = False

    background = np.zeros((3, 3, 3), dtype=bool)
    for offset in NEIGHBOR_OFFSETS_18_WITH_CENTER:
        local = tuple(offset[axis] + 1 for axis in range(3))
        background[local] = not patch[local]

    background_count = int(np.count_nonzero(background))
    if background_count <= 1 or background_count == len(NEIGHBOR_OFFSETS_18_WITH_CENTER):
        return False

    connected = _component_size(background, NEIGHBOR_OFFSETS_6)
    return connected == background_count


def _component_size(mask: np.ndarray, offsets: tuple[tuple[int, int, int], ...]) -> int:
    seeds = np.argwhere(mask)
    if seeds.size == 0:
        return 0

    start = tuple(int(value) for value in seeds[0])
    seen = {start}
    stack = [start]

    while stack:
        current = stack.pop()
        for offset in offsets:
            neighbor = tuple(current[axis] + offset[axis] for axis in range(3))
            if all(0 <= neighbor[axis] < 3 for axis in range(3)):
                if mask[neighbor] and neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)

    return len(seen)
