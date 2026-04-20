"""Geometry-preservation helpers for voxel-based skeleton evaluation."""

from __future__ import annotations

import numpy as np
from scipy import ndimage

from .validation import spacing_in_um


def build_buffer_structuring_element(
    *,
    radius: float,
    radius_unit: str,
    spacing: tuple[float, float, float],
    spatial_unit: str,
) -> tuple[np.ndarray, tuple[float, float, float], str]:
    """Build the dilation structuring element used by the buffer method."""
    if radius_unit == "voxels":
        structure = _build_voxel_ball(radius)
        return structure, (float(radius), float(radius), float(radius)), "voxel_distance"

    spacing_um = spacing_in_um(spacing, spatial_unit)
    voxel_radii = tuple(float(radius) / axis_spacing for axis_spacing in spacing_um)
    structure = _build_physical_ball(radius, spacing_um)
    return structure, voxel_radii, "physical_um"


def dilate_skeleton(volume: np.ndarray, structure: np.ndarray) -> np.ndarray:
    """Dilate a binary skeleton with the precomputed structuring element."""
    return ndimage.binary_dilation(np.asarray(volume, dtype=bool), structure=structure)


def count_geometry_terms(
    pred_skeleton: np.ndarray,
    ref_skeleton: np.ndarray,
    ref_buffer: np.ndarray,
    pred_buffer: np.ndarray,
) -> tuple[int, int, int]:
    """Compute TP, FP, and FN under the v1 buffer-method convention."""
    pred = np.asarray(pred_skeleton, dtype=bool)
    ref = np.asarray(ref_skeleton, dtype=bool)

    tp = int(np.count_nonzero(pred & ref_buffer))
    fp = int(np.count_nonzero(pred & ~ref_buffer))
    fn = int(np.count_nonzero(ref & ~pred_buffer))
    return tp, fp, fn


def compute_geometry_scores(
    *,
    tp: int,
    fp: int,
    fn: int,
    pred_voxels: int,
    ref_voxels: int,
    warnings: list[str],
) -> tuple[float, float]:
    """Compute completeness and correctness with explicit zero-denominator handling."""
    cp = _safe_quality_ratio(
        numerator=tp,
        denominator=tp + fn,
        metric_name="Cp",
        pred_voxels=pred_voxels,
        ref_voxels=ref_voxels,
        warnings=warnings,
    )
    cr = _safe_quality_ratio(
        numerator=tp,
        denominator=tp + fp,
        metric_name="Cr",
        pred_voxels=pred_voxels,
        ref_voxels=ref_voxels,
        warnings=warnings,
    )
    return cp, cr


def _safe_quality_ratio(
    *,
    numerator: int,
    denominator: int,
    metric_name: str,
    pred_voxels: int,
    ref_voxels: int,
    warnings: list[str],
) -> float:
    if denominator > 0:
        return float(numerator) / float(denominator)

    if pred_voxels == 0 and ref_voxels == 0:
        warnings.append(
            f"{metric_name} denominator was zero because both skeletons are empty; "
            f"{metric_name} was set to 1.0."
        )
        return 1.0

    warnings.append(
        f"{metric_name} denominator was zero; {metric_name} was set to 0.0 "
        "because only one skeleton is empty."
    )
    return 0.0


def _build_voxel_ball(radius_voxels: float) -> np.ndarray:
    extent = int(np.ceil(radius_voxels))
    coords = np.indices((2 * extent + 1, 2 * extent + 1, 2 * extent + 1), dtype=np.float32)
    center = float(extent)
    squared_distance = (
        (coords[0] - center) ** 2 + (coords[1] - center) ** 2 + (coords[2] - center) ** 2
    )
    return squared_distance <= (float(radius_voxels) ** 2 + 1e-8)


def _build_physical_ball(
    radius_um: float,
    spacing_um: tuple[float, float, float],
) -> np.ndarray:
    voxel_radii = [int(np.ceil(float(radius_um) / axis_spacing)) for axis_spacing in spacing_um]
    shape = tuple(2 * radius + 1 for radius in voxel_radii)
    coords = np.indices(shape, dtype=np.float32)
    squared_distance = np.zeros(shape, dtype=np.float32)

    for axis, radius in enumerate(voxel_radii):
        centered = (coords[axis] - float(radius)) * float(spacing_um[axis])
        squared_distance += centered**2

    return squared_distance <= (float(radius_um) ** 2 + 1e-8)
