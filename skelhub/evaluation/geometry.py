"""Geometry metrics: directional voxel-centre distances, tolerance coverage and displacement.

All inputs are boolean arrays on one orthogonal grid with per-axis spacing in
micrometres; validation lives in ``validation.py``.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
from scipy import ndimage

from skelhub.core import DistanceSummary, ToleranceMatch

from .validation import RELATIVE_TOLERANCE, ToleranceSpec


PERCENTILE = 95.0
PERCENTILE_METHOD = "linear"


def directional_distances(
    pred: np.ndarray,
    ref: np.ndarray,
    spacing_um: tuple[float, float, float],
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(D_pred_to_ref, D_ref_to_pred)`` in micrometres.

    Each value is the exact Euclidean distance from one foreground voxel centre
    to the nearest foreground voxel centre of the other skeleton. Both inputs
    must be nonempty. The EDTs run on the bounding box of both skeletons, which
    holds every nearest neighbour, so cropping does not change any distance.
    """
    if not pred.any() or not ref.any():
        raise ValueError("directional_distances needs two nonempty skeletons.")
    crop = _union_bounding_box(pred, ref)
    pred_crop = pred[crop]
    ref_crop = ref[crop]
    to_ref = ndimage.distance_transform_edt(~ref_crop, sampling=spacing_um)
    pred_to_ref = to_ref[pred_crop]
    del to_ref
    to_pred = ndimage.distance_transform_edt(~pred_crop, sampling=spacing_um)
    ref_to_pred = to_pred[ref_crop]
    return np.asarray(pred_to_ref, dtype=float), np.asarray(ref_to_pred, dtype=float)


def within_tolerance(distances: np.ndarray, tolerance_um: float, spacing_um: Sequence[float]) -> np.ndarray:
    """Boolean mask of ``d <= tau``, with a tiny relative slack for float32 header rounding."""
    slack = RELATIVE_TOLERANCE * max(float(tolerance_um), float(min(spacing_um)))
    return distances <= float(tolerance_um) + slack


def coverage_at_tolerance(
    spec: ToleranceSpec,
    pred_to_ref: np.ndarray,
    ref_to_pred: np.ndarray,
    spacing_um: Sequence[float],
) -> ToleranceMatch:
    """Precision, recall and F1 at one tolerance for two nonempty skeletons."""
    matched_pred = int(np.count_nonzero(within_tolerance(pred_to_ref, spec.tolerance_um, spacing_um)))
    matched_ref = int(np.count_nonzero(within_tolerance(ref_to_pred, spec.tolerance_um, spacing_um)))
    precision = matched_pred / pred_to_ref.size
    recall = matched_ref / ref_to_pred.size
    return _tolerance_match(
        spec,
        precision=precision,
        recall=recall,
        matched_pred=matched_pred,
        unmatched_pred=int(pred_to_ref.size) - matched_pred,
        matched_ref=matched_ref,
        unmatched_ref=int(ref_to_pred.size) - matched_ref,
    )


def empty_prediction_coverage(spec: ToleranceSpec, ref_voxels: int) -> ToleranceMatch:
    """Zero coverage for an empty prediction against a nonempty reference."""
    return _tolerance_match(
        spec,
        precision=0.0,
        recall=0.0,
        matched_pred=0,
        unmatched_pred=0,
        matched_ref=0,
        unmatched_ref=int(ref_voxels),
    )


def unavailable_coverage(spec: ToleranceSpec) -> ToleranceMatch:
    """Coverage entry with every score left as ``None``."""
    return ToleranceMatch(
        tolerance_um=spec.tolerance_um,
        requested_value=spec.requested_value,
        requested_unit=spec.requested_unit,
        is_primary=spec.is_primary,
    )


def summarize_distances(pred_to_ref: np.ndarray, ref_to_pred: np.ndarray) -> DistanceSummary:
    """Directional means, the symmetric mean and P95, and Hausdorff distance.

    The symmetric values weight each direction equally; the two distance
    collections are never pooled.
    """
    mean_pr = float(np.mean(pred_to_ref))
    mean_rp = float(np.mean(ref_to_pred))
    p95_pr = float(np.percentile(pred_to_ref, PERCENTILE, method=PERCENTILE_METHOD))
    p95_rp = float(np.percentile(ref_to_pred, PERCENTILE, method=PERCENTILE_METHOD))
    max_pr = float(np.max(pred_to_ref))
    max_rp = float(np.max(ref_to_pred))
    return DistanceSummary(
        mean_pred_to_ref_um=mean_pr,
        mean_ref_to_pred_um=mean_rp,
        symmetric_mean_um=(mean_pr + mean_rp) / 2.0,
        p95_pred_to_ref_um=p95_pr,
        p95_ref_to_pred_um=p95_rp,
        symmetric_p95_um=max(p95_pr, p95_rp),
        max_pred_to_ref_um=max_pr,
        max_ref_to_pred_um=max_rp,
        hausdorff_um=max(max_pr, max_rp),
    )


def _tolerance_match(
    spec: ToleranceSpec,
    *,
    precision: float,
    recall: float,
    matched_pred: int,
    unmatched_pred: int,
    matched_ref: int,
    unmatched_ref: int,
) -> ToleranceMatch:
    denominator = precision + recall
    f1 = 0.0 if denominator == 0 else 2.0 * precision * recall / denominator
    return ToleranceMatch(
        tolerance_um=spec.tolerance_um,
        requested_value=spec.requested_value,
        requested_unit=spec.requested_unit,
        is_primary=spec.is_primary,
        precision=float(precision),
        recall=float(recall),
        f1=float(f1),
        matched_prediction_voxels=matched_pred,
        unmatched_prediction_voxels=unmatched_pred,
        matched_reference_voxels=matched_ref,
        unmatched_reference_voxels=unmatched_ref,
    )


def _union_bounding_box(first: np.ndarray, second: np.ndarray) -> tuple[slice, ...]:
    union = first | second
    slices = []
    for axis in range(union.ndim):
        other_axes = tuple(index for index in range(union.ndim) if index != axis)
        occupied = np.flatnonzero(union.any(axis=other_axes))
        slices.append(slice(int(occupied[0]), int(occupied[-1]) + 1))
    return tuple(slices)
