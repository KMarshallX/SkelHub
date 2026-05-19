"""Milestone 5 and 6 tests for dilation, significance, and full skeleton extraction."""

from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np

from skelhub.algorithms.mcp.dilation import local_scale_adaptive_dilation
from skelhub.algorithms.mcp.distance_transform import compute_fdt
from skelhub.algorithms.mcp.skeleton import extract_skeleton, significance
from tests import FIXTURES_DIR, save_skeleton_visualization


STRAIGHT_TUBE_PATH = FIXTURES_DIR / "straight_tube.nii.gz"
Y_TUBE_PATH = FIXTURES_DIR / "y_tube.nii.gz"
Y_TUBE_NOISY_PATH = FIXTURES_DIR / "y_tube_noisy.nii.gz"


def _load_fixture(path: Path) -> np.ndarray:
    """Load a fixture as float32."""
    return np.asarray(nib.load(str(path)).dataobj, dtype=np.float32)


def test_local_scale_adaptive_dilation_covers_straight_tube_cross_sections() -> None:
    """Centreline dilation should recover nearly the full straight-tube support."""
    volume = _load_fixture(STRAIGHT_TUBE_PATH)
    object_mask = volume > 0.0
    fdt = compute_fdt(volume)

    branch_coords = [(z, 10, 30) for z in range(volume.shape[0])]
    dilated = local_scale_adaptive_dilation(object_mask, branch_coords, fdt)

    assert dilated.shape == object_mask.shape
    assert np.all(dilated <= object_mask)

    overall_coverage = np.count_nonzero(dilated & object_mask) / np.count_nonzero(object_mask)
    assert overall_coverage >= 0.98

    centre_slice = volume.shape[0] // 2
    slice_object = object_mask[centre_slice]
    slice_dilated = dilated[centre_slice]
    slice_coverage = np.count_nonzero(slice_dilated & slice_object) / np.count_nonzero(slice_object)
    assert slice_coverage >= 0.95

    expected_cross_section = int(np.count_nonzero(slice_object))
    assert abs(int(np.count_nonzero(slice_dilated)) - expected_cross_section) <= 2


def test_significance_sums_only_unmarked_branch_voxels() -> None:
    """Significance should ignore branch voxels already covered by O_marked."""
    lsf = np.zeros((3, 3, 5), dtype=np.float32)
    branch_coords = [(1, 1, x) for x in range(5)]
    values = [0.2, 0.5, 0.8, 0.3, 0.4]
    for coord, value in zip(branch_coords, values, strict=True):
        lsf[coord] = value

    marked_mask = np.zeros_like(lsf, dtype=bool)
    marked_mask[1, 1, 0] = True
    marked_mask[1, 1, 2] = True

    result = significance(branch_coords, lsf, marked_mask)

    assert np.isclose(result, 0.5 + 0.3 + 0.4)


def _count_false_branches(
    endpoints: list[tuple[int, int, int]],
    expected_endpoints: list[tuple[int, int, int]],
    tolerance: float = 3.5,
) -> int:
    """Count unexpected endpoints after greedy matching to the expected branch termini."""
    unmatched = endpoints.copy()
    for expected in expected_endpoints:
        if not unmatched:
            break
        distances = [
            float(np.linalg.norm(np.asarray(endpoint, dtype=np.float32) - np.asarray(expected, dtype=np.float32)))
            for endpoint in unmatched
        ]
        best_index = int(np.argmin(distances))
        if distances[best_index] <= tolerance:
            unmatched.pop(best_index)
    return len(unmatched)


def test_y_tube_end_to_end_skeleton_has_three_branches_and_no_false_branches() -> None:
    """The clean Y-tube should yield the expected three-branch skeleton."""
    volume = _load_fixture(Y_TUBE_PATH)
    skeleton, metadata = extract_skeleton(volume)

    branch_count = int(metadata["branch_count"])
    endpoints = list(metadata["endpoints"])
    false_branches = _count_false_branches(
        endpoints,
        [(0, 20, 20), (30, 20, 39), (30, 39, 20)],
    )

    save_skeleton_visualization(volume, skeleton, "y_tube_overlay.png", "Milestone 6: Y-tube")

    assert branch_count == 3
    assert len(endpoints) == 3
    assert false_branches == 0


def test_noisy_y_tube_end_to_end_skeleton_still_has_three_branches_and_no_false_branches() -> None:
    """Boundary noise should not introduce extra branches into the Y-tube skeleton."""
    volume = _load_fixture(Y_TUBE_NOISY_PATH)
    skeleton, metadata = extract_skeleton(volume)

    branch_count = int(metadata["branch_count"])
    endpoints = list(metadata["endpoints"])
    false_branches = _count_false_branches(
        endpoints,
        [(0, 20, 20), (30, 20, 39), (30, 39, 20)],
    )

    save_skeleton_visualization(
        volume,
        skeleton,
        "y_tube_noisy_overlay.png",
        "Milestone 6: noisy Y-tube",
    )

    assert branch_count == 3
    assert len(endpoints) == 3
    assert false_branches == 0


def test_extract_skeleton_respects_max_iterations_cap_and_reports_per_iteration_counts() -> None:
    """The outer loop should stop cleanly at the configured iteration cap."""
    volume = _load_fixture(Y_TUBE_PATH)

    skeleton, metadata = extract_skeleton(volume, max_iterations=1)

    assert np.count_nonzero(skeleton) > 0
    assert metadata["iterations"] == 1
    assert metadata["max_iterations_reached"] is True
    assert metadata["branches_added_per_iteration"] == [1]
    assert metadata["geodesic_calls"] == 1
    assert metadata["minimum_cost_path_calls"] >= 1
