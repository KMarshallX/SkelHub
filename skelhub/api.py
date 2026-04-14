"""Framework API for running algorithms, evaluation, and graph viewing."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import skelhub.algorithms  # noqa: F401 ensures backend registration
from skelhub.core import EvaluationResult, SkeletonResult, VolumeData, get_backend
from skelhub.evaluation import evaluate_skeleton_file
from skelhub.io import read_nifti, write_nifti
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
    log: Callable[[str], None] | None = None,
) -> EvaluationResult:
    """Run the framework-level evaluation placeholder on a prediction path."""
    return evaluate_skeleton_file(str(pred_path), log=log)


def launch_graph_viewer_from_path(
    graph_path: str | Path,
    *,
    edge_thickness: float = 2.0,
    node_size: float = 6.0,
) -> int:
    """Launch the framework graph visualization flow on a GraphML path."""
    return launch_graph_viewer(
        graph_path,
        edge_thickness=edge_thickness,
        node_size=node_size,
    )
