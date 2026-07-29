#!/usr/bin/env python3
"""Run local PCA on selected world and voxel coordinates from a GraphML graph."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import networkx as nx
import numpy as np


REPEATED_EIGENVALUE_RTOL = 1.0e-8
REPEATED_EIGENVALUE_ATOL = 1.0e-12


class LocalPCAError(ValueError):
    """Raised when local PCA input cannot be validated or processed."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compute unnormalised local PCA scatter matrices for selected GraphML "
            "nodes using both world and voxel coordinates."
        ),
        epilog=(
            "Example: run_localPCA.sh --input graph.graphml "
            "--node_cluster '[n190, n191, n248]'"
        ),
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Readable, non-empty GraphML vessel graph.",
    )
    parser.add_argument(
        "-c",
        "--node_cluster",
        required=True,
        help="Quoted bracketed node-ID list, for example '[n190, n191, n248]'.",
    )
    return parser.parse_args()


def parse_node_cluster(value: str) -> list[str]:
    """Parse and validate a bracketed, comma-separated node-ID list."""
    stripped = value.strip()
    if not (stripped.startswith("[") and stripped.endswith("]")):
        raise LocalPCAError(
            "--node_cluster must be a bracketed, comma-separated list, "
            "for example '[n190, n191, n248]'."
        )

    inner = stripped[1:-1].strip()
    node_ids = [item.strip() for item in inner.split(",")] if inner else []
    if any(not node_id for node_id in node_ids):
        raise LocalPCAError("--node_cluster contains an empty node ID.")
    if len(node_ids) < 3:
        raise LocalPCAError("--node_cluster must contain at least 3 node IDs.")

    duplicates = sorted(
        node_id for node_id, count in Counter(node_ids).items() if count > 1
    )
    if duplicates:
        raise LocalPCAError(
            "--node_cluster must contain unique node IDs; duplicate(s): "
            + ", ".join(duplicates)
        )
    return node_ids


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


def load_graphml(path_value: str) -> tuple[nx.Graph, Counter[str]]:
    """Load a readable GraphML file and retain raw node-ID occurrence counts."""
    path = Path(path_value).expanduser()
    if path.suffix.lower() != ".graphml":
        raise LocalPCAError(f"--input must have a .graphml extension: {path}")
    if not path.is_file():
        raise LocalPCAError(f"--input does not exist or is not a file: {path}")
    if not os.access(path, os.R_OK):
        raise LocalPCAError(f"--input is not readable: {path}")

    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError) as exc:
        raise LocalPCAError(f"--input is not valid GraphML: {path}: {exc}") from exc

    root = tree.getroot()
    if _local_name(root.tag) != "graphml":
        raise LocalPCAError(
            f"--input is not valid GraphML: root element must be 'graphml': {path}"
        )

    node_id_counts: Counter[str] = Counter()
    for element in root.iter():
        if _local_name(element.tag) != "node":
            continue
        node_id = element.get("id")
        if node_id is not None:
            node_id_counts[node_id] += 1

    try:
        graph = nx.read_graphml(path)
    except Exception as exc:
        raise LocalPCAError(f"--input is not valid GraphML: {path}: {exc}") from exc

    if graph.number_of_nodes() == 0:
        raise LocalPCAError(f"--input GraphML graph contains no nodes: {path}")
    return graph, node_id_counts


def validate_requested_nodes(
    graph: nx.Graph,
    node_id_counts: Counter[str],
    node_ids: list[str],
) -> None:
    """Require every requested node ID to occur exactly once in the input graph."""
    invalid = [
        (node_id, node_id_counts[node_id])
        for node_id in node_ids
        if node_id_counts[node_id] != 1 or node_id not in graph
    ]
    if not invalid:
        return

    details = ", ".join(
        f"{node_id} (found {count} time{'s' if count != 1 else ''})"
        for node_id, count in invalid
    )
    raise LocalPCAError(
        "Every requested node ID must exist exactly once in the GraphML graph; "
        + details
    )


