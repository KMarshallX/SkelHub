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


EVALUATION_SCHEMA_VERSION = "2.0"


@dataclass(slots=True)
class ToleranceMatch:
    """Directional coverage at one geometry tolerance.

    Scores and counts are ``None`` when the comparison has no reference-based
    meaning (empty reference); see ``GeometryResult.coverage_unavailable_reason``.
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


@dataclass(slots=True)
class DistanceSummary:
    """Directional and symmetric voxel-centre distances in micrometres."""

    mean_pred_to_ref_um: float
    mean_ref_to_pred_um: float
    symmetric_mean_um: float
    p95_pred_to_ref_um: float
    p95_ref_to_pred_um: float
    symmetric_p95_um: float
    max_pred_to_ref_um: float
    max_ref_to_pred_um: float
    hausdorff_um: float


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
    """Voxel Betti numbers and Euler characteristic of one skeleton."""

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
    """Betti numbers of the original (unbuffered) reference and prediction."""

    reference: BettiNumbers
    prediction: BettiNumbers
    foreground_connectivity: int = 26
    background_connectivity: int = 6

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
class EvaluationResult:
    """Standardized voxel-based evaluation result (schema 2.0).

    ``status`` is one of ``ok``, ``empty_prediction``, ``empty_reference`` or
    ``both_empty``. There is no combined quality score by design.
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
