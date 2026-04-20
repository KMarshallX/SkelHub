"""Voxel-based evaluation entrypoints for binary 3D skeleton volumes."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np

from skelhub.core import EvaluationResult

from .geometry import (
    build_buffer_structuring_element,
    compute_geometry_scores,
    count_geometry_terms,
    dilate_skeleton,
)
from .morphology import (
    BACKGROUND_CONNECTIVITY,
    FOREGROUND_CONNECTIVITY,
    clip_and_normalize_morphology,
    compute_raw_morphology_metrics,
)
from .validation import (
    SkeletonVolumeInput,
    build_anisotropy_warning,
    load_skeleton_nifti,
    prepare_skeleton_volume,
    validate_buffer_radius,
    validate_matching_inputs,
)


def evaluate_skeleton_files(
    pred_path: str | Path,
    ref_path: str | Path,
    *,
    buffer_radius: float,
    buffer_radius_unit: str = "voxels",
    log: Callable[[str], None] | None = None,
) -> EvaluationResult:
    """Evaluate two on-disk binary 3D skeleton NIfTI volumes."""
    if log is not None:
        log("Validating inputs...")

    pred_volume = load_skeleton_nifti(pred_path, label="Prediction skeleton")
    ref_volume = load_skeleton_nifti(ref_path, label="Reference skeleton")
    return _evaluate_prepared_inputs(
        pred_volume,
        ref_volume,
        buffer_radius=buffer_radius,
        buffer_radius_unit=buffer_radius_unit,
        log=log,
    )


def evaluate_skeleton_volumes(
    pred_skel: np.ndarray,
    ref_skel: np.ndarray,
    *,
    spacing: tuple[float, float, float],
    buffer_radius: float,
    buffer_radius_unit: str = "voxels",
    spacing_unit: str = "unknown",
    pred_label: str = "Prediction skeleton",
    ref_label: str = "Reference skeleton",
    log: Callable[[str], None] | None = None,
) -> EvaluationResult:
    """Evaluate two in-memory binary 3D skeleton volumes.

    This array-level function is the core v1 evaluation path and leaves a clean
    future path for wrappers that consume `SkeletonResult` objects directly.
    """
    if log is not None:
        log("Validating inputs...")

    pred_volume = prepare_skeleton_volume(
        pred_skel,
        spacing,
        label=pred_label,
        spatial_unit=spacing_unit,
    )
    ref_volume = prepare_skeleton_volume(
        ref_skel,
        spacing,
        label=ref_label,
        spatial_unit=spacing_unit,
    )
    return _evaluate_prepared_inputs(
        pred_volume,
        ref_volume,
        buffer_radius=buffer_radius,
        buffer_radius_unit=buffer_radius_unit,
        log=log,
    )


def _evaluate_prepared_inputs(
    pred_volume: SkeletonVolumeInput,
    ref_volume: SkeletonVolumeInput,
    *,
    buffer_radius: float,
    buffer_radius_unit: str,
    log: Callable[[str], None] | None,
) -> EvaluationResult:
    validate_buffer_radius(buffer_radius, buffer_radius_unit)
    validate_matching_inputs(
        pred_volume,
        ref_volume,
        require_matching_units_for_physical_radius=buffer_radius_unit == "um",
    )

    warnings: list[str] = []
    anisotropy_warning = build_anisotropy_warning(
        ref_volume.spacing,
        radius_unit=buffer_radius_unit,
        spatial_unit=ref_volume.spatial_unit,
    )
    if anisotropy_warning is not None:
        warnings.append(anisotropy_warning)

    structure, voxel_equivalent, radius_mode = build_buffer_structuring_element(
        radius=buffer_radius,
        radius_unit=buffer_radius_unit,
        spacing=ref_volume.spacing,
        spatial_unit=ref_volume.spatial_unit,
    )

    pred_voxels = int(np.count_nonzero(pred_volume.data))
    ref_voxels = int(np.count_nonzero(ref_volume.data))

    if log is not None:
        log("Dilating reference skeleton...")
    ref_buffer = dilate_skeleton(ref_volume.data, structure)

    if log is not None:
        log("Dilating predicted skeleton...")
    pred_buffer = dilate_skeleton(pred_volume.data, structure)

    tp, fp, fn = count_geometry_terms(pred_volume.data, ref_volume.data, ref_buffer, pred_buffer)
    cp, cr = compute_geometry_scores(
        tp=tp,
        fp=fp,
        fn=fn,
        pred_voxels=pred_voxels,
        ref_voxels=ref_voxels,
        warnings=warnings,
    )

    if log is not None:
        log("Counting connected components...")
        log("Counting endpoints...")
    raw_morphology, supporting_counts = compute_raw_morphology_metrics(
        pred_volume.data,
        ref_volume.data,
        warnings,
    )

    occ_clipped, occ_normalized = clip_and_normalize_morphology(raw_morphology["OCC"])
    bcc_clipped, bcc_normalized = clip_and_normalize_morphology(raw_morphology["BCC"])
    e_clipped, e_normalized = clip_and_normalize_morphology(raw_morphology["E"])

    if log is not None:
        log("Computing global performance score...")
    performance = float(np.mean([cp, cr, occ_normalized, bcc_normalized, e_normalized]))

    message = (
        "Evaluation completed successfully: "
        f"P={performance:.4f}, Cp={cp:.4f}, Cr={cr:.4f}."
    )
    return EvaluationResult(
        message=message,
        input_path=pred_volume.path,
        pred_path=pred_volume.path,
        ref_path=ref_volume.path,
        TP=tp,
        FP=fp,
        FN=fn,
        Cp=cp,
        Cr=cr,
        OCC=raw_morphology["OCC"],
        OCC_clipped=occ_clipped,
        OCC_normalized=occ_normalized,
        BCC=raw_morphology["BCC"],
        BCC_clipped=bcc_clipped,
        BCC_normalized=bcc_normalized,
        E=raw_morphology["E"],
        E_clipped=e_clipped,
        E_normalized=e_normalized,
        P=performance,
        buffer_radius=float(buffer_radius),
        buffer_radius_unit=buffer_radius_unit,
        buffer_radius_mode=radius_mode,
        foreground_connectivity=FOREGROUND_CONNECTIVITY,
        background_connectivity=BACKGROUND_CONNECTIVITY,
        warnings=warnings,
        metadata={
            "shape": tuple(int(value) for value in pred_volume.data.shape),
            "spacing": tuple(float(value) for value in pred_volume.spacing),
            "spacing_unit": ref_volume.spatial_unit,
            "pred_voxels": pred_voxels,
            "ref_voxels": ref_voxels,
            "buffer_radius_voxel_equivalent": tuple(float(value) for value in voxel_equivalent),
            "supporting_counts": supporting_counts,
        },
    )
