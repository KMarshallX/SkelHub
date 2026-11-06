"""Framework-level data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(slots=True)
class VolumeData:
    """Standardized in-memory NIfTI volume."""

    data: np.ndarray
    affine: np.ndarray
    header: Any
    path: str | None = None
    spacing: tuple[float, float, float] | None = None


@dataclass(slots=True)
class GraphResult:
    """Placeholder graph container for future postprocessing stages."""

    nodes: list[tuple[int, int, int]] = field(default_factory=list)
    edges: list[tuple[int, int]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SkeletonResult:
    """Standardized skeletonization result returned by all backends."""

    algorithm_name: str
    skeleton: np.ndarray
    input_metadata: dict[str, Any] = field(default_factory=dict)
    runtime_stats: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    backend_metadata: dict[str, Any] = field(default_factory=dict)
    graph: GraphResult | None = None


EVALUATION_SCHEMA_VERSION = "3.0"
FOREGROUND_EDT_NO_MASK_REASON = "No foreground mask supplied"
FOREGROUND_EDT_GRAPHML_REASON = (
    "Foreground EDT-sum agreement is NIfTI-only; it is not available for GraphML inputs"
)
INPUT_REPRESENTATION_NIFTI = "nifti"
INPUT_REPRESENTATION_GRAPHML = "graphml"


@dataclass(slots=True)
class ToleranceMatch:
    """Directional coverage at one geometry tolerance.

    Scores and counts are ``None`` when the comparison has no reference-based
    meaning (empty reference); see ``GeometryResult.coverage_unavailable_reason``.
    NIfTI runs fill the ``*_voxels`` counts; GraphML runs fill the ``*_length_um``
    curve lengths instead. The other family is always ``None``.
    """

    tolerance_um: float
    requested_value: float
    requested_unit: str
    is_primary: bool
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    matched_prediction_voxels: int | None = None
    unmatched_prediction_voxels: int | None = None
    matched_reference_voxels: int | None = None
    unmatched_reference_voxels: int | None = None
    matched_prediction_length_um: float | None = None
    unmatched_prediction_length_um: float | None = None
    matched_reference_length_um: float | None = None
    unmatched_reference_length_um: float | None = None


@dataclass(slots=True)
class DistanceSummary:
    """Directional and symmetric distances in micrometres.

    NIfTI runs use exact voxel-centre distances. GraphML runs use
    length-weighted samples of the stored polylines; their maxima and Hausdorff
    distance are sampled lower bounds, so ``hausdorff_is_approximate`` is True
    and the true value lies in ``[hausdorff_um, hausdorff_upper_bound_um]``.
    """

    mean_pred_to_ref_um: float
    mean_ref_to_pred_um: float
    symmetric_mean_um: float
    p95_pred_to_ref_um: float
    p95_ref_to_pred_um: float
    symmetric_p95_um: float
    max_pred_to_ref_um: float
    max_ref_to_pred_um: float
    hausdorff_um: float
    hausdorff_is_approximate: bool = False
    sampling_error_bound_um: float | None = None
    hausdorff_upper_bound_um: float | None = None


@dataclass(slots=True)
class GeometryResult:
    """Tolerance coverage (in requested order) and distance summaries."""

    tolerances: list[ToleranceMatch] = field(default_factory=list)
    distances: DistanceSummary | None = None
    coverage_unavailable_reason: str | None = None
    distances_unavailable_reason: str | None = None

    @property
    def primary(self) -> ToleranceMatch:
        """The tolerance result for the first requested tolerance."""
        return self.tolerances[0]


@dataclass(slots=True)
class BettiNumbers:
    """Betti numbers and Euler characteristic of one skeleton.

    NIfTI: voxel topology (foreground-26 / background-6). GraphML: computed from
    stored connectivity, with ``beta_2`` structurally zero for a 1D graph.
    """

    beta_0: int
    beta_1: int
    beta_2: int
    euler_characteristic: int


@dataclass(slots=True)
class CountComparison:
    """Reference and prediction counts with signed (pred - ref) and absolute error."""

    reference: int
    prediction: int

    @property
    def signed_difference(self) -> int:
        return self.prediction - self.reference

    @property
    def absolute_error(self) -> int:
        return abs(self.prediction - self.reference)


@dataclass(slots=True)
class TopologyResult:
    """Betti numbers of the original (unbuffered) reference and prediction.

    The voxel connectivities are ``None`` for GraphML inputs, whose topology
    comes from the stored edges.
    """

    reference: BettiNumbers
    prediction: BettiNumbers
    foreground_connectivity: int | None = 26
    background_connectivity: int | None = 6

    def comparison(self, k: int) -> CountComparison:
        """Count comparison for Betti number ``beta_k``, k in {0, 1, 2}."""
        if k not in (0, 1, 2):
            raise ValueError(f"Betti index must be 0, 1 or 2; got {k}.")
        name = f"beta_{k}"
        return CountComparison(getattr(self.reference, name), getattr(self.prediction, name))

    @property
    def betti_count_agreement(self) -> bool:
        """True when all three Betti counts agree. Not proof of matching structure."""
        return all(self.comparison(k).absolute_error == 0 for k in (0, 1, 2))


@dataclass(slots=True)
class ForegroundEdtSummary:
    """Foreground EDT sampled at every voxel of one skeleton, in micrometres.

    Skeleton voxels outside the mask sample zero and stay in the sum and the
    mean's denominator. ``mean_edt_um`` and ``outside_mask_fraction`` are
    ``None`` for an empty skeleton; ``unavailable_reason`` then says why.
    """

    edt_sum_um: float
    skeleton_voxels: int
    outside_mask_voxels: int
    mean_edt_um: float | None = None
    outside_mask_fraction: float | None = None
    unavailable_reason: str | None = None


@dataclass(slots=True)
class ForegroundMaskInfo:
    """Provenance of the shared foreground mask used for the EDT."""

    path: str | None
    header_spatial_unit: str | None
    effective_spatial_unit: str
    spatial_unit_source: str
    foreground_voxels: int
    touches_image_boundary: bool


@dataclass(slots=True)
class ForegroundEdtAgreement:
    """Foreground EDT-sum agreement between prediction and reference.

    Relative differences are fractions of the reference sum:
    ``(prediction - reference) / reference`` and its absolute value. Both are
    ``None`` when the reference sum is zero. Matching sums do not show spatial
    or topological agreement.
    """

    reference: ForegroundEdtSummary
    prediction: ForegroundEdtSummary
    mask: ForegroundMaskInfo
    signed_relative_difference: float | None = None
    absolute_relative_difference: float | None = None
    relative_difference_unavailable_reason: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GraphInputSummary:
    """What one GraphML input contributed to the evaluation.

    ``state`` is ``curve_geometry`` (positive edge length), ``no_curve_geometry``
    (nodes but no edges) or ``no_nodes``. ``edge_paths`` is ``stored``
    (``centerline_voxel_points``), ``straight_node_segments`` (the file declares
    no edge paths, so each edge is the segment between its nodes) or ``none``
    (no edges). Isolated nodes count in topology but carry no curve geometry.
    """

    path: str | None
    state: str
    nodes: int
    edges: int
    isolated_nodes: int
    self_loops: int
    parallel_edges: int
    total_length_um: float
    segments: int
    edge_paths: str
    reversed_edge_paths: int
    repeated_points_skipped: int
    points_outside_image: int
    length_samples: int = 0


@dataclass(slots=True)
class CoordinateImageInfo:
    """The NIfTI header that defines the voxel-index frame shared by both graphs."""

    path: str
    shape: list[int]
    header_spatial_unit: str | None
    effective_spatial_unit: str
    spatial_unit_source: str
    spacing_um: list[float]
    affine_um: list[list[float]]


@dataclass(slots=True)
class GraphSamplingInfo:
    """Curve-sampling settings of a GraphML evaluation.

    ``mode`` is ``automatic`` (``resolved_step_um = 0.1 * min(spacing_um)``) or
    ``custom`` (``requested_step_um`` used as given). Every stored segment is cut
    into equal intervals no longer than ``resolved_step_um``; maxima are sampled
    to within ``hausdorff_error_bound_um = resolved_step_um / 2``.
    """

    mode: str
    requested_step_um: float | None
    resolved_step_um: float
    automatic_rule: str
    hausdorff_error_bound_um: float


@dataclass(slots=True)
class GraphEvaluationInfo:
    """GraphML-specific provenance: the coordinate frame, sampling and both inputs."""

    coordinate_image: CoordinateImageInfo
    sampling: GraphSamplingInfo
    prediction: GraphInputSummary
    reference: GraphInputSummary


@dataclass(slots=True)
class EvaluationResult:
    """Standardized evaluation result (schema 3.0, evaluation v3) for NIfTI or GraphML inputs.

    ``status`` is one of ``ok``, ``empty_prediction``, ``empty_reference`` or
    ``both_empty``. There is no combined quality score by design.
    ``input_representation`` is ``nifti`` or ``graphml``; ``graph`` holds the
    GraphML provenance and is ``None`` for NIfTI runs. ``foreground_edt`` is
    ``None`` when no foreground mask was supplied, and always for GraphML.
    """

    message: str
    status: str
    geometry: GeometryResult
    topology: TopologyResult
    endpoints: CountComparison
    pred_path: str | None = None
    ref_path: str | None = None
    schema_version: str = EVALUATION_SCHEMA_VERSION
    config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    foreground_edt: ForegroundEdtAgreement | None = None
    input_representation: str = INPUT_REPRESENTATION_NIFTI
    graph: GraphEvaluationInfo | None = None

    @property
    def foreground_edt_unavailable_reason(self) -> str | None:
        """Why the foreground EDT-sum agreement is missing, or ``None`` when it was computed."""
        if self.foreground_edt is not None:
            return None
        if self.input_representation == INPUT_REPRESENTATION_GRAPHML:
            return FOREGROUND_EDT_GRAPHML_REASON
        return FOREGROUND_EDT_NO_MASK_REASON
