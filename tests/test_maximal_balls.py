"""Milestone 2 tests for fuzzy centers of maximal balls."""

from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np

from skelhub.algorithms.mcp.distance_transform import compute_fdt
from skelhub.algorithms.mcp.maximal_balls import compute_fcmb_mask
from tests import FIXTURES_DIR, save_tube_visualization


STRAIGHT_TUBE_PATH = FIXTURES_DIR / "straight_tube.nii.gz"


def _load_fixture(path: Path) -> np.ndarray:
    """Load a fixture as float32."""
    return np.asarray(nib.load(str(path)).dataobj, dtype=np.float32)


def test_compute_fcmb_mask_stays_on_or_near_straight_tube_centreline() -> None:
    """fCMB voxels should remain concentrated around the expected centreline."""
    volume = _load_fixture(STRAIGHT_TUBE_PATH)
    fdt = compute_fdt(volume)
    fcmb_mask = compute_fcmb_mask(volume, fdt)

    fcmb_coords = np.argwhere(fcmb_mask)
    radial_distance = np.sqrt((fcmb_coords[:, 1] - 10) ** 2 + (fcmb_coords[:, 2] - 30) ** 2)
    centreline_coords = np.argwhere(fdt == fdt.max())

    assert fcmb_mask.shape == volume.shape
    assert np.all(fcmb_mask <= (volume > 0))
    assert fcmb_coords.shape[0] > 0
    assert np.all(fcmb_mask[centreline_coords[:, 0], centreline_coords[:, 1], centreline_coords[:, 2]])
    assert np.max(radial_distance) <= 3.0
    assert np.all(np.bincount(fcmb_coords[:, 0], minlength=volume.shape[0]) > 0)


def test_maximal_balls_visualization_artifact_is_saved() -> None:
    """Milestone 2 should save a non-interactive fCMB visualization for inspection."""
    volume = _load_fixture(STRAIGHT_TUBE_PATH)
    fdt = compute_fdt(volume)
    fcmb_mask = compute_fcmb_mask(volume, fdt)

    artifact_path = save_tube_visualization(
        volume=volume,
        fdt=fdt,
        fcmb_mask=fcmb_mask,
        output_name="straight_tube_maximal_balls.png",
    )

    assert artifact_path.exists()
    assert artifact_path.stat().st_size > 0
