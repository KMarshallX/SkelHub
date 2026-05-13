"""Rasterization helpers for L1 contracted sample points."""

from __future__ import annotations

import numpy as np


def rasterize_l1_points(points: np.ndarray, shape: tuple[int, int, int]) -> np.ndarray:
    """Rasterize contracted L1 sample points into a binary skeleton volume."""
    skeleton = np.zeros(shape, dtype=np.uint8)
    if len(points) == 0:
        return skeleton

    rounded_points = np.rint(points).astype(int)
    for node in rounded_points:
        if np.all(node >= 0) and np.all(node < np.asarray(shape)):
            skeleton[tuple(node)] = 1
    return skeleton
