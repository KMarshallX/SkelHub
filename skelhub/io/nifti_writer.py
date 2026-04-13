"""NIfTI writer utilities."""

from __future__ import annotations

import os
from os import PathLike

import nibabel as nib
import numpy as np


def _ensure_nifti_extension(output_path: str | PathLike[str]) -> str:
    """Append `.nii.gz` when no NIfTI extension is present."""
    output_path = os.fspath(output_path)
    if output_path.endswith(".nii") or output_path.endswith(".nii.gz"):
        return output_path
    return f"{output_path}.nii.gz"


def write_nifti(
    data: np.ndarray,
    affine: np.ndarray,
    header: nib.Nifti1Header,
    output_path: str | PathLike[str],
) -> str:
    """Write a numpy array to a NIfTI file.

    Parameters
    ----------
    data
        Volume data in `(z, y, x)` index order.
    affine
        4x4 voxel-to-world affine matrix.
    header
        NIfTI header to preserve metadata fields where possible.
    output_path
        Output file path. If no NIfTI extension is given, `.nii.gz` is added.

    Returns
    -------
    str
        Final output path used on disk.
    """
    final_path = _ensure_nifti_extension(output_path)
    os.makedirs(os.path.dirname(os.path.abspath(final_path)), exist_ok=True)

    out_header = header.copy()
    image = nib.Nifti1Image(np.asarray(data), affine=affine, header=out_header)
    nib.save(image, final_path)
    return final_path
