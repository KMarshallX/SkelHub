"""Centreline samples used for foreground assignment and radius measurement."""

from __future__ import annotations

import math

import numpy as np

from .models import FeatureGraph

DEFAULT_SAMPLING_STEP = 1.0

# Guards ceil(L / step) against round-off, e.g. 2.4 / 0.8 evaluating just above 3.
_STEP_COUNT_TOLERANCE = 1e-9


def validate_sampling_step(step: float) -> float:
    """Return ``step`` as a float, rejecting values that are not finite and positive."""
    try:
        value = float(step)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Sampling step must be a number of voxels, got {step!r}.") from exc
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"Sampling step must be a finite number of voxels greater than 0, got {step!r}.")
    return value


def sample_polyline(points: np.ndarray, step: float) -> np.ndarray:
    """Split each straight piece of a polyline evenly into sub-pieces no longer than ``step``.

    A piece of length L becomes ceil(L / step) equal sub-pieces. Every stored
    point is kept, added points lie on the straight piece between two stored
    points, and repeated consecutive points are dropped.
    """
    points = np.asarray(points, dtype=float)
    samples = [points[0]]
    for start, end in zip(points[:-1], points[1:]):
        length = float(np.linalg.norm(end - start))
        if length == 0.0:
            continue
        pieces = max(1, math.ceil(length / step - _STEP_COUNT_TOLERANCE))
        for index in range(1, pieces):
            samples.append(start + (end - start) * (index / pieces))
        samples.append(end)
    return np.asarray(samples, dtype=float)


def edge_samples(graph: FeatureGraph, step: float | None) -> list[np.ndarray]:
    """Return per-edge voxel-space samples in ``graph.edges`` order.

    ``centerline_voxel_points`` paths are sampled with :func:`sample_polyline`
    (``step`` defaults to :data:`DEFAULT_SAMPLING_STEP`). ``centerline_voxels``
    paths are used as stored, one sample per voxel.
    """
    if not graph.uses_centerline_points:
        return [edge.path for edge in graph.edges]
    resolved = DEFAULT_SAMPLING_STEP if step is None else validate_sampling_step(step)
    return [sample_polyline(edge.path, resolved) for edge in graph.edges]
