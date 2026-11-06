"""GraphML–GraphML evaluation on stored floating-point polylines.

Both graphs live in the voxel-index frame of one coordinate image, which
supplies the affine and spatial unit. Geometry is length-weighted over the
stored polylines (see ``graph_geometry``); topology and endpoints come from the
stored connectivity. The foreground EDT-sum agreement is NIfTI-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

from skelhub.core import (
    INPUT_REPRESENTATION_GRAPHML,
    CountComparison,
    EvaluationResult,
    GeometryResult,
    GraphEvaluationInfo,
    GraphSamplingInfo,
    TopologyResult,
)

from .evaluator import STATUS_BOTH_EMPTY, STATUS_EMPTY_PREDICTION, STATUS_EMPTY_REFERENCE, STATUS_OK
from .geometry import unavailable_coverage
from .graph_geometry import (
    PERCENTILE,
    PERCENTILE_METHOD,
    SegmentDistanceIndex,
    directional_curve_distances,
    length_coverage,
    length_match,
    resolve_sample_step,
    summarize_curve_distances,
)
from .graph_inputs import (
    ENDPOINT_TOLERANCE_VOXELS,
    OUTSIDE_IMAGE_MARGIN_VOXELS,
    STATE_NO_NODES,
    WORLD_MATCH_FRACTION,
    CoordinateFrame,
    GraphCurveInput,
    prepare_graph_input,
    read_coordinate_image,
)
from .validation import RELATIVE_TOLERANCE, normalize_tolerances


GRAPH_METRIC_DEFINITIONS = "skelhub-graph-v1"
GRAPH_TOPOLOGY_DEFINITION = (
    "graph connectivity: beta_0 = connected components (isolated nodes included); "
    "beta_1 = E - V + beta_0; beta_2 = 0 structurally (a 1D graph has no cavities); chi = V - E"
)
GRAPH_ENDPOINT_DEFINITION = "node with degree 1; a self-loop adds 2 to its node's degree"
GRAPH_DISTANCE_DEFINITION = (
    "Euclidean distance from a length-weighted sample on one graph's stored polylines to the nearest "
    "point on any segment of the other graph, um"
)

Radius = float | Sequence[float]
Log = Callable[[str], None] | None


def evaluate_graph_files(
    pred_path: str | Path,
    ref_path: str | Path,
    *,
    coordinate_image_path: str | Path,
    buffer_radius: Radius,
    buffer_radius_unit: str = "voxels",
    coordinate_spatial_unit: str | None = None,
    sample_step_um: float | None = None,
    log: Log = None,
) -> EvaluationResult:
    """Evaluate a prediction GraphML against a reference GraphML.

    ``coordinate_image_path`` is a NIfTI whose header (voxels are not read)
    defines the voxel-index frame of both graphs' ``voxel_pos`` and
    ``centerline_voxel_points``. ``coordinate_spatial_unit`` labels its header
    unit when that is unknown. ``sample_step_um`` overrides the automatic
    maximum sampling interval ``0.1 * min(spacing_um)``.
    """
    _log(log, "Validating inputs...")
    coordinates = read_coordinate_image(coordinate_image_path, supplied_unit=coordinate_spatial_unit)
    spacing_um = coordinates.spacing_um
    sampling = resolve_sample_step(sample_step_um, spacing_um)
    tolerances = normalize_tolerances(buffer_radius, buffer_radius_unit, spacing_um)
    _log(log, "Reading graphs...")
    pred = prepare_graph_input(pred_path, coordinates, label="Prediction graph")
    ref = prepare_graph_input(ref_path, coordinates, label="Reference graph")
    status = _status(pred, ref)

    _log(log, f"Computing geometry (sampling interval {sampling.resolved_step_um:g} um)...")
    geometry, samples = _compute_geometry(pred, ref, tolerances, sampling, spacing_um, status)

    _log(log, "Computing topology and endpoints...")
    topology = TopologyResult(
        reference=ref.betti_numbers(),
        prediction=pred.betti_numbers(),
        foreground_connectivity=None,
        background_connectivity=None,
    )
    endpoints = CountComparison(reference=ref.endpoints, prediction=pred.endpoints)
    graph_info = GraphEvaluationInfo(
        coordinate_image=coordinates.info(),
        sampling=sampling,
        prediction=pred.summary(samples[0]),
        reference=ref.summary(samples[1]),
    )
    return EvaluationResult(
        message=_message(status, geometry),
        status=status,
        geometry=geometry,
        topology=topology,
        endpoints=endpoints,
        pred_path=pred.path,
        ref_path=ref.path,
        config=_config(buffer_radius_unit, tolerances),
        metadata=_metadata(coordinates, pred, ref),
        warnings=[
            *([coordinates.frame.units.warning] if coordinates.frame.units.warning else []),
            *pred.warnings,
            *ref.warnings,
            *_status_warnings(status, pred, ref),
        ],
        input_representation=INPUT_REPRESENTATION_GRAPHML,
        graph=graph_info,
    )


def _compute_geometry(
    pred: GraphCurveInput,
    ref: GraphCurveInput,
    tolerances: list,
    sampling: GraphSamplingInfo,
    spacing_um: tuple[float, float, float],
    status: str,
) -> tuple[GeometryResult, tuple[int, int]]:
    if status == STATUS_OK:
        piece_length = float(min(spacing_um))
        ref_index = SegmentDistanceIndex(ref.segment_starts_um, ref.segment_ends_um, piece_length_um=piece_length)
        pred_to_ref = directional_curve_distances(
            pred.segment_starts_um, pred.segment_ends_um, ref_index, sampling.resolved_step_um
        )
        del ref_index
        pred_index = SegmentDistanceIndex(pred.segment_starts_um, pred.segment_ends_um, piece_length_um=piece_length)
        ref_to_pred = directional_curve_distances(
            ref.segment_starts_um, ref.segment_ends_um, pred_index, sampling.resolved_step_um
        )
        geometry = GeometryResult(
            tolerances=[length_coverage(spec, pred_to_ref, ref_to_pred, spacing_um) for spec in tolerances],
            distances=summarize_curve_distances(pred_to_ref, ref_to_pred, sampling),
        )
        return geometry, (len(pred_to_ref.distances), len(ref_to_pred.distances))
    if status == STATUS_EMPTY_PREDICTION:
        geometry = GeometryResult(
            tolerances=[
                length_match(
                    spec,
                    precision=0.0,
                    recall=0.0,
                    matched_pred=0.0,
                    unmatched_pred=0.0,
                    matched_ref=0.0,
                    unmatched_ref=ref.total_length_um,
                )
                for spec in tolerances
            ],
            distances_unavailable_reason=(
                f"Prediction graph has no curve geometry ({_state_text(pred)}); distances to it are undefined."
            ),
        )
        return geometry, (0, 0)
    if status == STATUS_EMPTY_REFERENCE:
        reason = (
            f"Reference graph has no curve geometry ({_state_text(ref)}); reference-based geometry is undefined."
        )
    else:
        reason = (
            f"Neither graph has curve geometry (prediction: {_state_text(pred)}; reference: {_state_text(ref)}); "
            "geometry is undefined and no score is awarded."
        )
    geometry = GeometryResult(
        tolerances=[unavailable_coverage(spec) for spec in tolerances],
        coverage_unavailable_reason=reason,
        distances_unavailable_reason=reason,
    )
    return geometry, (0, 0)


def _status(pred: GraphCurveInput, ref: GraphCurveInput) -> str:
    """Geometry availability from positive edge length, with the NIfTI status names."""
    pred_curve = pred.total_length_um > 0.0
    ref_curve = ref.total_length_um > 0.0
    if pred_curve and ref_curve:
        return STATUS_OK
    if ref_curve:
        return STATUS_EMPTY_PREDICTION
    if pred_curve:
        return STATUS_EMPTY_REFERENCE
    return STATUS_BOTH_EMPTY


def _state_text(graph: GraphCurveInput) -> str:
    if graph.state == STATE_NO_NODES:
        return "no graph nodes"
    if graph.segment_starts_um.shape[0] == 0:
        return f"{graph.node_count} node(s) but no edges"
    return f"{graph.edge_count} edge(s)"


def _status_warnings(status: str, pred: GraphCurveInput, ref: GraphCurveInput) -> list[str]:
    if status == STATUS_OK:
        return []
    if status == STATUS_EMPTY_PREDICTION:
        return [
            f"Prediction graph has no curve geometry ({_state_text(pred)}): the prediction failed. "
            "Coverage is zero and distances are unavailable."
        ]
    if status == STATUS_EMPTY_REFERENCE:
        return [
            f"Reference graph has no curve geometry ({_state_text(ref)}): this pair is unsuitable for "
            "reference-based quality scoring."
        ]
    return [
        f"Neither graph has curve geometry (prediction: {_state_text(pred)}; reference: {_state_text(ref)}): "
        "geometry is unavailable. Topology and endpoint agreement do not indicate a successful prediction."
    ]


def _config(buffer_radius_unit: str, tolerances: list) -> dict:
    return {
        "buffer_radius_unit": buffer_radius_unit,
        "requested_tolerances": [spec.requested_value for spec in tolerances],
        "tolerances_um": [spec.tolerance_um for spec in tolerances],
        "primary_tolerance_um": tolerances[0].tolerance_um,
        "topology_definition": GRAPH_TOPOLOGY_DEFINITION,
        "endpoint_definition": GRAPH_ENDPOINT_DEFINITION,
        "distance": GRAPH_DISTANCE_DEFINITION,
        "coverage_weighting": "curve length",
        "percentile": PERCENTILE,
        "percentile_method": PERCENTILE_METHOD,
        "tolerance_relative_slack": RELATIVE_TOLERANCE,
        "endpoint_tolerance_voxels": ENDPOINT_TOLERANCE_VOXELS,
        "world_coordinate_match_fraction_of_spacing": WORLD_MATCH_FRACTION,
        "outside_image_margin_voxels": OUTSIDE_IMAGE_MARGIN_VOXELS,
        "metric_definitions": GRAPH_METRIC_DEFINITIONS,
    }


def _metadata(coordinates: CoordinateFrame, pred: GraphCurveInput, ref: GraphCurveInput) -> dict:
    return {
        "shape": [int(value) for value in coordinates.shape],
        "spacing_um": [float(value) for value in coordinates.spacing_um],
        "affine_um": coordinates.affine_um.tolist(),
        "pred_length_um": pred.total_length_um,
        "ref_length_um": ref.total_length_um,
    }


def _message(status: str, geometry: GeometryResult) -> str:
    primary = geometry.primary
    if primary.f1 is None:
        return f"GraphML evaluation completed with status={status}; geometry unavailable."
    return (
        f"GraphML evaluation completed with status={status}: "
        f"F1={primary.f1:.4f} at {primary.tolerance_um:g} um (primary tolerance)."
    )


def _log(log: Log, message: str) -> None:
    if log is not None:
        log(message)
