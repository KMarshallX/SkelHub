"""Milestone 3 tests for local significance factor."""

from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np

from skelhub.algorithms.mcp.distance_transform import compute_fdt
from skelhub.algorithms.mcp.lsf import compute_lsf
from skelhub.algorithms.mcp.maximal_balls import compute_fcmb_mask
from tests import FIXTURES_DIR


STRAIGHT_TUBE_PATH = FIXTURES_DIR / "straight_tube.nii.gz"
FUZZY_STRAIGHT_TUBE_PATH = FIXTURES_DIR / "fuzzy_straight_tube.nii.gz"


def _load_fixture(path: Path) -> np.ndarray:
    """Load a fixture as float32."""
    return np.asarray(nib.load(str(path)).dataobj, dtype=np.float32)


def test_compute_lsf_is_zero_outside_fcmb_set() -> None:
    """Non-fCMB voxels should have LSF equal to zero."""
    volume = _load_fixture(STRAIGHT_TUBE_PATH)
    fdt = compute_fdt(volume)
    fcmb_mask = compute_fcmb_mask(volume, fdt)
    lsf = compute_lsf(volume, fdt)

    assert lsf.shape == volume.shape
    assert np.all(lsf[~fcmb_mask] == 0.0)
    assert np.all(lsf[volume == 0] == 0.0)


def test_compute_lsf_produces_positive_values_on_fcmb_voxels() -> None:
    """fCMB voxels should retain strictly positive LSF values in the valid range."""
    volume = _load_fixture(STRAIGHT_TUBE_PATH)
    fdt = compute_fdt(volume)
    fcmb_mask = compute_fcmb_mask(volume, fdt)
    lsf = compute_lsf(volume, fdt)

    assert np.any(fcmb_mask)
    assert np.all(lsf[fcmb_mask] > 0.0)
    assert np.all(lsf[fcmb_mask] <= 1.0)


def test_compute_lsf_identifies_strong_quench_voxels_in_fuzzy_tube() -> None:
    """Strong quench voxels should be recoverable via the LSF > 0.5 criterion."""
    volume = _load_fixture(FUZZY_STRAIGHT_TUBE_PATH)
    fdt = compute_fdt(volume)
    lsf = compute_lsf(volume, fdt)

    strong_quench = lsf > 0.5
    centreline = volume[:, 10, 30] > 0

    assert np.any(strong_quench)
    assert np.all(lsf[strong_quench] > 0.5)
    assert np.count_nonzero(strong_quench[:, 10, 30]) >= int(0.8 * np.count_nonzero(centreline))