def _finite_float(value: object, *, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise LocalPCAError(f"{label} must be numeric.") from exc
    if not np.isfinite(number):
        raise LocalPCAError(f"{label} must be finite.")
    return number


def extract_coordinates(
    graph: nx.Graph,
    node_ids: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Extract ordered world XYZ and voxel coordinates for the selected nodes."""
    world_points: list[list[float]] = []
    voxel_points: list[list[float]] = []

    for node_id in node_ids:
        attributes = graph.nodes[node_id]
        world_points.append(
            [
                _finite_float(
                    attributes.get(axis),
                    label=f"Node {node_id!r} world coordinate {axis!r}",
                )
                for axis in ("X", "Y", "Z")
            ]
        )

        voxel_value = attributes.get("voxel_pos")
        try:
            parsed_voxel = json.loads(str(voxel_value))
            voxel_point = np.asarray(parsed_voxel, dtype=float)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise LocalPCAError(
                f"Node {node_id!r} attribute 'voxel_pos' must be a JSON array "
                "of three finite numeric coordinates."
            ) from exc
        if voxel_point.shape != (3,) or not np.isfinite(voxel_point).all():
            raise LocalPCAError(
                f"Node {node_id!r} attribute 'voxel_pos' must be a JSON array "
                "of three finite numeric coordinates."
            )
        voxel_points.append(voxel_point.tolist())

    return np.asarray(world_points, dtype=float), np.asarray(voxel_points, dtype=float)


def compute_pca(
    points: np.ndarray,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    list[str],
]:
    """Compute descending eigenpairs of the unnormalised centered scatter matrix."""
    centroid = points.mean(axis=0)
    centered = points - centroid
    scatter = centered.T @ centered

    eigenvalues, eigenvectors = np.linalg.eigh(scatter)
    descending = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[descending]
    eigenvectors = eigenvectors[:, descending]

    norms = np.linalg.norm(eigenvectors, axis=0)
    normalized_eigenvectors = eigenvectors / norms

    warnings: list[str] = []
    largest_eigenvalue = max(float(np.max(np.abs(eigenvalues))), 0.0)
    rank_tolerance = largest_eigenvalue * 1.0e-10
    rank = int(np.count_nonzero(eigenvalues > rank_tolerance))
    if rank <= 1:
        warnings.append(
            "Selected points are collinear; two principal directions are "
            "underdetermined."
        )
    elif rank == 2:
        warnings.append(
            "Selected points are coplanar; the direction normal to the point "
            "plane may be numerically sensitive."
        )

    scale = max(largest_eigenvalue, 1.0)
    repeated_pairs: list[str] = []
    for first in range(len(eigenvalues)):
        for second in range(first + 1, len(eigenvalues)):
            if np.isclose(
                eigenvalues[first],
                eigenvalues[second],
                rtol=REPEATED_EIGENVALUE_RTOL,
                atol=REPEATED_EIGENVALUE_ATOL * scale,
            ):
                repeated_pairs.append(f"{first + 1} and {second + 1}")
    if repeated_pairs:
        warnings.append(
            "Eigenvalues "
            + ", ".join(repeated_pairs)
            + " are effectively repeated; their corresponding principal "
            "directions are underdetermined."
        )

    return (
        centroid,
        scatter,
        eigenvalues,
        eigenvectors,
        normalized_eigenvectors,
        warnings,
    )


def _format_vector(values: np.ndarray) -> str:
    return np.array2string(
        np.asarray(values),
        precision=12,
        separator=", ",
        suppress_small=False,
    )


def print_report(label: str, coordinate_names: str, points: np.ndarray) -> None:
    """Print one coordinate system's scatter matrix, warnings, and eigenpairs."""
    (
        centroid,
        scatter,
        eigenvalues,
        eigenvectors,
        normalized_eigenvectors,
        warnings,
    ) = compute_pca(points)

    print(f"\n=== {label} ({coordinate_names}) ===")
    print(f"Centroid: {_format_vector(centroid)}")
    print("Unnormalised scatter matrix C = sum((x - mean) (x - mean)^T):")
    print(_format_vector(scatter))
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  - {warning}")
    else:
        print("Warnings: none")

    print("Eigenpairs (descending eigenvalue order):")
    for index, eigenvalue in enumerate(eigenvalues):
        print(f"  {index + 1}. Eigenvalue: {eigenvalue:.12g}")
        print(
            "     Eigenvector (raw solver output; not additionally normalised): "
            f"{_format_vector(eigenvectors[:, index])}"
        )
        print(
            "     Normalised eigenvector (unit vector): "
            f"{_format_vector(normalized_eigenvectors[:, index])}"
        )


def main() -> int:
    args = parse_args()
    try:
        node_ids = parse_node_cluster(args.node_cluster)
        graph, node_id_counts = load_graphml(args.input)
        validate_requested_nodes(graph, node_id_counts, node_ids)
        world_points, voxel_points = extract_coordinates(graph, node_ids)
    except LocalPCAError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"Input GraphML: {Path(args.input).expanduser()}")
    print(f"Node cluster ({len(node_ids)} unique nodes): [{', '.join(node_ids)}]")
    print(
        "PCA convention: centered unnormalised scatter matrix; C is not divided "
        "by N or N-1."
    )
    print(
        "Note: numpy.linalg.eigh returns unit-length eigenvectors, so raw and "
        "normalised vectors will normally be identical; eigenvector signs are arbitrary."
    )
    print_report("World coordinates", "X, Y, Z", world_points)
    print_report("Voxel coordinates", "voxel_pos", voxel_points)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
