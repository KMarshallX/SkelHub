"""Public orchestration API for vessel feature extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import nibabel as nib
import numpy as np

from .graph import load_feature_graph
from .measurement import calculate_feature_records
from .models import FeatureExtractionResult
from .reporting import write_feature_csvs

_UNIT_SUFFIX = {"mm": "mm", "micron": "um", "meter": "m", "unknown": "unknown"}


def _load_binary_volume(path: str | Path, *, label: str) -> tuple[np.ndarray, np.ndarray, nib.Nifti1Header]:
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"{label} volume does not exist: {input_path}")
    image = nib.load(str(input_path))
    data = np.asarray(image.dataobj)
    if data.ndim != 3:
        raise ValueError(f"{label} volume must be 3D.")
    unique = np.unique(data)
    if not set(unique.tolist()).issubset({0, 1}):
        raise ValueError(f"{label} volume must be binary with values in {{0, 1}}.")
    return data.astype(bool, copy=False), np.asarray(image.affine, dtype=float), image.header.copy()


def _spatial_unit(header: nib.Nifti1Header) -> str:
    spatial, _ = header.get_xyzt_units()
    return _UNIT_SUFFIX.get(spatial, "unknown")


def extract_features_from_paths(
    foreground_path: str | Path,
    skeleton_path: str | Path,
    graph_path: str | Path,
    edge_output_path: str | Path,
    node_output_path: str | Path,
    *,
    log: Callable[[str], None] | None = None,
) -> FeatureExtractionResult:
    """Extract dual-space branch features and write edge/node CSV outputs."""
    if log:
        log(f"Loading binary vessel foreground: {foreground_path}")
    foreground, foreground_affine, foreground_header = _load_binary_volume(foreground_path, label="Foreground")
    if log:
        log(f"Loading binary vessel skeleton: {skeleton_path}")
    skeleton, skeleton_affine, _ = _load_binary_volume(skeleton_path, label="Skeleton")
    if foreground.shape != skeleton.shape:
        raise ValueError("Foreground and skeleton volumes must have matching shapes.")
    if not np.allclose(foreground_affine, skeleton_affine, rtol=0.0, atol=1e-6):
        raise ValueError("Foreground and skeleton volumes must have matching spatial geometry.")
    if np.any(skeleton & ~foreground):
        raise ValueError("Skeleton foreground must be contained in vessel foreground.")

    if log:
        log(f"Loading feature graph: {graph_path}")
    graph = load_feature_graph(graph_path, foreground.shape)
    warnings: list[str] = []
    graph_path_voxels = {
        tuple(int(value) for value in voxel)
        for edge in graph.edges
        for voxel in edge.centerline_voxels
    }
    off_skeleton = sum(not skeleton[voxel] for voxel in graph_path_voxels)
    if off_skeleton:
        warning = (
            f"Graph contains {off_skeleton} centerline voxels outside the supplied skeleton; "
            "GraphML edge paths are used as authoritative feature geometry."
        )
        warnings.append(warning)
        if log:
            log(warning)

    zooms = tuple(float(value) for value in foreground_header.get_zooms()[:3])
    if len(zooms) != 3 or not np.isfinite(zooms).all() or any(value <= 0 for value in zooms):
        raise ValueError("Foreground NIfTI header must provide three positive finite voxel sizes.")
    unit = _spatial_unit(foreground_header)
    if log:
        log(f"Calculating voxel and image-space features (image unit: {unit}).")
    edges, nodes = calculate_feature_records(foreground, graph, zooms)
    result = FeatureExtractionResult(edges=edges, nodes=nodes, physical_unit=unit, warnings=tuple(warnings))
    write_feature_csvs(result, edge_output_path, node_output_path)
    if log:
        log(f"Wrote edge CSV: {edge_output_path}")
        log(f"Wrote node CSV: {node_output_path}")
    return result

