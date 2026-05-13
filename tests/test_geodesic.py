"""Milestone 3 tests for geodesic distance."""

from __future__ import annotations

import math

import numpy as np

from skelhub.algorithms.mcp.geodesic import compute_geodesic_distance


def test_geodesic_distance_is_zero_at_source_voxels() -> None:
    """Source voxels should start at zero distance."""
    object_mask = np.zeros((5, 5, 5), dtype=bool)
    object_mask[2, 2, 1:4] = True
    source_mask = np.zeros_like(object_mask)
    source_mask[2, 2, 1] = True

    distance = compute_geodesic_distance(object_mask, source_mask)

    assert distance[2, 2, 1] == 0.0


def test_geodesic_distance_increases_along_object_paths() -> None:
    """Distances should grow with accumulated Euclidean step length inside the object."""
    object_mask = np.zeros((5, 5, 5), dtype=bool)
    object_mask[2, 2, 1:4] = True
    object_mask[2, 3, 3] = True
    source_mask = np.zeros_like(object_mask)
    source_mask[2, 2, 1] = True

    distance = compute_geodesic_distance(object_mask, source_mask)

    assert distance[2, 2, 2] > distance[2, 2, 1]
    assert distance[2, 2, 3] > distance[2, 2, 2]
    assert math.isclose(float(distance[2, 3, 3]), 1.0 + math.sqrt(2.0), rel_tol=1e-6)


def test_geodesic_distance_is_infinite_outside_object_support() -> None:
    """Exterior voxels should remain infinite."""
    object_mask = np.zeros((5, 5, 5), dtype=bool)
    object_mask[2, 2, 1:4] = True
    source_mask = np.zeros_like(object_mask)
    source_mask[2, 2, 1] = True

    distance = compute_geodesic_distance(object_mask, source_mask)

    assert np.isinf(distance[0, 0, 0])
    assert np.isinf(distance[4, 4, 4])


def test_geodesic_distance_preserves_inf_for_disconnected_regions() -> None:
    """Disconnected object regions should remain unreachable from the source set."""
    object_mask = np.zeros((7, 7, 7), dtype=bool)
    object_mask[3, 3, 1:4] = True
    object_mask[5, 5, 5] = True
    source_mask = np.zeros_like(object_mask)
    source_mask[3, 3, 1] = True

    distance = compute_geodesic_distance(object_mask, source_mask)

    assert np.isfinite(distance[3, 3, 3])
    assert np.isinf(distance[5, 5, 5])
