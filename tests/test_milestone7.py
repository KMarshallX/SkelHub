"""Milestone 7 validation and reporting tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import nibabel as nib
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_main_cli_verbose_reports_iteration_and_summary_details(tmp_path: Path) -> None:
    """Verbose CLI output should expose per-object iteration and runtime summaries."""
    in_path = tmp_path / "input.nii.gz"
    out_path = tmp_path / "nested" / "out.nii.gz"

    arr = np.zeros((12, 12, 12), dtype=np.uint8)
    arr[3:9, 3:9, 3:9] = 1
    nib.save(nib.Nifti1Image(arr, affine=np.eye(4)), str(in_path))

    result = subprocess.run(
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
            "--verbose",
            "--max-iterations",
            "2",
            "--min-object-size",
            "1",
        ],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    stdout = result.stdout
    assert out_path.exists()
    assert "object 1/1 (label=1):" in stdout
    assert "branches_added_per_iteration=" in stdout
    assert "time=" in stdout
    assert "final summary:" in stdout
    assert "average_iterations_per_object=" in stdout


def test_main_cli_verbose_reports_when_iteration_cap_is_hit(tmp_path: Path) -> None:
    """Verbose mode should make iteration-cap exits explicit."""
    in_path = tmp_path / "input.nii.gz"
    out_path = tmp_path / "out.nii.gz"

    arr = np.zeros((40, 40, 60), dtype=np.uint8)
    arr[18:23, 18:23, 5:55] = 1
    arr[18:23, 18:35, 40:45] = 1
    arr[18:35, 18:23, 40:45] = 1
    nib.save(nib.Nifti1Image(arr, affine=np.eye(4)), str(in_path))

    result = subprocess.run(
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
            "--verbose",
            "--max-iterations",
            "1",
            "--min-object-size",
            "1",
        ],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    stdout = result.stdout
    assert out_path.exists()
    assert "maximum iteration cap reached (1); stopping object safely" in stdout
