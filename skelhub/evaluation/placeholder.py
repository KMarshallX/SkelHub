"""Minimal framework-level evaluation placeholder."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np

from skelhub.core import EvaluationResult
from skelhub.io import read_nifti


def evaluate_skeleton_file(
    pred_path: str,
    log: Callable[[str], None] | None = None,
) -> EvaluationResult:
    """Validate and load a skeleton NIfTI, then emit a placeholder message."""
    path = Path(pred_path)
    if not path.exists():
        raise FileNotFoundError(f"Skeleton input does not exist: {path}")
    if path.suffix not in {".nii", ".gz"} or not str(path).endswith((".nii", ".nii.gz")):
        raise ValueError("Evaluation input must be a .nii or .nii.gz file.")

    data, _affine, _header = read_nifti(path)
    if data.ndim != 3:
        raise ValueError("Evaluation input must be a 3D NIfTI volume.")

    voxel_count = int(np.count_nonzero(np.asarray(data) > 0))
    message = (
        f"Evaluation placeholder executed successfully for {path.name} "
        f"with {voxel_count} nonzero skeleton voxels."
    )
    if log is not None:
        log(message)
    return EvaluationResult(
        message=message,
        input_path=str(path),
        metadata={"nonzero_voxels": voxel_count, "shape": tuple(int(v) for v in data.shape)},
    )
