"""Validation helpers for voxel-based skeleton evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np


SUPPORTED_RADIUS_UNITS = {"voxels", "um"}
SPATIAL_UNIT_TO_UM = {
    "meter": 1_000_000.0,
    "mm": 1_000.0,
    "micron": 1.0,
    "um": 1.0,
}


@dataclass(slots=True)
class SkeletonVolumeInput:
    """Validated binary skeleton volume used by the evaluation subsystem."""

    data: np.ndarray
    spacing: tuple[float, float, float]
    spatial_unit: str = "unknown"
    path: str | None = None
    affine: np.ndarray | None = None
    header: Any | None = None


def validate_buffer_radius(radius: float, unit: str) -> None:
    """Validate the buffer radius configuration."""
    if unit not in SUPPORTED_RADIUS_UNITS:
        raise ValueError(
            f"Unsupported buffer radius unit '{unit}'. Expected one of {sorted(SUPPORTED_RADIUS_UNITS)}."
        )
    if not np.isfinite(radius):
        raise ValueError("Buffer radius must be a finite numeric value.")
    if radius < 0:
        raise ValueError("Buffer radius must be greater than or equal to 0.")


def prepare_skeleton_volume(
    data: np.ndarray,
    spacing: tuple[float, float, float],
    *,
    label: str,
    spatial_unit: str = "unknown",
    path: str | None = None,
    affine: np.ndarray | None = None,
    header: Any | None = None,
) -> SkeletonVolumeInput:
    """Validate a raw 3D binary skeleton array and package it for evaluation."""
    array = np.asarray(data)
    if array.ndim != 3:
        raise ValueError(f"{label} must be a 3D volume. Got ndim={array.ndim}.")
    if not _is_binary_array(array):
        unique_values = np.unique(array)
        preview = ", ".join(str(value) for value in unique_values[:10])
        if unique_values.size > 10:
            preview += ", ..."
        raise ValueError(
            f"{label} must contain only binary values {{0, 1}}. Found values: [{preview}]"
        )

    normalized_spacing = _normalize_spacing_tuple(spacing, label=label)
    return SkeletonVolumeInput(
        data=np.asarray(array > 0, dtype=bool),
        spacing=normalized_spacing,
        spatial_unit=spatial_unit or "unknown",
        path=path,
        affine=affine,
        header=header,
    )


def load_skeleton_nifti(path: str | Path, *, label: str) -> SkeletonVolumeInput:
    """Load and validate a raw binary skeleton NIfTI without implicit normalization."""
    volume_path = Path(path)
    if not volume_path.exists():
        raise FileNotFoundError(f"{label} does not exist: {volume_path}")
    if not str(volume_path).endswith((".nii", ".nii.gz")):
        raise ValueError(f"{label} must be a .nii or .nii.gz file. Got: {volume_path}")

    image = nib.load(str(volume_path))
    if not isinstance(image, nib.Nifti1Image):
        image = nib.Nifti1Image.from_image(image)

    header = image.header.copy() if image.header is not None else nib.Nifti1Header()
    spacing = tuple(float(value) for value in header.get_zooms()[:3])
    spatial_unit = header.get_xyzt_units()[0] or "unknown"
    raw_data = np.asarray(image.dataobj)

    return prepare_skeleton_volume(
        raw_data,
        spacing,
        label=label,
        spatial_unit=spatial_unit,
        path=str(volume_path),
        affine=image.affine.copy(),
        header=header,
    )


def validate_matching_inputs(
    pred_volume: SkeletonVolumeInput,
    ref_volume: SkeletonVolumeInput,
    *,
    require_matching_units_for_physical_radius: bool,
) -> None:
    """Ensure prediction and reference inputs can be evaluated together."""
    if pred_volume.data.shape != ref_volume.data.shape:
        raise ValueError(
            "Prediction and reference skeletons must have matching shapes. "
            f"Got pred={pred_volume.data.shape}, ref={ref_volume.data.shape}."
        )

    if not np.allclose(pred_volume.spacing, ref_volume.spacing, rtol=0.0, atol=1e-6):
        raise ValueError(
            "Prediction and reference skeletons must have matching spacing. "
            f"Got pred={pred_volume.spacing}, ref={ref_volume.spacing}."
        )

    if require_matching_units_for_physical_radius and pred_volume.spatial_unit != ref_volume.spatial_unit:
        raise ValueError(
            "Prediction and reference skeletons must use matching spatial units "
            "when --buffer-radius-unit um is requested. "
            f"Got pred='{pred_volume.spatial_unit}', ref='{ref_volume.spatial_unit}'."
        )


def spacing_in_um(spacing: tuple[float, float, float], spatial_unit: str) -> tuple[float, float, float]:
    """Convert spacing values into micrometers."""
    if spatial_unit not in SPATIAL_UNIT_TO_UM:
        raise ValueError(
            "Physical buffer radii in micrometers require convertible NIfTI spatial units. "
            f"Got spatial unit '{spatial_unit}'. Supported units: {sorted(SPATIAL_UNIT_TO_UM)}."
        )
    factor = SPATIAL_UNIT_TO_UM[spatial_unit]
    return tuple(float(value) * factor for value in spacing)


def build_anisotropy_warning(
    spacing: tuple[float, float, float],
    *,
    radius_unit: str,
    spatial_unit: str,
) -> str | None:
    """Return a warning string when anisotropy could affect buffer interpretation."""
    if np.allclose(spacing, spacing[0], rtol=0.0, atol=1e-6):
        return None

    if radius_unit == "voxels":
        return (
            "Input spacing is anisotropic "
            f"{spacing}; voxel-radius buffer dilation will be physically anisotropic. "
            "Double-check the chosen buffer radius and unit."
        )

    return (
        "Input spacing is anisotropic "
        f"{spacing} with spatial unit '{spatial_unit}'; micrometer-radius buffer dilation "
        "uses that spacing to build an anisotropic structuring element. "
        "Double-check the chosen buffer radius and unit."
    )


def _is_binary_array(values: np.ndarray) -> bool:
    unique_values = np.unique(values)
    if unique_values.size == 0:
        return True
    return bool(np.isin(unique_values, (0, 1)).all())


def _normalize_spacing_tuple(
    spacing: tuple[float, float, float] | tuple[float, ...],
    *,
    label: str,
) -> tuple[float, float, float]:
    if len(spacing) != 3:
        raise ValueError(f"{label} spacing must contain exactly three values. Got {spacing}.")

    normalized = tuple(float(value) for value in spacing[:3])
    if any(not np.isfinite(value) or value <= 0 for value in normalized):
        raise ValueError(f"{label} spacing must contain positive finite values. Got {normalized}.")
    return normalized
