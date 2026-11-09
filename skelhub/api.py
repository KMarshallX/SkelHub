"""Framework API for algorithms, evaluation, postprocessing, and graph viewing."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

import skelhub.algorithms  # noqa: F401 ensures backend registration
from skelhub.core import EvaluationResult, SkeletonResult, VolumeData, get_backend
from skelhub.evaluation import (  # noqa: F401 re-exported
    evaluate_graph_files,
    evaluate_paths,
    evaluate_skeleton_files,
    evaluate_skeleton_result,
)
from skelhub.io import read_nifti, write_nifti
from skelhub.postprocessing.feature import (
    FeatureExtractionResult,
    extract_features_from_paths as _extract_features_from_paths,
)
from skelhub.postprocessing.graphgen import generate_graphml_from_nifti
from skelhub.visualization import launch_graph_viewer


def _volume_from_path(input_path: str | Path) -> VolumeData:
    """Load a NIfTI file into the framework VolumeData container."""
    data, affine, header = read_nifti(input_path)
    zooms = tuple(float(value) for value in header.get_zooms()[:3]) if header is not None else None
    return VolumeData(
        data=data,
        affine=affine,
        header=header,
        path=str(input_path),
        spacing=zooms if zooms and len(zooms) == 3 else None,
    )


def run_algorithm_from_path(
    algorithm: str,
    input_path: str | Path,
    output_path: str | Path,
    config: object,
    log: Callable[[str], None] | None = None,
) -> SkeletonResult:
    """Run one registered algorithm from disk input to disk output."""
    backend = get_backend(algorithm)
    volume = _volume_from_path(input_path)
    result = backend.run(volume=volume, config=backend.build_config(config), log=log)
    write_nifti(result.skeleton, volume.affine, volume.header, output_path)
    return result


def evaluate_prediction_path(
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
    """Evaluate a NIfTI–NIfTI or GraphML–GraphML prediction/reference pair.

    ``buffer_radius`` is one tolerance or a sequence of tolerances; the first is primary.
    The pair's representation comes from the file extensions; mixed pairs are rejected.

    NIfTI: ``pred_spatial_unit`` / ``ref_spatial_unit`` label headers whose unit is unknown.
    ``foreground_path`` adds the optional foreground EDT-sum agreement from one shared
    binary foreground mask; ``foreground_spatial_unit`` labels its unknown header unit.

    GraphML: ``coordinate_image_path`` (required) is the NIfTI whose voxel grid both graphs
    use; ``coordinate_spatial_unit`` labels its unknown header unit; ``sample_step_um``
    overrides the automatic maximum sampling interval ``0.1 * min(spacing_um)``.

    Options that do not apply to the detected representation raise ``ValueError``.
    """
    return evaluate_paths(
        pred_path,
        ref_path,
        buffer_radius=buffer_radius,
        buffer_radius_unit=buffer_radius_unit,
        pred_spatial_unit=pred_spatial_unit,
        ref_spatial_unit=ref_spatial_unit,
        foreground_path=foreground_path,
        foreground_spatial_unit=foreground_spatial_unit,
        coordinate_image_path=coordinate_image_path,
        coordinate_spatial_unit=coordinate_spatial_unit,
        sample_step_um=sample_step_um,
        log=log,
    )


def generate_graphml_from_skeleton_path(
    input_path: str | Path,
    output_path: str | Path,
    *,
    log: Callable[[str], None] | None = None,
):
    """Generate a Voreen-style proto-graph GraphML file from a skeleton NIfTI."""
    return generate_graphml_from_nifti(input_path, output_path, log=log)


def extract_features_from_paths(
    foreground_path: str | Path,
    skeleton_path: str | Path,
    graph_path: str | Path,
    edge_output_path: str | Path,
    node_output_path: str | Path,
    *,
    sampling_step: float | None = None,
    log: Callable[[str], None] | None = None,
) -> FeatureExtractionResult:
    """Extract Voreen-style edge/node CSV features from vessel inputs.

    Uses edge ``centerline_voxel_points`` when present, else ``centerline_voxels``.
    ``sampling_step`` (voxels, > 0, default 1) applies only to ``centerline_voxel_points``.
    """
    return _extract_features_from_paths(
        foreground_path,
        skeleton_path,
        graph_path,
        edge_output_path,
        node_output_path,
        sampling_step=sampling_step,
        log=log,
    )


def launch_graph_viewer_from_path(
    graph_path: str | Path | None = None,
    *,
    edge_thickness: float = 1.0,
    node_size: float = 2.5,
    edge_geometry: str = "straight",
) -> int:
    """Launch the framework visualization flow on an optional GraphML or NIfTI path."""
    return launch_graph_viewer(
        graph_path,
        edge_thickness=edge_thickness,
        node_size=node_size,
        edge_geometry=edge_geometry,
    )
