"""Public orchestration API for vessel feature extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import nibabel as nib
import numpy as np

from .graph import load_feature_graph
from .measurement import calculate_feature_records
from .models import FeatureExtractionResult, FeatureGraph
from .reporting import write_feature_csvs
from .sampling import DEFAULT_SAMPLING_STEP, validate_sampling_step

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


def _ids_preview(ids: list[int], limit: int = 5) -> str:
    shown = ", ".join(str(value) for value in ids[:limit])
    return shown + (f", ... ({len(ids) - limit} more)" if len(ids) > limit else "")


def _require_graph_in_foreground(graph: FeatureGraph, foreground: np.ndarray) -> None:
    """Raise unless every node position and stored edge path point lies in a foreground voxel.

    Uses the checker's rule: a point counts as inside when any foreground
    voxel cell it touches (including on a shared face, edge or corner) is set.
    """
    # Imported here, not at module level: skelhub.postprocessing imports this package, and an
    # eager import would preload the checker and break `python -m skelhub.postprocessing.checker`.
    from skelhub.postprocessing.checker import points_in_foreground_cells

    node_positions = np.vstack([node.voxel_pos for node in graph.nodes])
    outside_nodes = [
        node.id for node, inside in zip(graph.nodes, points_in_foreground_cells(node_positions, foreground))
        if not inside
    ]
    outside_points = 0
    outside_edges: list[int] = []
    for edge in graph.edges:
        if edge.path.size == 0:
            continue
        outside = int(np.count_nonzero(~points_in_foreground_cells(edge.path, foreground)))
        if outside:
            outside_points += outside
            outside_edges.append(edge.id)
    if not outside_nodes and not outside_edges:
        return
    problems = []
    if outside_nodes:
        problems.append(
            f"{len(outside_nodes)} of {len(graph.nodes)} node voxel_pos values (node ids {_ids_preview(outside_nodes)})"
        )
    if outside_edges:
        problems.append(
            f"{outside_points} {graph.geometry_attribute} entries on {len(outside_edges)} of "
            f"{len(graph.edges)} edges (edge ids {_ids_preview(outside_edges)})"
        )
    raise ValueError("Graph geometry lies outside the vessel foreground: " + "; ".join(problems) + ".")


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
    """Extract dual-space branch features and write edge/node CSV outputs.

    Edge geometry is ``centerline_voxel_points`` when the graph has it, else
    ``centerline_voxels``. Every node position and stored path entry must lie in
    a foreground voxel, otherwise a ``ValueError`` is raised.

    ``sampling_step`` is the maximum spacing (voxels, > 0) of radius samples
    along ``centerline_voxel_points``; ``None`` means 1 voxel. Passing it for a
    graph that only has ``centerline_voxels`` raises a ``ValueError``.
    """
    if sampling_step is not None:
        sampling_step = validate_sampling_step(sampling_step)
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
    if graph.uses_centerline_points:
        resolved_step: float | None = DEFAULT_SAMPLING_STEP if sampling_step is None else sampling_step
    elif sampling_step is not None:
        raise ValueError(
            "The sampling step applies only to centerline_voxel_points, but this graph provides only "
            "centerline_voxels."
        )
    else:
        resolved_step = None
    if log:
        geometry = f"Edge geometry: {graph.geometry_attribute}"
        if resolved_step is not None:
            geometry += f" (radius samples at most {resolved_step:g} voxel apart)"
        log(geometry)
    _require_graph_in_foreground(graph, foreground)

    warnings: list[str] = []
    if not graph.uses_centerline_points:
        graph_path_voxels = {
            tuple(int(value) for value in voxel)
            for edge in graph.edges
            for voxel in edge.path
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
    edges, nodes = calculate_feature_records(foreground, graph, zooms, resolved_step)
    result = FeatureExtractionResult(
        edges=edges,
        nodes=nodes,
        physical_unit=unit,
        warnings=tuple(warnings),
        geometry_attribute=graph.geometry_attribute,
        sampling_step=resolved_step,
    )
    write_feature_csvs(result, edge_output_path, node_output_path)
    if log:
        log(f"Wrote edge CSV: {edge_output_path}")
        log(f"Wrote node CSV: {node_output_path}")
    return result

