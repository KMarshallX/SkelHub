"""Foreground EDT-sum agreement: one shared foreground EDT sampled at both skeletons.

The inputs are boolean arrays on one validated orthogonal grid with per-axis
spacing in micrometres; validation lives in ``validation.py``. Nothing here
pads, crops, resamples or alters the inputs.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
from scipy import ndimage

from skelhub.core import ForegroundEdtAgreement, ForegroundEdtSummary, ForegroundMaskInfo


FOREGROUND_EDT_DEFINITION = "skelhub-foreground-edt-sum-v1"
FOREGROUND_EDT_DISTANCE = (
    "Euclidean distance from a foreground voxel centre to the nearest background voxel centre "
    "observed inside the image, um; 0 at background voxels"
)
BOUNDARY_POLICY = (
    "full-image EDT on the supplied mask; only background observed inside the image is used; "
    "no padding and no crop"
)


def compute_foreground_edt_agreement(
    foreground: np.ndarray,
    pred: np.ndarray,
    ref: np.ndarray,
    spacing_um: Sequence[float],
    *,
    path: str | None,
    header_spatial_unit: str | None,
    effective_spatial_unit: str,
    spatial_unit_source: str,
) -> ForegroundEdtAgreement:
    """Sum and summarize one foreground EDT at every prediction and reference skeleton voxel.

    One ``distance_transform_edt`` runs on the full mask with physical spacing.
    Skeleton voxels outside the mask sample the EDT's zero and are kept in the
    sums and in the mean denominators. The EDT is released before returning.
    The keyword arguments are mask provenance, recorded as given.
    """
    mask_info = ForegroundMaskInfo(
        path=path,
        header_spatial_unit=header_spatial_unit,
        effective_spatial_unit=effective_spatial_unit,
        spatial_unit_source=spatial_unit_source,
        foreground_voxels=int(np.count_nonzero(foreground)),
        touches_image_boundary=touches_image_boundary(foreground),
    )
    edt = ndimage.distance_transform_edt(foreground, sampling=tuple(float(value) for value in spacing_um))
    reference = _summarize(edt, ref, foreground, "Reference")
    prediction = _summarize(edt, pred, foreground, "Prediction")
    del edt

    warnings: list[str] = []
    if mask_info.touches_image_boundary:
        warnings.append(
            "Foreground mask touches the image boundary. Background outside the image is not observed, so "
            "EDT values near that boundary may overestimate the clearance."
        )
    for summary, name in ((reference, "Reference"), (prediction, "Prediction")):
        if summary.outside_mask_voxels:
            warnings.append(
                f"{name} skeleton has {summary.outside_mask_voxels} of {summary.skeleton_voxels} voxels "
                f"({100.0 * float(summary.outside_mask_fraction):.2f}%) outside the foreground mask. They count as "
                "zero EDT and stay in the sum and the mean."
            )

    signed = absolute = reason = None
    if reference.edt_sum_um > 0.0:
        signed = (prediction.edt_sum_um - reference.edt_sum_um) / reference.edt_sum_um
        absolute = abs(signed)
    elif reference.skeleton_voxels == 0:
        reason = "Reference EDT sum is zero because the reference skeleton is empty; relative differences are undefined."
    else:
        reason = (
            "Reference EDT sum is zero because no reference voxel lies inside the foreground mask; "
            "relative differences are undefined."
        )

    return ForegroundEdtAgreement(
        reference=reference,
        prediction=prediction,
        mask=mask_info,
        signed_relative_difference=signed,
        absolute_relative_difference=absolute,
        relative_difference_unavailable_reason=reason,
        warnings=warnings,
    )


def touches_image_boundary(mask: np.ndarray) -> bool:
    """True when any foreground voxel lies on any face of the image."""
    for axis in range(mask.ndim):
        if np.take(mask, 0, axis=axis).any() or np.take(mask, -1, axis=axis).any():
            return True
    return False


def _summarize(edt: np.ndarray, skeleton: np.ndarray, foreground: np.ndarray, name: str) -> ForegroundEdtSummary:
    voxels = int(np.count_nonzero(skeleton))
    outside = int(np.count_nonzero(skeleton & ~foreground))
    total = float(np.sum(edt[skeleton], dtype=np.float64))
    if voxels == 0:
        return ForegroundEdtSummary(
            edt_sum_um=total,
            skeleton_voxels=0,
            outside_mask_voxels=0,
            unavailable_reason=f"{name} skeleton is empty; mean EDT and outside-mask fraction are undefined.",
        )
    return ForegroundEdtSummary(
        edt_sum_um=total,
        skeleton_voxels=voxels,
        outside_mask_voxels=outside,
        mean_edt_um=total / voxels,
        outside_mask_fraction=outside / voxels,
    )
