"""Evaluation subsystem tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from skelhub.evaluation import evaluate_skeleton_files, evaluate_skeleton_volumes


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_identical_skeletons_produce_perfect_scores() -> None:
    """Identical binary skeletons should score perfectly with a zero-radius buffer."""
    ref = _line_skeleton()
    pred = ref.copy()

    result = evaluate_skeleton_volumes(
        pred,
        ref,
        spacing=(1.0, 1.0, 1.0),
        buffer_radius=0.0,
    )

    assert result.TP == 3
    assert result.FP == 0
    assert result.FN == 0
    assert result.Cp == pytest.approx(1.0)
    assert result.Cr == pytest.approx(1.0)
    assert result.OCC == pytest.approx(0.0)
    assert result.BCC == pytest.approx(0.0)
    assert result.E == pytest.approx(0.0)
    assert result.OCC_normalized == pytest.approx(1.0)
    assert result.BCC_normalized == pytest.approx(1.0)
    assert result.E_normalized == pytest.approx(1.0)
    assert result.P == pytest.approx(1.0)


def test_split_prediction_changes_geometry_and_morphology_metrics() -> None:
    """A split prediction should change completeness and signed morphology values predictably."""
    ref = _line_skeleton()
    pred = np.zeros_like(ref)
    pred[2, 2, 1] = 1
    pred[2, 2, 3] = 1

    result = evaluate_skeleton_volumes(
        pred,
        ref,
        spacing=(1.0, 1.0, 1.0),
        buffer_radius=0.0,
    )

    assert result.TP == 2
    assert result.FP == 0
    assert result.FN == 1
    assert result.Cp == pytest.approx(2.0 / 3.0)
    assert result.Cr == pytest.approx(1.0)
    assert result.OCC == pytest.approx(1.0)
    assert result.BCC == pytest.approx(0.0)
    assert result.E == pytest.approx(-1.0)
    assert result.OCC_normalized == pytest.approx(0.8)
    assert result.BCC_normalized == pytest.approx(1.0)
    assert result.E_normalized == pytest.approx(0.8)
    assert result.P == pytest.approx((2.0 / 3.0 + 1.0 + 0.8 + 1.0 + 0.8) / 5.0)


def test_endpoint_count_uses_6_connectivity_for_diagonal_tip_cases() -> None:
    """Diagonal-only side contacts should not suppress endpoints under the v1 rule."""
    ref = np.zeros((4, 4, 4), dtype=np.uint8)
    pred = np.zeros_like(ref)

    ref[1, 1, 1] = 1
    ref[1, 1, 2] = 1
    ref[2, 2, 2] = 1

    pred[:] = ref

    result = evaluate_skeleton_volumes(
        pred,
        ref,
        spacing=(1.0, 1.0, 1.0),
        buffer_radius=0.0,
    )

    assert result.metadata["supporting_counts"]["ref_endpoints"] == 2
    assert result.metadata["supporting_counts"]["pred_endpoints"] == 2
    assert not any("E reference count was zero" in warning for warning in result.warnings)


def test_empty_skeletons_return_stable_scores_with_explicit_warnings() -> None:
    """Empty skeletons should not crash and should expose the zero-denominator policy."""
    empty = np.zeros((4, 4, 4), dtype=np.uint8)

    result = evaluate_skeleton_volumes(
        empty,
        empty,
        spacing=(1.0, 1.0, 1.0),
        buffer_radius=0.0,
    )

    assert result.TP == 0
    assert result.FP == 0
    assert result.FN == 0
    assert result.Cp == pytest.approx(1.0)
    assert result.Cr == pytest.approx(1.0)
    assert result.P == pytest.approx(1.0)
    assert any("both skeletons are empty" in warning for warning in result.warnings)


def test_anisotropic_spacing_emits_warning_for_voxel_radius() -> None:
    """Anisotropic spacing should be surfaced clearly in evaluation warnings."""
    skeleton = _line_skeleton()

    result = evaluate_skeleton_volumes(
        skeleton,
        skeleton,
        spacing=(1.0, 1.0, 2.0),
        buffer_radius=1.0,
        buffer_radius_unit="voxels",
    )

    assert any("anisotropic" in warning.lower() for warning in result.warnings)


def test_shape_mismatch_fails_hard() -> None:
    """Prediction/reference shape mismatches should raise explicit errors."""
    pred = np.zeros((4, 4, 4), dtype=np.uint8)
    ref = np.zeros((5, 4, 4), dtype=np.uint8)

    with pytest.raises(ValueError, match="matching shapes"):
        evaluate_skeleton_volumes(
            pred,
            ref,
            spacing=(1.0, 1.0, 1.0),
            buffer_radius=1.0,
        )


def test_non_binary_values_fail_hard() -> None:
    """Non-binary skeleton values should be rejected explicitly."""
    pred = _line_skeleton().astype(np.float32)
    pred[2, 2, 2] = 0.5

    with pytest.raises(ValueError, match="binary values"):
        evaluate_skeleton_volumes(
            pred,
            _line_skeleton(),
            spacing=(1.0, 1.0, 1.0),
            buffer_radius=1.0,
        )


def test_spacing_mismatch_fails_hard_for_file_inputs(tmp_path: Path) -> None:
    """File-based evaluation should reject mismatched spacing instead of resampling."""
    pred_path = tmp_path / "pred.nii.gz"
    ref_path = tmp_path / "ref.nii.gz"
    _write_binary_nifti(pred_path, _line_skeleton(), spacing=(1.0, 1.0, 1.0))
    _write_binary_nifti(ref_path, _line_skeleton(), spacing=(1.0, 1.0, 2.0))

    with pytest.raises(ValueError, match="matching spacing"):
        evaluate_skeleton_files(
            pred_path,
            ref_path,
            buffer_radius=1.0,
        )


def test_evaluation_cli_smoke_and_json_output(tmp_path: Path) -> None:
    """The CLI should evaluate successfully and emit a structured JSON report."""
    pred_path = tmp_path / "pred.nii.gz"
    ref_path = tmp_path / "ref.nii.gz"
    json_path = tmp_path / "report.json"
    _write_binary_nifti(pred_path, _line_skeleton(), spacing=(1.0, 1.0, 1.0))
    _write_binary_nifti(ref_path, _line_skeleton(), spacing=(1.0, 1.0, 1.0))

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "skelhub",
            "evaluate",
            "--pred",
            str(pred_path),
            "--ref",
            str(ref_path),
            "--buffer-radius",
            "0",
            "--json-output",
            str(json_path),
        ],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert "SkelHub Evaluation Report" in result.stdout
    assert "Global performance score P: 1.0000" in result.stdout
    assert payload["config"]["buffer_radius"] == 0.0
    assert payload["raw_metrics"]["TP"] == 3
    assert payload["normalized_metrics"]["P"] == pytest.approx(1.0)


def _line_skeleton() -> np.ndarray:
    array = np.zeros((5, 5, 5), dtype=np.uint8)
    array[2, 2, 1:4] = 1
    return array


def _write_binary_nifti(
    path: Path,
    data: np.ndarray,
    *,
    spacing: tuple[float, float, float],
    spatial_unit: str = "mm",
) -> None:
    image = nib.Nifti1Image(np.asarray(data, dtype=np.uint8), affine=np.eye(4))
    image.header.set_zooms(spacing)
    image.header.set_xyzt_units(spatial_unit)
    nib.save(image, str(path))
