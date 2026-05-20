"""Milestone 4 tests for minimum-cost path extraction."""

from __future__ import annotations

import math

import numpy as np

from skelhub.algorithms.mcp.path_cost import minimum_cost_path


def _build_straight_tube(
    shape: tuple[int, int, int] = (9, 15, 25),
    center: tuple[int, int] = (7, 4),
    radius: float = 3.0,
) -> tuple[np.ndarray, list[tuple[int, int, int]]]:
    """Create a straight tube along x with its geometric centreline."""
    z, y, x = np.indices(shape)
    center_y, center_z = center
    radial = np.sqrt((y - center_y) ** 2 + (z - center_z) ** 2)
    object_mask = radial <= radius
    centreline = [(center_z, center_y, ix) for ix in range(shape[2])]
    return object_mask, centreline


def _build_l_shaped_tube(
    shape: tuple[int, int, int] = (9, 25, 25),
    z_center: int = 4,
    y_center: int = 7,
    bend_x: int = 12,
    y_end: int = 20,
    radius: float = 3.0,
) -> tuple[np.ndarray, list[tuple[int, int, int]]]:
    """Create an L-shaped tube with a known centreline through a sharp bend."""
    z, y, x = np.indices(shape)
    horizontal = (np.abs(z - z_center) ** 2 + np.abs(y - y_center) ** 2 <= radius**2) & (x <= bend_x)
    vertical = (np.abs(z - z_center) ** 2 + np.abs(x - bend_x) ** 2 <= radius**2) & (y >= y_center)
    object_mask = horizontal | vertical

    centreline = [(z_center, y_center, ix) for ix in range(bend_x + 1)]
    centreline.extend((z_center, iy, bend_x) for iy in range(y_center + 1, y_end + 1))
    return object_mask, centreline


def _lsf_from_centreline(
    object_mask: np.ndarray,
    centreline: list[tuple[int, int, int]],
    sigma: float = 1.0,
    floor: float = 0.05,
) -> np.ndarray:
    """Create an LSF field that peaks at the provided centreline and decays outward."""
    lsf = np.zeros(object_mask.shape, dtype=np.float32)
    centreline_array = np.asarray(centreline, dtype=np.float32)

    for coord in np.argwhere(object_mask):
        squared_distance = np.min(np.sum((centreline_array - coord.astype(np.float32)) ** 2, axis=1))
        value = floor + (1.0 - floor) * math.exp(-0.5 * squared_distance / sigma**2)
        lsf[tuple(int(v) for v in coord)] = float(value)

    return lsf


def _assert_path_is_26_connected(path: list[tuple[int, int, int]]) -> None:
    """Verify that consecutive path voxels use valid 26-neighbour steps."""
    for current, following in zip(path[:-1], path[1:]):
        delta = np.abs(np.subtract(current, following))
        assert np.all(delta <= 1)
        assert np.any(delta > 0)


def _assert_path_inside_object(path: list[tuple[int, int, int]], object_mask: np.ndarray) -> None:
    """Verify that every path voxel stays inside the object support."""
    assert path
    for voxel in path:
        assert object_mask[voxel]


def _max_distance_to_polyline(path: list[tuple[int, int, int]], centreline: list[tuple[int, int, int]]) -> float:
    """Return the largest Euclidean distance from the path to the expected centreline."""
    centreline_array = np.asarray(centreline, dtype=np.float32)
    distances = []
    for voxel in path:
        squared = np.sum((centreline_array - np.asarray(voxel, dtype=np.float32)) ** 2, axis=1)
        distances.append(float(np.sqrt(np.min(squared))))
    return max(distances)


def test_minimum_cost_path_follows_straight_tube_centreline_within_one_voxel() -> None:
    """The path should stay on the medial route of a straight synthetic tube."""
    object_mask, centreline = _build_straight_tube()
    lsf = _lsf_from_centreline(object_mask, centreline, sigma=1.0)

    source_coords = [(4, 7, 0), (4, 7, 1)]
    target_coord = (4, 7, 24)

    path = minimum_cost_path(object_mask, lsf, source_coords, target_coord)

    _assert_path_inside_object(path, object_mask)
    _assert_path_is_26_connected(path)
    assert path[0] == target_coord
    assert path[-1] in set(source_coords)
    assert _max_distance_to_polyline(path, centreline) <= 1.0


def test_minimum_cost_path_follows_expected_medial_route_around_sharp_corner() -> None:
    """The path should track the centreline around an L-bend instead of hugging the inner wall."""
    object_mask, centreline = _build_l_shaped_tube()
    lsf = _lsf_from_centreline(object_mask, centreline, sigma=1.0)

    source_coords = [(4, 7, 0), (4, 7, 1), (4, 7, 2)]
    target_coord = (4, 20, 12)

    path = minimum_cost_path(object_mask, lsf, source_coords, target_coord)

    _assert_path_inside_object(path, object_mask)
    _assert_path_is_26_connected(path)
    assert path[0] == target_coord
    assert path[-1] in set(source_coords)
    assert any(voxel[0] == 4 and voxel[1] in (7, 8) and voxel[2] in (11, 12) for voxel in path)
    assert _max_distance_to_polyline(path, centreline) <= 1.5


def test_minimum_cost_path_returns_singleton_when_target_is_already_a_source() -> None:
    """If the target is already part of the skeleton, the path is that voxel alone."""
    object_mask, centreline = _build_straight_tube()
    lsf = _lsf_from_centreline(object_mask, centreline)

    target_coord = (4, 7, 10)
    path = minimum_cost_path(object_mask, lsf, [target_coord, (4, 7, 0)], target_coord)

    assert path == [target_coord]


def test_minimum_cost_path_returns_empty_for_disconnected_target_region() -> None:
    """Disconnected object regions should not produce a path."""
    object_mask = np.zeros((7, 7, 7), dtype=bool)
    object_mask[3, 3, 0:3] = True
    object_mask[3, 3, 5:7] = True
    lsf = np.zeros_like(object_mask, dtype=np.float32)
    lsf[object_mask] = 1.0

    path = minimum_cost_path(object_mask, lsf, [(3, 3, 0)], (3, 3, 6))

    assert path == []
