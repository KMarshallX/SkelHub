"""Voxel-based evaluation entrypoints for binary 3D skeleton volumes.

Three entrypoints (files, in-memory arrays, ``SkeletonResult``) validate their
inputs into ``SkeletonVolumeInput`` objects and share one metric path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from skelhub.core import (
    CountComparison,
    EvaluationResult,
    GeometryResult,
    SkeletonResult,
    TopologyResult,
    VolumeData,
)

from .endpoints import count_endpoints
from .geometry import (
    PERCENTILE,
    PERCENTILE_METHOD,
    coverage_at_tolerance,
    directional_distances,
    empty_prediction_coverage,
    summarize_distances,
    unavailable_coverage,
)
from .topology import BACKGROUND_CONNECTIVITY, FOREGROUND_CONNECTIVITY, compute_betti_numbers
from .validation import (
    AFFINE_MATCH_FRACTION,
    RELATIVE_TOLERANCE,
    SkeletonVolumeInput,
    array_affine,
    normalize_tolerances,
    prepare_skeleton_nifti,
    prepare_skeleton_volume,
    read_skeleton_nifti,
    require_matching_shapes,
    validate_matching_inputs,
    volume_input_from_volume_data,
)


METRIC_DEFINITIONS = "skelhub-voxel-v2"

STATUS_OK = "ok"
STATUS_EMPTY_PREDICTION = "empty_prediction"
STATUS_EMPTY_REFERENCE = "empty_reference"
STATUS_BOTH_EMPTY = "both_empty"

Radius = float | Sequence[float]
Log = Callable[[str], None] | None


def evaluate_skeleton_files(
    pred_path: str | Path,
    ref_path: str | Path,
    *,
    buffer_radius: Radius,
    buffer_radius_unit: str = "voxels",
    pred_spatial_unit: str | None = None,
    ref_spatial_unit: str | None = None,
    log: Log = None,
) -> EvaluationResult:
    """Evaluate two on-disk binary 3D skeleton NIfTI volumes.

    Units come from each header and the full affines must agree after
    conversion to micrometres. ``pred_spatial_unit`` / ``ref_spatial_unit``
    label headers whose unit is unknown; they cannot override a known unit.
    """
    _log(log, "Validating inputs...")
    raw_pred = read_skeleton_nifti(pred_path, label="Prediction skeleton")
    raw_ref = read_skeleton_nifti(ref_path, label="Reference skeleton")
    require_matching_shapes(raw_pred.data.shape, raw_ref.data.shape)
    pred = prepare_skeleton_nifti(raw_pred, label="Prediction skeleton", supplied_unit=pred_spatial_unit, role="pred")
    ref = prepare_skeleton_nifti(raw_ref, label="Reference skeleton", supplied_unit=ref_spatial_unit, role="ref")
    return _evaluate_prepared_inputs(pred, ref, buffer_radius, buffer_radius_unit, log)


def evaluate_skeleton_volumes(
    pred_skel: np.ndarray,
    ref_skel: np.ndarray,
    *,
    spacing: Sequence[float],
    spacing_unit: str,
    buffer_radius: Radius,
    buffer_radius_unit: str = "voxels",
    affine: np.ndarray | None = None,
    pred_label: str = "Prediction skeleton",
    ref_label: str = "Reference skeleton",
    log: Log = None,
) -> EvaluationResult:
    """Evaluate two in-memory binary 3D skeletons on one shared voxel grid.

    Same-grid contract: both arrays use the same voxel-to-world transform,
    ``diag(spacing)`` or the explicit ``affine`` (whose column lengths must equal
    ``spacing``), expressed in ``spacing_unit`` (``mm``, ``um``, ``micron`` or
    ``meter``).
    """
    _log(log, "Validating inputs...")
    shared_affine = array_affine(spacing, affine)
    require_matching_shapes(np.shape(pred_skel), np.shape(ref_skel))
    pred = prepare_skeleton_volume(pred_skel, shared_affine, None, supplied_unit=spacing_unit, label=pred_label)
    ref = prepare_skeleton_volume(ref_skel, shared_affine, None, supplied_unit=spacing_unit, label=ref_label)
    return _evaluate_prepared_inputs(pred, ref, buffer_radius, buffer_radius_unit, log)


def evaluate_skeleton_result(
    prediction: SkeletonResult,
    reference: VolumeData,
    *,
    input_volume: VolumeData,
    buffer_radius: Radius,
    buffer_radius_unit: str = "voxels",
    pred_spatial_unit: str | None = None,
    ref_spatial_unit: str | None = None,
    log: Log = None,
) -> EvaluationResult:
    """Evaluate a backend ``SkeletonResult`` against a reference skeleton volume.

    ``input_volume`` is the volume the backend ran on; its affine and header
    units define the prediction's grid. ``reference`` uses its own affine and
    header units. ``pred_spatial_unit`` / ``ref_spatial_unit`` label unknown
    (or missing) header units of ``input_volume`` / ``reference``.
    """
    _log(log, "Validating inputs...")
    require_matching_shapes(np.shape(prediction.skeleton), np.shape(reference.data))
    pred = volume_input_from_volume_data(
        input_volume,
        data=prediction.skeleton,
        label=f"Prediction skeleton ({prediction.algorithm_name})",
        supplied_unit=pred_spatial_unit,
        role="pred",
    )
    ref = volume_input_from_volume_data(
        reference, label="Reference skeleton", supplied_unit=ref_spatial_unit, role="ref"
    )
    return _evaluate_prepared_inputs(pred, ref, buffer_radius, buffer_radius_unit, log)


def _evaluate_prepared_inputs(
    pred: SkeletonVolumeInput,
    ref: SkeletonVolumeInput,
    buffer_radius: Radius,
    buffer_radius_unit: str,
    log: Log,
) -> EvaluationResult:
    validate_matching_inputs(pred, ref)
    spacing_um = ref.spacing_um
    tolerances = normalize_tolerances(buffer_radius, buffer_radius_unit, spacing_um)

    pred_voxels = int(np.count_nonzero(pred.data))
    ref_voxels = int(np.count_nonzero(ref.data))
    status = _status(pred_voxels, ref_voxels)

    _log(log, "Computing geometry...")
    geometry = _compute_geometry(pred.data, ref.data, spacing_um, tolerances, status, ref_voxels)

    _log(log, "Computing topology and endpoints...")
    topology = TopologyResult(
        reference=compute_betti_numbers(ref.data),
        prediction=compute_betti_numbers(pred.data),
        foreground_connectivity=FOREGROUND_CONNECTIVITY,
        background_connectivity=BACKGROUND_CONNECTIVITY,
    )
    endpoints = CountComparison(reference=count_endpoints(ref.data), prediction=count_endpoints(pred.data))

    return EvaluationResult(
        message=_message(status, geometry),
        status=status,
        geometry=geometry,
        topology=topology,
        endpoints=endpoints,
        pred_path=pred.path,
        ref_path=ref.path,
        config={
            "buffer_radius_unit": buffer_radius_unit,
            "requested_tolerances": [spec.requested_value for spec in tolerances],
            "tolerances_um": [spec.tolerance_um for spec in tolerances],
            "primary_tolerance_um": tolerances[0].tolerance_um,
            "foreground_connectivity": FOREGROUND_CONNECTIVITY,
            "background_connectivity": BACKGROUND_CONNECTIVITY,
            "endpoint_definition": "foreground voxel with exactly one 26-neighbour",
            "distance": "Euclidean distance between voxel centres, um",
            "percentile": PERCENTILE,
            "percentile_method": f"numpy {PERCENTILE_METHOD}",
            "tolerance_relative_slack": RELATIVE_TOLERANCE,
            "affine_match_fraction_of_spacing": AFFINE_MATCH_FRACTION,
            "metric_definitions": METRIC_DEFINITIONS,
        },
        metadata={
            "shape": [int(value) for value in ref.data.shape],
            "spacing_um": [float(value) for value in spacing_um],
            "affine_um": ref.affine_um.tolist(),
            "source_spatial_units": {"prediction": pred.units.header_unit, "reference": ref.units.header_unit},
            "effective_spatial_units": {
                "prediction": pred.units.effective_unit,
                "reference": ref.units.effective_unit,
            },
            "spatial_unit_sources": {"prediction": pred.units.source, "reference": ref.units.source},
            "pred_voxels": pred_voxels,
            "ref_voxels": ref_voxels,
        },
        warnings=[
            *(volume.units.warning for volume in (pred, ref) if volume.units.warning),
            *_status_warnings(status),
        ],
    )


def _compute_geometry(
    pred: np.ndarray,
    ref: np.ndarray,
    spacing_um: tuple[float, float, float],
    tolerances: list,
    status: str,
    ref_voxels: int,
) -> GeometryResult:
    if status == STATUS_OK:
        pred_to_ref, ref_to_pred = directional_distances(pred, ref, spacing_um)
        return GeometryResult(
            tolerances=[coverage_at_tolerance(spec, pred_to_ref, ref_to_pred, spacing_um) for spec in tolerances],
            distances=summarize_distances(pred_to_ref, ref_to_pred),
        )
    if status == STATUS_EMPTY_PREDICTION:
        return GeometryResult(
            tolerances=[empty_prediction_coverage(spec, ref_voxels) for spec in tolerances],
            distances_unavailable_reason="Prediction is empty; distances to an empty skeleton are undefined.",
        )
    reason = (
        "Reference is empty; reference-based geometry is undefined."
        if status == STATUS_EMPTY_REFERENCE
        else "Both skeletons are empty; geometry is undefined and no score is awarded."
    )
    return GeometryResult(
        tolerances=[unavailable_coverage(spec) for spec in tolerances],
        coverage_unavailable_reason=reason,
        distances_unavailable_reason=reason,
    )


def _status(pred_voxels: int, ref_voxels: int) -> str:
    if pred_voxels and ref_voxels:
        return STATUS_OK
    if ref_voxels:
        return STATUS_EMPTY_PREDICTION
    if pred_voxels:
        return STATUS_EMPTY_REFERENCE
    return STATUS_BOTH_EMPTY


def _status_warnings(status: str) -> list[str]:
    return {
        STATUS_OK: [],
        STATUS_EMPTY_PREDICTION: [
            "Prediction skeleton is empty: the prediction failed. Coverage is zero and distances are unavailable."
        ],
        STATUS_EMPTY_REFERENCE: [
            "Reference skeleton is empty: this pair is unsuitable for reference-based quality scoring."
        ],
        STATUS_BOTH_EMPTY: [
            "Both skeletons are empty: geometry is unavailable. Topology and endpoint agreement do not "
            "indicate a successful prediction."
        ],
    }[status]


def _message(status: str, geometry: GeometryResult) -> str:
    primary = geometry.primary
    if primary.f1 is None:
        return f"Evaluation completed with status={status}; geometry unavailable."
    return (
        f"Evaluation completed with status={status}: "
        f"F1={primary.f1:.4f} at {primary.tolerance_um:g} um (primary tolerance)."
    )


def _log(log: Log, message: str) -> None:
    if log is not None:
        log(message)
