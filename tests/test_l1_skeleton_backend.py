"""L1 skeleton backend tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import nibabel as nib
import numpy as np

from skelhub.algorithms.l1_skeleton import L1SkeletonConfig
from skelhub.core import SkeletonResult, VolumeData, get_backend, list_backends


REPO_ROOT = Path(__file__).resolve().parents[1]


def _tube() -> np.ndarray:
    volume = np.zeros((9, 9, 15), dtype=np.float32)
    volume[3:6, 3:6, 2:13] = 1.0
    return volume


def _y_branch() -> np.ndarray:
    volume = np.zeros((15, 15, 15), dtype=np.float32)
    volume[7, 7, 2:8] = 1.0
    for offset in range(6):
        volume[7 - offset, 7, 7 + offset] = 1.0
        volume[7 + offset, 7, 7 + offset] = 1.0
    return volume


def test_registry_exposes_l1_skeleton_backend() -> None:
    assert "l1_skeleton" in list_backends()
    assert get_backend("l1_skeleton").name == "l1_skeleton"


def test_l1_skeleton_config_validation_rejects_bad_values() -> None:
    for config in (
        L1SkeletonConfig(sample_count=0),
        L1SkeletonConfig(initial_radius=0.0),
        L1SkeletonConfig(radius_growth=1.0),
        L1SkeletonConfig(max_iterations=0),
        L1SkeletonConfig(branch_threshold=1.1),
    ):
        try:
            config.validate()
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected {config!r} to fail validation.")


def test_l1_skeleton_empty_foreground_returns_warning() -> None:
    data = np.zeros((5, 5, 5), dtype=np.float32)
    volume = VolumeData(data=data, affine=np.eye(4), header=None, path="memory", spacing=(1.0, 1.0, 1.0))

    result = get_backend("l1_skeleton").run(volume=volume, config=L1SkeletonConfig())

    assert isinstance(result, SkeletonResult)
    assert result.algorithm_name == "l1_skeleton"
    assert result.skeleton.shape == data.shape
    assert result.skeleton.dtype == np.uint8
    assert int(np.count_nonzero(result.skeleton)) == 0
    assert result.warnings
    assert result.backend_metadata["l1_skeleton"]["input_foreground_voxels"] == 0


def test_l1_skeleton_rejects_non_3d_input() -> None:
    volume = VolumeData(data=np.zeros((5, 5), dtype=np.float32), affine=np.eye(4), header=None)

    try:
        get_backend("l1_skeleton").run(volume=volume, config=L1SkeletonConfig())
    except ValueError:
        pass
    else:
        raise AssertionError("Expected l1_skeleton to reject non-3D input.")


def test_l1_skeleton_backend_returns_centered_binary_tube_skeleton() -> None:
    data = _tube()
    volume = VolumeData(data=data, affine=np.eye(4), header=None, path="memory", spacing=(1.0, 1.0, 1.0))
    config = L1SkeletonConfig(
        sample_count=80,
        initial_radius=2.0,
        max_radius=4.0,
        max_iterations=20,
        stop_error=0.02,
    )

    result = get_backend("l1_skeleton").run(volume=volume, config=config)
    voxels = np.argwhere(result.skeleton > 0)

    assert isinstance(result, SkeletonResult)
    assert result.skeleton.shape == data.shape
    assert result.skeleton.dtype == np.uint8
    assert set(np.unique(result.skeleton)).issubset({0, 1})
    assert len(voxels) > 0
    assert abs(float(np.mean(voxels[:, 0])) - 4.0) <= 1.5
    assert abs(float(np.mean(voxels[:, 1])) - 4.0) <= 1.5
    assert result.graph is not None
    assert result.backend_metadata["l1_skeleton"]["graph_nodes"] > 0


def test_l1_skeleton_y_branch_has_multiple_edges() -> None:
    data = _y_branch()
    volume = VolumeData(data=data, affine=np.eye(4), header=None, path="memory", spacing=(1.0, 1.0, 1.0))
    config = L1SkeletonConfig(
        sample_count=32,
        initial_radius=2.0,
        max_radius=5.0,
        max_iterations=18,
        branch_threshold=0.5,
    )

    result = get_backend("l1_skeleton").run(volume=volume, config=config)

    assert np.count_nonzero(result.skeleton) > 0
    assert result.graph is not None
    assert len(result.graph.edges) >= 2
    assert result.backend_metadata["l1_skeleton"]["graph_edges"] >= 2


def test_framework_run_cli_executes_l1_skeleton_and_writes_graphml(tmp_path: Path) -> None:
    input_path = tmp_path / "input.nii.gz"
    output_path = tmp_path / "out.nii.gz"
    graph_path = tmp_path / "out.graphml"
    nib.save(nib.Nifti1Image(_tube(), affine=np.eye(4)), str(input_path))

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "skelhub",
            "run",
            "--algorithm",
            "l1_skeleton",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--l1-sample-count",
            "80",
            "--l1-initial-radius",
            "2.0",
            "--l1-max-radius",
            "4.0",
            "--l1-max-iterations",
            "20",
            "--l1-graph-output",
            str(graph_path),
            "--verbose",
        ],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    out = np.asarray(nib.load(str(output_path)).dataobj)
    assert output_path.exists()
    assert graph_path.exists()
    assert np.count_nonzero(out) > 0
    assert "framework run complete: algorithm=l1_skeleton" in result.stdout
