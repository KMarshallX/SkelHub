"""Milestone 2 tests for the distance transform."""

from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np

from skelhub.algorithms.mcp.distance_transform import compute_fdt
from skelhub.algorithms.mcp.maximal_balls import compute_fcmb_mask
from tests import FIXTURES_DIR, save_tube_visualization


STRAIGHT_TUBE_PATH = FIXTURES_DIR / "straight_tube.nii.gz"
FUZZY_STRAIGHT_TUBE_PATH = FIXTURES_DIR / "fuzzy_straight_tube.nii.gz"


def _load_fixture(path: Path) -> np.ndarray:
    """Load a fixture as float32."""
    return np.asarray(nib.load(str(path)).dataobj, dtype=np.float32)


def test_compute_fdt_peaks_on_straight_tube_centreline() -> None:
    """FDT maxima should lie on the synthetic tube centreline."""
    volume = _load_fixture(STRAIGHT_TUBE_PATH)

    fdt = compute_fdt(volume)
    peak_coords = np.argwhere(fdt == fdt.max())

    assert fdt.shape == volume.shape
    assert np.all(fdt[volume == 0] == 0.0)
    assert fdt.max() > 0.0
    assert peak_coords.shape[0] == volume.shape[0]
    assert np.all(peak_coords[:, 1] == 10)
    assert np.all(peak_coords[:, 2] == 30)


def test_compute_fdt_supports_fuzzy_memberships_on_matched_geometry() -> None:
    """Fuzzy FDT should differ from binary EDT while preserving structure."""
    binary_volume = _load_fixture(STRAIGHT_TUBE_PATH)
    fuzzy_volume = _load_fixture(FUZZY_STRAIGHT_TUBE_PATH)

    binary_fdt = compute_fdt(binary_volume)
    fuzzy_fdt = compute_fdt(fuzzy_volume)

    centreline = (slice(None), 10, 30)
    boundary_shell = (fuzzy_volume.shape[0] // 2, 10, 33)
    fuzzy_peak_coords = np.argwhere(fuzzy_fdt == fuzzy_fdt.max())

    assert fuzzy_fdt.shape == fuzzy_volume.shape
    assert np.all(fuzzy_fdt[fuzzy_volume == 0] == 0.0)
    assert np.array_equal(fuzzy_volume > 0, binary_volume > 0)
    assert fuzzy_fdt.max() > 0.0
    assert not np.allclose(fuzzy_fdt, binary_fdt)
    assert np.all(fuzzy_peak_coords[:, 1] == 10)
    assert np.all(fuzzy_peak_coords[:, 2] == 30)
    assert float(np.mean(fuzzy_fdt[centreline])) < float(np.mean(binary_fdt[centreline]))
    assert fuzzy_fdt[boundary_shell] < fuzzy_fdt[fuzzy_volume.shape[0] // 2, 10, 30]


def test_distance_transform_visualization_artifact_is_saved() -> None:
    """Milestone 2 should save a non-interactive FDT visualization for inspection."""
    volume = _load_fixture(STRAIGHT_TUBE_PATH)
    fdt = compute_fdt(volume)
    fcmb_mask = compute_fcmb_mask(volume, fdt)

    artifact_path = save_tube_visualization(
        volume=volume,
        fdt=fdt,
        fcmb_mask=fcmb_mask,
        output_name="straight_tube_distance_transform.png",
    )

    assert artifact_path.exists()
    assert artifact_path.stat().st_size > 0


def test_fixture_generator_writes_fuzzy_counterparts() -> None:
    """Fuzzy fixture counterparts should be present for matched-shape testing."""
    assert FUZZY_STRAIGHT_TUBE_PATH.exists()
    assert (FIXTURES_DIR / "fuzzy_y_tube.nii.gz").exists()
