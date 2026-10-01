"""Voxel topology: Betti numbers under foreground-26 / background-6 connectivity."""

from __future__ import annotations

import numpy as np
from scipy import ndimage
from skimage.measure import euler_number

from skelhub.core import BettiNumbers


FOREGROUND_CONNECTIVITY = 26
BACKGROUND_CONNECTIVITY = 6

_FOREGROUND_STRUCTURE = ndimage.generate_binary_structure(rank=3, connectivity=3)
_BACKGROUND_STRUCTURE = ndimage.generate_binary_structure(rank=3, connectivity=1)


def padded_foreground_crop(volume: np.ndarray) -> np.ndarray:
    """Foreground bounding box padded with one background layer on every side.

    Topology and 26-neighbour counts are unchanged by this crop: everything
    outside the box is background that joins the single exterior component.
    """
    skeleton = np.asarray(volume, dtype=bool)
    if not skeleton.any():
        return np.zeros((3, 3, 3), dtype=bool)
    occupied = np.argwhere(skeleton)
    low = occupied.min(axis=0)
    high = occupied.max(axis=0) + 1
    crop = skeleton[tuple(slice(int(a), int(b)) for a, b in zip(low, high))]
    return np.pad(crop, 1, mode="constant", constant_values=False)


def compute_betti_numbers(volume: np.ndarray) -> BettiNumbers:
    """Return ``(beta_0, beta_1, beta_2, chi)`` of a binary 3D skeleton.

    - beta_0: 26-connected foreground components.
    - beta_2: 6-connected background components minus the one exterior component.
    - chi: 3D Euler characteristic with matching connectivity (scikit-image, connectivity=3).
    - beta_1 = beta_0 + beta_2 - chi (independent cycles).
    """
    padded = padded_foreground_crop(volume)
    _, beta_0 = ndimage.label(padded, structure=_FOREGROUND_STRUCTURE)
    _, background_components = ndimage.label(~padded, structure=_BACKGROUND_STRUCTURE)
    beta_2 = int(background_components) - 1
    chi = int(euler_number(padded, connectivity=3))
    beta_1 = int(beta_0) + beta_2 - chi
    if beta_2 < 0 or beta_1 < 0:
        raise RuntimeError(
            f"Invalid Betti numbers (beta_0={beta_0}, beta_1={beta_1}, beta_2={beta_2}, chi={chi}); "
            "the foreground/background connectivity conventions are inconsistent."
        )
    return BettiNumbers(beta_0=int(beta_0), beta_1=beta_1, beta_2=beta_2, euler_characteristic=chi)
