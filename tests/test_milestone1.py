"""Milestone 1 acceptance-oriented tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import cast

import nibabel as nib
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SCRIPT = REPO_ROOT / "tests" / "fixtures" / "generate_fixtures.py"


def test_fixture_generation_script_runs(tmp_path: Path) -> None:
    """Fixture generation script should run and create all expected files."""
    env = dict()
    env.update(**{"PYTHONPATH": str(REPO_ROOT)})
    subprocess.run([sys.executable, str(FIXTURE_SCRIPT)], check=True, cwd=REPO_ROOT)

    expected = [
        REPO_ROOT / "tests" / "fixtures" / "straight_tube.nii.gz",
        REPO_ROOT / "tests" / "fixtures" / "y_tube.nii.gz",
        REPO_ROOT / "tests" / "fixtures" / "y_tube_noisy.nii.gz",
        REPO_ROOT / "tests" / "fixtures" / "two_tubes.nii.gz",
        REPO_ROOT / "tests" / "fixtures" / "fuzzy_straight_tube.nii.gz",
        REPO_ROOT / "tests" / "fixtures" / "fuzzy_y_tube.nii.gz",
    ]
    for file_path in expected:
        assert file_path.exists(), f"Missing fixture: {file_path}"


def test_main_cli_produces_a_valid_skeleton_volume(tmp_path: Path) -> None:
    """CLI should skeletonize a simple binary object without leaving the input support."""
    in_path = tmp_path / "input.nii.gz"
    out_path = tmp_path / "out.nii.gz"

    arr = np.zeros((12, 12, 12), dtype=np.uint8)
    arr[3:9, 3:9, 3:9] = 1
    nib.save(nib.Nifti1Image(arr, affine=np.eye(4)), str(in_path))

    subprocess.run(
        [
            sys.executable,
            "-m",
            "skelhub",
            "run",
            "--algorithm",
            "mcp",
            "-i",
            str(in_path),
            "-o",
            str(out_path),
        ],
        check=True,
        cwd=REPO_ROOT,
    )

    assert out_path.exists()
    out_img = cast(nib.Nifti1Image, nib.load(str(out_path)))
    out_data = out_img.get_fdata(dtype=np.float32)
    assert out_data.shape == arr.shape
    assert np.count_nonzero(out_data) > 0
    assert np.all((out_data > 0) <= arr.astype(bool))
