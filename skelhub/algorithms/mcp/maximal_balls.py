"""Fuzzy center of maximal ball module."""

from __future__ import annotations

import itertools

import numpy as np


def _build_neighbour_data() -> tuple[np.ndarray, np.ndarray]:
    """Precompute 26-neighbour offsets and Euclidean distances."""
    offsets = np.array(
        [offset for offset in itertools.product((-1, 0, 1), repeat=3) if offset != (0, 0, 0)],
        dtype=np.int8,
    )
    distances = np.linalg.norm(offsets, axis=1).astype(np.float32)
    return offsets, distances


NEIGHBOUR_OFFSETS, NEIGHBOUR_DISTANCES = _build_neighbour_data()


def _shifted_view(padded: np.ndarray, offset: np.ndarray) -> np.ndarray:
    """Return the unpadded view shifted by the given offset."""
    z0 = 1 + int(offset[0])
    y0 = 1 + int(offset[1])
    x0 = 1 + int(offset[2])
    return padded[z0 : z0 + padded.shape[0] - 2, y0 : y0 + padded.shape[1] - 2, x0 : x0 + padded.shape[2] - 2]


def compute_fcmb_mask(volume: np.ndarray, fdt: np.ndarray) -> np.ndarray:
    """Return a boolean mask of fuzzy centers of maximal balls."""
    memberships = np.clip(np.asarray(volume, dtype=np.float32), 0.0, 1.0)
    distances = np.asarray(fdt, dtype=np.float32)

    if memberships.ndim != 3 or distances.ndim != 3:
        raise ValueError("compute_fcmb_mask expects 3D inputs.")
    if memberships.shape != distances.shape:
        raise ValueError("volume and fdt must have the same shape.")

    object_mask = memberships > 0.0
    fcmb_mask = object_mask.copy()

    padded_memberships = np.pad(memberships, 1, mode="constant", constant_values=0.0)
    padded_distances = np.pad(distances, 1, mode="constant", constant_values=0.0)

    for offset, neighbour_distance in zip(NEIGHBOUR_OFFSETS, NEIGHBOUR_DISTANCES, strict=True):
        neighbour_memberships = _shifted_view(padded_memberships, offset)
        neighbour_distances = _shifted_view(padded_distances, offset)

        threshold = 0.5 * (memberships + neighbour_memberships) * neighbour_distance
        fcmb_mask &= (neighbour_distances - distances) < threshold

    return fcmb_mask
