"""Public API for Voreen-faithful skeleton-to-protograph generation."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np

from skelhub.io import read_nifti

from .classification import classify_skeleton_voxels
from .components import extract_skeleton_components
from .graphml import write_graphml
from .protograph import ProtoGraph, build_protograph


def generate_protograph_from_skeleton(
    skeleton: np.ndarray,
    *,
    affine: np.ndarray | None = None,
    log: Callable[[str], None] | None = None,
) -> ProtoGraph:
    """Generate a Voreen-style proto-graph from a 3D skeleton array."""
    if skeleton.ndim != 3:
        raise ValueError("Graph generation expects a 3D skeleton volume.")
    if not np.any(skeleton):
        raise ValueError("Input skeleton volume does not contain foreground voxels.")

    if log:
        log("Classifying skeleton voxels with 26-neighborhood counts.")
    classes = classify_skeleton_voxels(skeleton)

    if log:
        log("Extracting end, regular, and branch connected components.")
    components = extract_skeleton_components(classes)

    if log:
        log("Building proto-graph topology from classified components.")
    graph = build_protograph(components, skeleton.shape, affine=affine)
    if not graph.nodes or not graph.edges:
        raise ValueError("Generated proto-graph is empty or edge-free.")
    return graph


def generate_graphml_from_nifti(
    input_path: str | Path,
    output_path: str | Path,
    *,
    log: Callable[[str], None] | None = None,
) -> ProtoGraph:
    """Load a skeleton NIfTI, generate a proto-graph, and write GraphML."""
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input skeleton does not exist: {input_path}")

    if log:
        log(f"Loading skeleton NIfTI: {input_path}")
    data, affine, _ = read_nifti(str(input_path))
    graph = generate_protograph_from_skeleton(data, affine=affine, log=log)

    if log:
        log(f"Writing GraphML: {output_path}")
    write_graphml(graph, output_path)
    return graph
