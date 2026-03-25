"""Root voxel detection helpers for a single object."""

from __future__ import annotations

import numpy as np

from core.maximal_balls import compute_fcmb_mask


def max_fdt(object_mask: np.ndarray, fdt: np.ndarray) -> tuple[int, int, int]:
    """Return the object voxel with the highest FDT value."""
    support = np.asarray(object_mask, dtype=bool)
    distances = np.asarray(fdt, dtype=np.float32)

    if support.ndim != 3 or distances.ndim != 3:
        raise ValueError("max_fdt expects 3D inputs.")
    if support.shape != distances.shape:
        raise ValueError("object_mask and fdt must have the same shape.")
    coords = np.argwhere(support)
    if coords.size == 0:
        raise ValueError("max_fdt requires a non-empty object mask.")

    values = distances[support]
    best_index = int(np.argmax(values))
    return tuple(int(value) for value in coords[best_index])


def topmost(volume: np.ndarray, object_mask: np.ndarray, fdt: np.ndarray) -> tuple[int, int, int]:
    """Return the topmost fCMB voxel with maximal FDT within that slice."""
    memberships = np.asarray(volume, dtype=np.float32)
    support = np.asarray(object_mask, dtype=bool)
    distances = np.asarray(fdt, dtype=np.float32)

    if memberships.ndim != 3 or support.ndim != 3 or distances.ndim != 3:
        raise ValueError("topmost expects 3D inputs.")
    if memberships.shape != support.shape or support.shape != distances.shape:
        raise ValueError("volume, object_mask, and fdt must have the same shape.")
    if not np.any(support):
        raise ValueError("topmost requires a non-empty object mask.")

    fcmb_mask = compute_fcmb_mask(memberships, distances) & support
    if not np.any(fcmb_mask):
        return max_fdt(support, distances)

    top_z = int(np.min(np.argwhere(fcmb_mask)[:, 0]))
    slice_mask = fcmb_mask.copy()
    slice_mask[np.arange(slice_mask.shape[0]) != top_z, :, :] = False
    coords = np.argwhere(slice_mask)
    values = distances[slice_mask]
    best_index = int(np.argmax(values))
    return tuple(int(value) for value in coords[best_index])


def detect_root(
    volume: np.ndarray,
    object_mask: np.ndarray,
    fdt: np.ndarray,
    method: str = "max_fdt",
) -> tuple[int, int, int]:
    """Select the root voxel for one object."""
    if method == "max_fdt":
        return max_fdt(object_mask, fdt)
    if method == "topmost":
        return topmost(volume, object_mask, fdt)
    raise ValueError(f"Unsupported root detection method: {method}")
