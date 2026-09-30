"""NIfTI reader utilities."""

from __future__ import annotations

from dataclasses import dataclass
from os import PathLike
from pathlib import Path
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


@dataclass(slots=True)
class BinaryMaskVolume:
    """A validated binary 3D NIfTI mask and its spatial metadata."""

    mask: np.ndarray
    affine: np.ndarray
    spatial_unit: str
    source_path: str

    @property
    def shape(self) -> tuple[int, int, int]:
        """Volume shape in voxel-index order."""
        return tuple(int(size) for size in self.mask.shape)  # type: ignore[return-value]


def _value_preview(values: np.ndarray, limit: int = 10) -> str:
    preview = ", ".join(str(value) for value in values[:limit])
    return preview + (", ..." if values.size > limit else "")


def read_binary_mask(file_path: str | PathLike[str], *, label: str = "NIfTI") -> BinaryMaskVolume:
    """Load a 3D NIfTI whose voxel values are exactly 0 or 1.

    This follows the viewer's binary-input contract: values must be finite and
    in {0, 1}; anything else is rejected rather than thresholded. The spatial
    unit is read from the header (``"unknown"`` when unset).
    """
    path = Path(file_path)
    if not path.is_file():
        raise ValueError(f"{label} input does not exist: {path}")
    if not (path.name.lower().endswith(".nii") or path.name.lower().endswith(".nii.gz")):
        raise ValueError(f"{label} input must be a .nii or .nii.gz file: {path}")
    try:
        image = nib.load(str(path))
        if not isinstance(image, nib.Nifti1Image):
            image = nib.Nifti1Image.from_image(image)
        data = np.asanyarray(image.dataobj)
    except Exception as exc:  # nibabel raises several concrete types
        raise ValueError(f"Unable to read {label} NIfTI '{path}': {exc}") from exc
    if data.ndim != 3:
        raise ValueError(f"{label} must be a 3D volume; got {data.ndim}D with shape {data.shape}.")
    if data.size == 0:
        raise ValueError(f"{label} volume has no voxels (shape {data.shape}).")
    if np.issubdtype(data.dtype, np.floating) and not np.isfinite(data).all():
        raise ValueError(f"{label} contains non-finite voxel values (NaN or infinity).")
    unique_values = np.unique(data)
    if not np.isin(unique_values, (0, 1)).all():
        raise ValueError(
            f"{label} must be binary with values {{0, 1}}; found [{_value_preview(unique_values)}]."
        )
    affine = np.asarray(image.affine, dtype=float)
    if affine.shape != (4, 4) or not np.isfinite(affine).all():
        raise ValueError(f"{label} affine must be a finite 4x4 matrix.")
    spatial_unit, _time_unit = image.header.get_xyzt_units()
    return BinaryMaskVolume(
        mask=data != 0,
        affine=affine,
        spatial_unit=spatial_unit or "unknown",
        source_path=str(path),
    )
