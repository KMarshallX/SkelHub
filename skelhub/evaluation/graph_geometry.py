"""Continuous curve geometry for GraphML evaluation: length-weighted sampling and nearest-segment distances.

Inputs are straight segments in micrometres (from ``graph_inputs``). Each
segment of length ``L`` is cut into ``n = ceil(L / h)`` equal intervals; each
interval's midpoint is one sample with weight ``L / n``. Interval boundaries
are also measured, for the maxima only, and carry no weight. Every distance is
the exact Euclidean distance to the nearest point on any segment of the other
graph; nearest vertices or midpoints never stand in for it.

Memory is bounded: samples are generated and measured in fixed-size chunks,
and only one distance and one weight per midpoint are kept.
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Sequence

import numpy as np
from scipy.spatial import cKDTree

from skelhub.core import DistanceSummary, GraphSamplingInfo, ToleranceMatch

from .geometry import PERCENTILE, f1_score, within_tolerance
from .validation import ToleranceSpec


AUTOMATIC_STEP_FRACTION = 0.1
AUTOMATIC_STEP_RULE = "0.1 * min(coordinate-image spacing_um)"
SAMPLING_AUTOMATIC = "automatic"
SAMPLING_CUSTOM = "custom"
PERCENTILE_METHOD = "inverse weighted empirical CDF: smallest distance whose cumulative length fraction >= 0.95"
# Absorbs float rounding in cumulative weight fractions (uniform weights would otherwise land one sample late).
PERCENTILE_FRACTION_SLACK = 1e-12
# Samples (or query points) generated and measured per chunk.
SAMPLE_CHUNK = 65_536


def resolve_sample_step(sample_step_um: float | None, spacing_um: Sequence[float]) -> GraphSamplingInfo:
    """Return the sampling settings: automatic ``0.1 * min(spacing)`` or the requested step, unchanged."""
    if sample_step_um is None:
        step = AUTOMATIC_STEP_FRACTION * float(min(spacing_um))
        mode, requested = SAMPLING_AUTOMATIC, None
    else:
        if isinstance(sample_step_um, bool) or not isinstance(sample_step_um, Real):
            raise ValueError(f"Sample step must be a number in um; got {sample_step_um!r}.")
        step = float(sample_step_um)
        if not np.isfinite(step) or step <= 0:
            raise ValueError(f"Sample step must be a positive, finite number of um; got {step}.")
        mode, requested = SAMPLING_CUSTOM, step
    return GraphSamplingInfo(
        mode=mode,
        requested_step_um=requested,
        resolved_step_um=step,
        automatic_rule=AUTOMATIC_STEP_RULE,
        hausdorff_error_bound_um=step / 2.0,
    )


@dataclass(slots=True)
class DirectionalCurveDistances:
    """Distances from one graph's samples to the other graph, with the samples' length weights."""

    distances: np.ndarray
    weights: np.ndarray
    sampled_max_um: float

    @property
    def total_weight(self) -> float:
        return float(np.sum(self.weights, dtype=np.float64))


class SegmentDistanceIndex:
    """Exact nearest-segment distance queries against one set of segments.

    Segments are split into pieces no longer than ``piece_length_um`` (their
    union is the same set of points) and the piece midpoints go into a k-d
    tree. For a query point the nearest midpoint's piece gives an upper bound
    ``U`` on the distance; every piece that could be closer has its midpoint
    within ``U + half`` of the longest piece, so a ball query of that radius
    finds all candidates, and their exact point-to-segment distances are
    minimized.
    """

    def __init__(self, starts_um: np.ndarray, ends_um: np.ndarray, *, piece_length_um: float):
        if not len(starts_um):
            raise ValueError("SegmentDistanceIndex needs at least one segment.")
        lengths = np.linalg.norm(ends_um - starts_um, axis=1)
        pieces = np.maximum(1, np.ceil(lengths / piece_length_um)).astype(np.int64)
        segment = np.repeat(np.arange(len(starts_um)), pieces)
        offsets = np.concatenate([[0], np.cumsum(pieces)[:-1]])
        local = np.arange(int(pieces.sum())) - np.repeat(offsets, pieces)
        direction = ends_um - starts_um
        first = local / pieces[segment]
        second = (local + 1) / pieces[segment]
        self.starts = starts_um[segment] + first[:, None] * direction[segment]
        self.ends = starts_um[segment] + second[:, None] * direction[segment]
        self.ends[(local + 1) == pieces[segment]] = ends_um[segment[(local + 1) == pieces[segment]]]
        self.half_length = 0.5 * float(np.max(np.linalg.norm(self.ends - self.starts, axis=1)))
        self.tree = cKDTree(0.5 * (self.starts + self.ends))

    def distances(self, points: np.ndarray) -> np.ndarray:
        """Exact distance from each point (N, 3) to the nearest segment."""
        result = np.empty(len(points), dtype=float)
        for begin in range(0, len(points), SAMPLE_CHUNK):
            chunk = points[begin : begin + SAMPLE_CHUNK]
            result[begin : begin + len(chunk)] = self._chunk_distances(chunk)
        return result

    def _chunk_distances(self, points: np.ndarray) -> np.ndarray:
        _, nearest = self.tree.query(points)
        bound = point_segment_distances(points, self.starts[nearest], self.ends[nearest])
        radius = (bound + self.half_length) * (1.0 + 1e-12) + 1e-12
        candidates = self.tree.query_ball_point(points, radius, return_sorted=False)
        counts = np.fromiter((len(item) for item in candidates), dtype=np.int64, count=len(points))
        flat = np.fromiter((index for item in candidates for index in item), dtype=np.int64, count=int(counts.sum()))
        owner = np.repeat(np.arange(len(points)), counts)
        exact = point_segment_distances(points[owner], self.starts[flat], self.ends[flat])
        offsets = np.concatenate([[0], np.cumsum(counts)[:-1]])
        result = bound.copy()
        # The nearest midpoint always lies inside its own ball, so groups are nonempty; guard anyway.
        present = counts > 0
        if present.any():
            result[present] = np.minimum(bound[present], np.minimum.reduceat(exact, offsets[present]))
        return result


def point_segment_distances(points: np.ndarray, starts: np.ndarray, ends: np.ndarray) -> np.ndarray:
    """Row-wise Euclidean distance from ``points[i]`` to segment ``[starts[i], ends[i]]`` (positive length)."""
    direction = ends - starts
    offset = points - starts
    t = np.einsum("ij,ij->i", offset, direction) / np.einsum("ij,ij->i", direction, direction)
    np.clip(t, 0.0, 1.0, out=t)
    return np.linalg.norm(offset - t[:, None] * direction, axis=1)


def directional_curve_distances(
    starts_um: np.ndarray,
    ends_um: np.ndarray,
    target: SegmentDistanceIndex,
    step_um: float,
) -> DirectionalCurveDistances:
    """Sample one graph's segments and measure each sample's distance to ``target``.

    Midpoints are weighted by their interval length; boundaries (both ends of
    every interval, so every stored bend) only feed the maximum.
    """
    lengths = np.linalg.norm(ends_um - starts_um, axis=1)
    intervals = np.maximum(1, np.ceil(lengths / step_um)).astype(np.int64)
    weights_per_segment = lengths / intervals
    distances = np.empty(int(intervals.sum()), dtype=float)
    weights = np.repeat(weights_per_segment, intervals)
    sampled_max = 0.0
    for begin, chunk in _sample_chunks(starts_um, ends_um, intervals, midpoints=True):
        values = target.distances(chunk)
        distances[begin : begin + len(values)] = values
        sampled_max = max(sampled_max, float(values.max()))
    for _begin, chunk in _sample_chunks(starts_um, ends_um, intervals + 1, midpoints=False, intervals=intervals):
        sampled_max = max(sampled_max, float(target.distances(chunk).max()))
    return DirectionalCurveDistances(distances=distances, weights=weights, sampled_max_um=sampled_max)


def _sample_chunks(
    starts: np.ndarray,
    ends: np.ndarray,
    counts: np.ndarray,
    *,
    midpoints: bool,
    intervals: np.ndarray | None = None,
):
    """Yield ``(first global index, points)`` for samples in chunks of at most ``SAMPLE_CHUNK``.

    Midpoints: sample k of a segment sits at ``t = (k + 0.5) / n``. Boundaries:
    sample k sits at ``t = k / n`` for k = 0..n (``counts = n + 1``).
    """
    divisions = counts if intervals is None else intervals
    cumulative = np.cumsum(counts)
    total = int(cumulative[-1]) if len(cumulative) else 0
    first_of_segment = cumulative - counts
    direction = ends - starts
    for begin in range(0, total, SAMPLE_CHUNK):
        index = np.arange(begin, min(begin + SAMPLE_CHUNK, total), dtype=np.int64)
        segment = np.searchsorted(cumulative, index, side="right")
        local = index - first_of_segment[segment]
        t = (local + 0.5) / divisions[segment] if midpoints else local / divisions[segment]
        yield begin, starts[segment] + t[:, None] * direction[segment]


def length_coverage(
    spec: ToleranceSpec,
    pred_to_ref: DirectionalCurveDistances,
    ref_to_pred: DirectionalCurveDistances,
    spacing_um: Sequence[float],
) -> ToleranceMatch:
    """Length-weighted precision, recall and F1 at one tolerance for two graphs with curve geometry."""
    matched_pred, unmatched_pred = _split_length(pred_to_ref, spec.tolerance_um, spacing_um)
    matched_ref, unmatched_ref = _split_length(ref_to_pred, spec.tolerance_um, spacing_um)
    precision = matched_pred / pred_to_ref.total_weight
    recall = matched_ref / ref_to_pred.total_weight
    return length_match(
        spec,
        precision=precision,
        recall=recall,
        matched_pred=matched_pred,
        unmatched_pred=unmatched_pred,
        matched_ref=matched_ref,
        unmatched_ref=unmatched_ref,
    )


def length_match(
    spec: ToleranceSpec,
    *,
    precision: float,
    recall: float,
    matched_pred: float,
    unmatched_pred: float,
    matched_ref: float,
    unmatched_ref: float,
) -> ToleranceMatch:
    """A ``ToleranceMatch`` carrying curve lengths (µm) in place of voxel counts."""
    return ToleranceMatch(
        tolerance_um=spec.tolerance_um,
        requested_value=spec.requested_value,
        requested_unit=spec.requested_unit,
        is_primary=spec.is_primary,
        precision=float(precision),
        recall=float(recall),
        f1=f1_score(precision, recall),
        matched_prediction_length_um=float(matched_pred),
        unmatched_prediction_length_um=float(unmatched_pred),
        matched_reference_length_um=float(matched_ref),
        unmatched_reference_length_um=float(unmatched_ref),
    )


def summarize_curve_distances(
    pred_to_ref: DirectionalCurveDistances,
    ref_to_pred: DirectionalCurveDistances,
    sampling: GraphSamplingInfo,
) -> DistanceSummary:
    """Length-weighted means and P95s, and sampled maxima with the Hausdorff bound.

    Symmetric mean = the two directional means averaged; symmetric P95 = the
    larger directional P95. The sampled Hausdorff distance ``H_hat`` satisfies
    ``H_hat <= H <= H_hat + h / 2`` up to floating-point error.
    """
    mean_pr = weighted_mean(pred_to_ref.distances, pred_to_ref.weights)
    mean_rp = weighted_mean(ref_to_pred.distances, ref_to_pred.weights)
    p95_pr = weighted_percentile(pred_to_ref.distances, pred_to_ref.weights, PERCENTILE)
    p95_rp = weighted_percentile(ref_to_pred.distances, ref_to_pred.weights, PERCENTILE)
    hausdorff = max(pred_to_ref.sampled_max_um, ref_to_pred.sampled_max_um)
    bound = sampling.hausdorff_error_bound_um
    return DistanceSummary(
        mean_pred_to_ref_um=mean_pr,
        mean_ref_to_pred_um=mean_rp,
        symmetric_mean_um=(mean_pr + mean_rp) / 2.0,
        p95_pred_to_ref_um=p95_pr,
        p95_ref_to_pred_um=p95_rp,
        symmetric_p95_um=max(p95_pr, p95_rp),
        max_pred_to_ref_um=pred_to_ref.sampled_max_um,
        max_ref_to_pred_um=ref_to_pred.sampled_max_um,
        hausdorff_um=hausdorff,
        hausdorff_is_approximate=True,
        sampling_error_bound_um=bound,
        hausdorff_upper_bound_um=hausdorff + bound,
    )


def weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    """Σ wᵢ dᵢ / Σ wᵢ."""
    return float(np.sum(weights * values, dtype=np.float64) / np.sum(weights, dtype=np.float64))


def weighted_percentile(values: np.ndarray, weights: np.ndarray, percentile: float) -> float:
    """Inverse weighted empirical CDF: the smallest value whose cumulative weight fraction reaches ``percentile``."""
    order = np.argsort(values, kind="stable")
    cumulative = np.cumsum(weights[order], dtype=np.float64)
    target = (percentile / 100.0) * cumulative[-1]
    index = int(np.searchsorted(cumulative, target * (1.0 - PERCENTILE_FRACTION_SLACK), side="left"))
    return float(values[order][min(index, len(values) - 1)])


def _split_length(
    distances: DirectionalCurveDistances, tolerance_um: float, spacing_um: Sequence[float]
) -> tuple[float, float]:
    matched = within_tolerance(distances.distances, tolerance_um, spacing_um)
    return (
        float(np.sum(distances.weights[matched], dtype=np.float64)),
        float(np.sum(distances.weights[~matched], dtype=np.float64)),
    )
