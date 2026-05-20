"""Flux-driven medial curve backend tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from skelhub.algorithms.flux import FluxConfig
from skelhub.core import SkeletonResult, VolumeData, get_backend, list_backends


REPO_ROOT = Path(__file__).resolve().parents[1]


def _straight_tube(shape: tuple[int, int, int] = (13, 13, 21)) -> np.ndarray:
    volume = np.zeros(shape, dtype=np.uint8)
    volume[4:9, 4:9, 3 : shape[2] - 3] = 1
    return volume


def test_registry_exposes_flux_backend() -> None:
    """The framework registry should expose the flux backend."""
    assert "flux" in list_backends()
    assert get_backend("flux").name == "flux"


def test_flux_config_validation_rejects_bad_values() -> None:
    """Flux config validation should reject invalid sigma controls."""
    with pytest.raises(ValueError):
        FluxConfig(sigma=-0.1).validate()
    with pytest.raises(ValueError):
        FluxConfig(sigma_unit="pixels").validate()


def test_flux_backend_rejects_non_binary_input() -> None:
    """Flux should enforce the exact binary input contract."""
    data = _straight_tube().astype(np.float32)
    data[6, 6, 6] = 0.5
    volume = VolumeData(data=data, affine=np.eye(4), header=None, spacing=(1.0, 1.0, 1.0))

    with pytest.raises(ValueError, match=r"\{0, 1\}"):
        get_backend("flux").run(volume=volume, config=FluxConfig())


def test_flux_backend_handles_empty_binary_input() -> None:
    """Empty binary inputs should return an empty skeleton and warning."""
    data = np.zeros((5, 6, 7), dtype=np.uint8)
    volume = VolumeData(data=data, affine=np.eye(4), header=None, spacing=(1.0, 1.0, 1.0))

    result = get_backend("flux").run(volume=volume, config=FluxConfig())

    assert isinstance(result, SkeletonResult)
    assert result.algorithm_name == "flux"
    assert result.skeleton.shape == data.shape
    assert result.skeleton.dtype == np.uint8
    assert np.count_nonzero(result.skeleton) == 0
    assert result.warnings


def test_flux_backend_returns_binary_skeleton_and_metadata() -> None:
    """Flux should produce a same-shape binary uint8 skeleton with trace metadata."""
    data = _straight_tube()
    volume = VolumeData(
        data=data,
        affine=np.eye(4),
        header=None,
        path="synthetic_tube.nii.gz",
        spacing=(0.5, 0.5, 1.0),
    )

    result = get_backend("flux").run(
        volume=volume,
        config=FluxConfig(threshold=0.0, sigma=0.5, sigma_unit="physical"),
    )

    assert isinstance(result, SkeletonResult)
    assert result.algorithm_name == "flux"
    assert result.skeleton.shape == data.shape
    assert result.skeleton.dtype == np.uint8
    assert np.count_nonzero(result.skeleton) > 0
    assert set(np.unique(result.skeleton)).issubset({0, 1})
    assert result.input_metadata["spacing"] == (0.5, 0.5, 1.0)

    metadata = result.backend_metadata["flux"]
    assert result.backend_metadata["config"] == {
        "threshold": 0.0,
        "sigma": 0.5,
        "sigma_unit": "physical",
    }
    assert metadata["input_foreground_voxels"] == int(np.count_nonzero(data))
    assert metadata["output_foreground_voxels"] == int(np.count_nonzero(result.skeleton))
    assert metadata["copied_vmtk_source"] is False
    assert "signed Euclidean distance" in metadata["distance"]
    assert "26-neighborhood flux" in metadata["average_outward_flux"]
    assert metadata["sigma_voxels"] == (1.0, 1.0, 0.5)


def test_framework_run_cli_executes_flux_path(tmp_path: Path) -> None:
    """`python -m skelhub run --algorithm flux` should execute successfully."""
    input_path = tmp_path / "input.nii.gz"
    output_path = tmp_path / "flux_cli_out.nii.gz"
    nib.save(nib.Nifti1Image(_straight_tube(), affine=np.eye(4)), str(input_path))

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "skelhub",
            "run",
            "--algorithm",
            "flux",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--flux-sigma-unit",
            "voxels",
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
    assert set(np.unique(out)).issubset({0.0, 1.0})
    assert "framework run complete: algorithm=flux" in result.stdout
