"""Framework CLI smoke tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import nibabel as nib
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_framework_run_cli_executes_mcp_path(tmp_path: Path) -> None:
    """`python -m skelhub run --algorithm mcp` should execute successfully."""
    input_path = tmp_path / "input.nii.gz"
    output_path = tmp_path / "out.nii.gz"

    arr = np.zeros((12, 12, 20), dtype=np.uint8)
    arr[4:8, 4:8, 3:17] = 1
    nib.save(nib.Nifti1Image(arr, affine=np.eye(4)), str(input_path))

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "skelhub",
            "run",
            "--algorithm",
            "mcp",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--min-object-size",
            "1",
            "--verbose",
        ],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    out = np.asarray(nib.load(str(output_path)).dataobj)
    assert output_path.exists()
    assert np.count_nonzero(out) > 0
    assert "framework run complete: algorithm=mcp" in result.stdout


def test_framework_run_cli_lists_lee94_choice() -> None:
    """The unified CLI help should advertise lee94 as a supported algorithm."""
    result = subprocess.run(
        [sys.executable, "-m", "skelhub", "run", "--help"],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert "lee94" in result.stdout


def test_framework_graphviz_cli_help_lists_graphviz_options() -> None:
    """The graph visualization CLI help should expose the new command options."""
    result = subprocess.run(
        [sys.executable, "-m", "skelhub", "graphviz", "--help"],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert "usage: skelhub graphviz [-h] [-i INPUT]" in result.stdout
    assert "--edge_thickness" in result.stdout
    assert "--node_size" in result.stdout


def test_framework_graphviz_cli_reports_missing_coordinates(tmp_path: Path) -> None:
    """The graph viewer CLI should fail clearly for GraphML without 3D coordinates."""
    graph_path = tmp_path / "missing_coords.graphml"
    graph_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <graph id="G" edgedefault="undirected">
    <node id="n0"/>
    <node id="n1"/>
    <edge id="e0" source="n0" target="n1"/>
  </graph>
</graphml>
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-m", "skelhub", "graphviz", "--input", str(graph_path)],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Expected node attributes 'X', 'Y', 'Z'" in result.stderr
