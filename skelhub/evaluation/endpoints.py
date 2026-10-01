"""Endpoint-count diagnostics for binary 3D skeletons."""

from __future__ import annotations

import numpy as np
from scipy import ndimage

from .topology import padded_foreground_crop


_NEIGHBOUR_KERNEL = np.ones((3, 3, 3), dtype=np.int16)
_NEIGHBOUR_KERNEL[1, 1, 1] = 0


def count_endpoints(volume: np.ndarray) -> int:
    """Count foreground voxels with exactly one 26-neighbour (the centre voxel excluded)."""
    skeleton = padded_foreground_crop(volume)
    neighbour_count = ndimage.convolve(skeleton.astype(np.int16), _NEIGHBOUR_KERNEL, mode="constant", cval=0)
    return int(np.count_nonzero(skeleton & (neighbour_count == 1)))
