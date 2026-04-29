"""Voreen-compatible skeleton voxel classification."""

from __future__ import annotations

import numpy as np
from scipy import ndimage


BACKGROUND = np.uint8(0)
END = np.uint8(1)
REGULAR = np.uint8(2)
BRANCH = np.uint8(3)


def classify_skeleton_voxels(skeleton: np.ndarray) -> np.ndarray:
    """Classify skeleton voxels using Voreen's 26-neighbor count rule.

    Classes match ``SkeletonClassReader::getClass``:
    background -> 0, end -> 1, regular -> 2, branch -> 3.
    """
    if skeleton.ndim != 3:
        raise ValueError("Graph generation expects a 3D skeleton volume.")

    foreground = np.asarray(skeleton > 0, dtype=np.uint8)
    if not np.any(foreground):
        raise ValueError("Input skeleton volume does not contain foreground voxels.")

    kernel = np.ones((3, 3, 3), dtype=np.uint8)
    neighbor_count = ndimage.convolve(
        foreground,
        kernel,
        mode="constant",
        cval=0,
    ).astype(np.int16)
    neighbor_count -= foreground.astype(np.int16)

    classes = np.zeros(foreground.shape, dtype=np.uint8)
    classes[foreground.astype(bool)] = np.clip(
        neighbor_count[foreground.astype(bool)],
        1,
        3,
    ).astype(np.uint8)
    return classes
