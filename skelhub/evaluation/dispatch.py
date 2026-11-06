"""Route a prediction/reference file pair to NIfTI or GraphML evaluation.

The representation comes from the file extension: ``.graphml`` is GraphML,
``.nii`` / ``.nii.gz`` is NIfTI. Mixed pairs and options that do not apply to
the detected representation are rejected instead of ignored.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

from skelhub.core import INPUT_REPRESENTATION_GRAPHML, INPUT_REPRESENTATION_NIFTI, EvaluationResult

from .evaluator import evaluate_skeleton_files
from .graph_evaluator import evaluate_graph_files


GRAPHML_SUFFIX = ".graphml"
NIFTI_SUFFIXES = (".nii", ".nii.gz")


def detect_input_representation(path: str | Path) -> str | None:
    """``graphml``, ``nifti`` or ``None`` (unrecognized extension), from the file name only."""
    name = str(path).lower()
    if name.endswith(GRAPHML_SUFFIX):
        return INPUT_REPRESENTATION_GRAPHML
    if name.endswith(NIFTI_SUFFIXES):
        return INPUT_REPRESENTATION_NIFTI
    return None


def pair_representation(pred_path: str | Path, ref_path: str | Path) -> str:
    """The shared representation of a pair; mixed GraphML/NIfTI pairs are rejected.

    A pair with no GraphML file is treated as NIfTI, so unrecognized
    extensions keep the NIfTI reader's own error messages.
    """
    pred = detect_input_representation(pred_path)
    ref = detect_input_representation(ref_path)
    if INPUT_REPRESENTATION_GRAPHML not in (pred, ref):
        return INPUT_REPRESENTATION_NIFTI
    if pred == ref:
        return INPUT_REPRESENTATION_GRAPHML
    raise ValueError(
        "Prediction and reference must both be GraphML (.graphml) or both be NIfTI (.nii/.nii.gz); "
        f"got prediction '{Path(pred_path).name}' ({pred or 'unrecognized'}) and reference "
        f"'{Path(ref_path).name}' ({ref or 'unrecognized'}). Mixed comparisons are not supported."
    )


def evaluate_paths(
    pred_path: str | Path,
    ref_path: str | Path,
    *,
    buffer_radius: float | Sequence[float],
    buffer_radius_unit: str = "voxels",
    pred_spatial_unit: str | None = None,
    ref_spatial_unit: str | None = None,
    foreground_path: str | Path | None = None,
    foreground_spatial_unit: str | None = None,
    coordinate_image_path: str | Path | None = None,
    coordinate_spatial_unit: str | None = None,
    sample_step_um: float | None = None,
    log: Callable[[str], None] | None = None,
) -> EvaluationResult:
    """Evaluate a NIfTI–NIfTI or GraphML–GraphML pair, checking that every option fits the pair."""
    representation = pair_representation(pred_path, ref_path)
    if representation == INPUT_REPRESENTATION_GRAPHML:
        _reject_nifti_options(pred_spatial_unit, ref_spatial_unit, foreground_path, foreground_spatial_unit)
        if coordinate_image_path is None:
            raise ValueError(
                "GraphML evaluation needs a coordinate image: the NIfTI whose voxel grid both graphs' "
                "voxel_pos and centerline_voxel_points refer to (--coordinate-image; Python: coordinate_image_path)."
            )
        return evaluate_graph_files(
            pred_path,
            ref_path,
            coordinate_image_path=coordinate_image_path,
            buffer_radius=buffer_radius,
            buffer_radius_unit=buffer_radius_unit,
            coordinate_spatial_unit=coordinate_spatial_unit,
            sample_step_um=sample_step_um,
            log=log,
        )
    _reject_graph_options(coordinate_image_path, coordinate_spatial_unit, sample_step_um)
    return evaluate_skeleton_files(
        str(pred_path),
        str(ref_path),
        buffer_radius=buffer_radius,
        buffer_radius_unit=buffer_radius_unit,
        pred_spatial_unit=pred_spatial_unit,
        ref_spatial_unit=ref_spatial_unit,
        foreground_path=None if foreground_path is None else str(foreground_path),
        foreground_spatial_unit=foreground_spatial_unit,
        log=log,
    )


def _reject_nifti_options(
    pred_spatial_unit: str | None,
    ref_spatial_unit: str | None,
    foreground_path: object,
    foreground_spatial_unit: str | None,
) -> None:
    if pred_spatial_unit is not None or ref_spatial_unit is not None:
        raise ValueError(
            "GraphML inputs have no spatial unit of their own; --pred-spatial-unit / --ref-spatial-unit "
            "(Python: pred_spatial_unit / ref_spatial_unit) apply to NIfTI only. Declare the coordinate "
            "image's unit with --coordinate-spatial-unit (Python: coordinate_spatial_unit) if its header "
            "unit is unknown."
        )
    if foreground_path is not None or foreground_spatial_unit is not None:
        raise ValueError(
            "The foreground EDT-sum agreement is NIfTI-only; --foreground / --foreground-spatial-unit "
            "(Python: foreground_path / foreground_spatial_unit) cannot be used with GraphML inputs."
        )


def _reject_graph_options(
    coordinate_image_path: object,
    coordinate_spatial_unit: str | None,
    sample_step_um: float | None,
) -> None:
    given = [
        flag
        for flag, value in (
            ("--coordinate-image (coordinate_image_path)", coordinate_image_path),
            ("--coordinate-spatial-unit (coordinate_spatial_unit)", coordinate_spatial_unit),
            ("--sample-step-um (sample_step_um)", sample_step_um),
        )
        if value is not None
    ]
    if given:
        raise ValueError(
            f"{', '.join(given)} only apply to GraphML inputs; the prediction and reference here are NIfTI."
        )
