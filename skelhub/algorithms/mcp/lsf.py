"""Local significance factor module."""

from __future__ import annotations

import numpy as np

from .maximal_balls import NEIGHBOUR_DISTANCES, NEIGHBOUR_OFFSETS, compute_fcmb_mask


def _shifted_view(padded: np.ndarray, offset: np.ndarray) -> np.ndarray:
    """Return the unpadded view shifted by the given offset."""
    z0 = 1 + int(offset[0])
    y0 = 1 + int(offset[1])
    x0 = 1 + int(offset[2])
    return padded[z0 : z0 + padded.shape[0] - 2, y0 : y0 + padded.shape[1] - 2, x0 : x0 + padded.shape[2] - 2]


def compute_lsf(volume: np.ndarray, fdt: np.ndarray) -> np.ndarray:
    """Return the local significance factor with zeros outside the fCMB set."""
    memberships = np.clip(np.asarray(volume, dtype=np.float32), 0.0, 1.0)
    distances = np.asarray(fdt, dtype=np.float32)

    if memberships.ndim != 3 or distances.ndim != 3:
        raise ValueError("compute_lsf expects 3D inputs.")
    if memberships.shape != distances.shape:
        raise ValueError("volume and fdt must have the same shape.")

    object_mask = memberships > 0.0
    if not np.any(object_mask):
        return np.zeros_like(memberships, dtype=np.float32)

    fcmb_mask = compute_fcmb_mask(memberships, distances)
    padded_memberships = np.pad(memberships, 1, mode="constant", constant_values=0.0)
    padded_distances = np.pad(distances, 1, mode="constant", constant_values=0.0)

    max_ratio = np.full(memberships.shape, -np.inf, dtype=np.float32)
    for offset, neighbour_distance in zip(NEIGHBOUR_OFFSETS, NEIGHBOUR_DISTANCES, strict=True):
        neighbour_memberships = _shifted_view(padded_memberships, offset)
        neighbour_distances = _shifted_view(padded_distances, offset)

        denominator = 0.5 * (memberships + neighbour_memberships) * neighbour_distance
        ratio = np.full(memberships.shape, -np.inf, dtype=np.float32)
        valid = denominator > 0.0
        ratio[valid] = (neighbour_distances[valid] - distances[valid]) / denominator[valid]
        max_ratio = np.maximum(max_ratio, ratio)

    positive_part = np.maximum(max_ratio, 0.0)
    lsf = np.zeros_like(memberships, dtype=np.float32)
    lsf[fcmb_mask] = 1.0 - positive_part[fcmb_mask]
    lsf[fcmb_mask] = np.clip(lsf[fcmb_mask], 0.0, 1.0)
    lsf[~object_mask] = 0.0
    return lsf
