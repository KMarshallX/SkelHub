"""NIfTI reader utilities."""

from __future__ import annotations

from typing import Tuple

import nibabel as nib
import numpy as np


def _is_binary_array(values: np.ndarray) -> bool:
    """Return True when the input values are exactly binary {0, 1}."""
    unique_values = np.unique(values)
    if unique_values.size == 0:
        return True
    return np.array_equal(unique_values, np.array([0])) or np.array_equal(
        unique_values, np.array([0, 1])
    )


def _normalize_to_unit_interval(values: np.ndarray) -> np.ndarray:
    """Normalize values to [0, 1] with safe handling of constant arrays."""
    vmin = float(np.min(values))
    vmax = float(np.max(values))
    if vmax == vmin:
        return np.zeros_like(values, dtype=np.float32)
    normalized = (values - vmin) / (vmax - vmin)
    return normalized.astype(np.float32, copy=False)


def read_nifti(file_path: str) -> Tuple[np.ndarray, np.ndarray, nib.Nifti1Header]:
    """Load a NIfTI file.

    Parameters
    ----------
    file_path
        Path to `.nii` or `.nii.gz` file.

    Returns
    -------
    tuple
        `(data, affine, header)` where `data` is `float32` in [0, 1],
        `affine` is the 4x4 voxel-to-world matrix, and `header` is the
        source NIfTI header.
    """
    image = nib.load(file_path)
    if not isinstance(image, nib.Nifti1Image):
        image = nib.Nifti1Image.from_image(image)
    raw = np.asarray(image.dataobj)

    if np.issubdtype(raw.dtype, np.integer) and _is_binary_array(raw):
        data = raw.astype(np.float32, copy=False)
    else:
        data = raw.astype(np.float32, copy=False)
        if float(np.min(data)) < 0.0 or float(np.max(data)) > 1.0:
            data = _normalize_to_unit_interval(data)
        else:
            data = np.clip(data, 0.0, 1.0).astype(np.float32, copy=False)

    header = image.header.copy() if image.header is not None else nib.Nifti1Header()
    return data, image.affine.copy(), header
