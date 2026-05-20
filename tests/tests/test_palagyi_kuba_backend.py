"""Palagyi-Kuba backend tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import ndimage as ndi

from skelhub.algorithms.palagyi_kuba import PalagyiKubaConfig
from skelhub.algorithms.palagyi_kuba.directions import SUBITERATION_ORDER
from skelhub.algorithms.palagyi_kuba.templates import CURVE_TEMPLATES, SURFACE_TEMPLATES
from skelhub.core import SkeletonResult, VolumeData, get_backend, list_backends


REPO_ROOT = Path(__file__).resolve().parents[1]


def _volume(data: np.ndarray) -> VolumeData:
    return VolumeData(data=data, affine=np.eye(4), header=None, spacing=(1.0, 1.0, 1.0))


def test_registry_exposes_palagyi_kuba_backend() -> None:
    assert "palagyi_kuba" in list_backends()
    assert get_backend("palagyi_kuba").name == "palagyi_kuba"


def test_palagyi_kuba_config_validation() -> None:
    PalagyiKubaConfig(mode="curve").validate()
    PalagyiKubaConfig(mode="surface", max_cycles=1).validate()

    for config in (
        PalagyiKubaConfig(mode="bad"),
        PalagyiKubaConfig(binarize_threshold=-0.1),
        PalagyiKubaConfig(max_cycles=0),
    ):
        try:
            config.validate()
        except ValueError:
            pass
        else:
            raise AssertionError("Expected invalid PalagyiKubaConfig to be rejected.")


def test_template_inventory_and_direction_schedule_are_locked() -> None:
    assert [template.label for template in CURVE_TEMPLATES] == [f"T{i}" for i in range(1, 15)]
    assert [template.label for template in SURFACE_TEMPLATES] == ["T1'", "T2'", "T7'", "T8'", "T9'", "T10'"]
    assert SUBITERATION_ORDER == ("US", "NE", "DW", "SE", "UW", "DN", "SW", "UN", "DE", "NW", "UE", "DS")


def test_non_3d_input_is_rejected() -> None:
    backend = get_backend("palagyi_kuba")
    try:
        backend.run(_volume(np.zeros((4, 4), dtype=np.uint8)), PalagyiKubaConfig())
    except ValueError:
        pass
    else:
        raise AssertionError("Expected non-3D input to be rejected.")


def test_empty_foreground_returns_zero_skeleton_with_warning() -> None:
    result = get_backend("palagyi_kuba").run(
        _volume(np.zeros((5, 5, 5), dtype=np.uint8)),
        PalagyiKubaConfig(),
    )

    assert isinstance(result, SkeletonResult)
    assert result.skeleton.dtype == np.uint8
    assert result.skeleton.shape == (5, 5, 5)
    assert np.count_nonzero(result.skeleton) == 0
    assert any("no foreground" in warning for warning in result.warnings)


def test_non_binary_input_thresholds_at_configured_value() -> None:
    data = np.zeros((7, 7, 7), dtype=np.float32)
    data[2:5, 2:5, 2:5] = 0.75
    data[0, 0, 0] = 0.25

    result = get_backend("palagyi_kuba").run(_volume(data), PalagyiKubaConfig(max_cycles=1))

    assert result.skeleton.dtype == np.uint8
    assert set(np.unique(result.skeleton)).issubset({0, 1})
    assert any("not exactly binary" in warning for warning in result.warnings)
    assert result.backend_metadata["palagyi_kuba"]["input_foreground_voxels"] == 27


def test_straight_line_is_preserved_in_curve_mode() -> None:
    data = np.zeros((7, 7, 7), dtype=np.uint8)
    data[3, 3, 1:6] = 1

    result = get_backend("palagyi_kuba").run(_volume(data), PalagyiKubaConfig(mode="curve"))

    assert np.array_equal(result.skeleton, data)


def test_solid_block_thins_and_remains_connected() -> None:
    data = np.zeros((9, 9, 9), dtype=np.uint8)
    data[2:7, 2:7, 2:7] = 1

    result = get_backend("palagyi_kuba").run(_volume(data), PalagyiKubaConfig(mode="curve", max_cycles=8))
    structure = ndi.generate_binary_structure(3, 3)
    _, components = ndi.label(result.skeleton.astype(bool), structure=structure)

    assert 0 < np.count_nonzero(result.skeleton) < np.count_nonzero(data)
    assert components == 1
    assert result.backend_metadata["palagyi_kuba"]["cycle_count"] >= 1


def test_simple_branch_fixture_remains_26_connected() -> None:
    data = np.zeros((9, 9, 9), dtype=np.uint8)
    data[4, 4, 1:8] = 1
    data[4, 1:5, 4] = 1
    data[2:5, 4, 4] = 1

    result = get_backend("palagyi_kuba").run(_volume(data), PalagyiKubaConfig(mode="curve"))
    structure = ndi.generate_binary_structure(3, 3)
    _, components = ndi.label(result.skeleton.astype(bool), structure=structure)

    assert components == 1
    assert np.count_nonzero(result.skeleton) == np.count_nonzero(data)


def test_surface_mode_smoke_on_simple_slab() -> None:
    data = np.zeros((9, 9, 9), dtype=np.uint8)
    data[3:6, 2:7, 2:7] = 1

    result = get_backend("palagyi_kuba").run(_volume(data), PalagyiKubaConfig(mode="surface", max_cycles=6))

    assert result.skeleton.dtype == np.uint8
    assert result.skeleton.shape == data.shape
    assert set(np.unique(result.skeleton)).issubset({0, 1})
    assert np.count_nonzero(result.skeleton) > 0


def test_framework_run_cli_executes_palagyi_kuba_path(tmp_path: Path) -> None:
    input_path = tmp_path / "input.nii.gz"
    output_path = tmp_path / "out.nii.gz"

    arr = np.zeros((9, 9, 9), dtype=np.uint8)
    arr[2:7, 2:7, 2:7] = 1
    nib.save(nib.Nifti1Image(arr, affine=np.eye(4)), str(input_path))

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "skelhub",
            "run",
            "--algorithm",
            "palagyi_kuba",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--pk-mode",
            "curve",
            "--pk-max-cycles",
            "4",
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
    assert "framework run complete: algorithm=palagyi_kuba" in result.stdout
