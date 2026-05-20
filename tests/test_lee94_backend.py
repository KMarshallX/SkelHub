"""Lee94 backend tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import nibabel as nib
import numpy as np

from skelhub.algorithms.lee94 import Lee94Config
from skelhub.api import run_algorithm_from_path
from skelhub.core import SkeletonResult, VolumeData, get_backend, list_backends


REPO_ROOT = Path(__file__).resolve().parents[1]
SMALL_DATA = REPO_ROOT / "test_data" / "small_test_data" / "CLIP_MASKED_sub_160um_seg.nii.gz"


def test_registry_exposes_lee94_backend() -> None:
    """The framework registry should expose the Lee94 backend."""
    assert "lee94" in list_backends()
    assert get_backend("lee94").name == "lee94"
    assert "mcp" in list_backends()


def test_lee94_config_validation_rejects_bad_threshold() -> None:
    """The Lee94 config should validate threshold bounds clearly."""
    try:
        Lee94Config(binarize_threshold=-0.1).validate()
    except ValueError:
        pass
    else:
        raise AssertionError("Expected Lee94Config to reject negative thresholds.")


def test_lee94_backend_returns_framework_result() -> None:
    """The Lee94 backend should return a standard SkeletonResult."""
    image = nib.load(str(SMALL_DATA))
    data = np.asarray(image.dataobj, dtype=np.float32)
    zooms = tuple(float(v) for v in image.header.get_zooms()[:3])
    volume = VolumeData(
        data=data,
        affine=image.affine.copy(),
        header=image.header.copy(),
        path=str(SMALL_DATA),
        spacing=zooms if len(zooms) == 3 else None,
    )

    result = get_backend("lee94").run(volume=volume, config=Lee94Config().validate())

    assert isinstance(result, SkeletonResult)
    assert result.algorithm_name == "lee94"
    assert result.skeleton.shape == data.shape
    assert np.count_nonzero(result.skeleton) > 0
    assert "lee94" in result.backend_metadata
    assert "implementation" in result.backend_metadata["lee94"]


def test_run_algorithm_from_path_executes_lee94_on_small_dataset(tmp_path: Path) -> None:
    """Framework API should execute the Lee94 backend through the shared run path."""
    output_path = tmp_path / "lee94_small.nii.gz"
    result = run_algorithm_from_path(
        algorithm="lee94",
        input_path=SMALL_DATA,
        output_path=output_path,
        config=Lee94Config(),
    )

    out = np.asarray(nib.load(str(output_path)).dataobj)
    assert output_path.exists()
    assert result.algorithm_name == "lee94"
    assert np.count_nonzero(out) > 0


def test_framework_run_cli_executes_lee94_path(tmp_path: Path) -> None:
    """`python -m skelhub run --algorithm lee94` should execute successfully."""
    output_path = tmp_path / "lee94_cli_out.nii.gz"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "skelhub",
            "run",
            "--algorithm",
            "lee94",
            "--input",
            str(SMALL_DATA),
            "--output",
            str(output_path),
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
    assert "framework run complete: algorithm=lee94" in result.stdout
