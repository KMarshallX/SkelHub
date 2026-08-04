"""Contract degree-2 GraphML nodes into ordered edge centreline paths."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Callable, Sequence

import igraph as ig
import numpy as np


NodeProgress = Callable[[int, int], None]


@dataclass(frozen=True, slots=True)
class ProtographCleaningStats:
    """Counts describing one degree-2 contraction."""

    input_nodes: int
    input_edges: int
    degree_two_nodes: int
    removed_nodes: int
    output_nodes: int
    output_edges: int
    parallel_path_pairs: int
    retained_cycle_anchors: int


@dataclass(frozen=True, slots=True)
class _Chain:
    nodes: tuple[int, ...]
    edges: tuple[int, ...]


def _load_json_path(
    value: object,
    *,
    label: str,
    integer: bool,
) -> list[tuple[float, float, float]] | list[tuple[int, int, int]]:
    try:
        raw = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must contain a JSON list of 3D points.") from exc

    points = np.asarray(raw, dtype=float)
    if points.ndim != 2 or points.shape[1:] != (3,) or len(points) == 0:
        raise ValueError(f"{label} must contain at least one 3D point.")
    if not np.isfinite(points).all():
        raise ValueError(f"{label} must contain only finite coordinates.")

    if integer:
        rounded = np.rint(points)
        if not np.allclose(points, rounded, rtol=0.0, atol=1e-8):
            raise ValueError(f"{label} must contain integer voxel coordinates.")
        return [tuple(int(value) for value in point) for point in rounded]
    return [tuple(float(value) for value in point) for point in points]


def _load_node_positions(graph: ig.Graph, progress: NodeProgress | None) -> list[np.ndarray]:
    if "voxel_pos" not in graph.vs.attributes():
        raise ValueError("GraphML nodes must provide the 'voxel_pos' attribute.")

    total = graph.vcount()
    positions: list[np.ndarray] = []
    for processed, vertex in enumerate(graph.vs, start=1):
        label = f"node {vertex.index} voxel_pos"
        try:
            raw = json.loads(str(vertex["voxel_pos"]))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"{label} must contain JSON coordinates.") from exc
        point = np.asarray(raw, dtype=float)
        if point.shape != (3,) or not np.isfinite(point).all():
            raise ValueError(f"{label} must contain three finite coordinates.")
        positions.append(point)
        if progress is not None:
            progress(processed, total)
    return positions


def _oriented_path(
    graph: ig.Graph,
    edge_id: int,
    start: int,
    end: int,
    positions: Sequence[np.ndarray],
    *,
    attribute: str,
    integer: bool,
) -> list[tuple[float, float, float]] | list[tuple[int, int, int]]:
    edge = graph.es[edge_id]
    points = _load_json_path(
        edge[attribute],
        label=f"edge {edge_id} {attribute}",
        integer=integer,
    )
    expected_start = np.rint(positions[start]) if integer else positions[start]
    expected_end = np.rint(positions[end]) if integer else positions[end]
    first = np.asarray(points[0], dtype=float)
    last = np.asarray(points[-1], dtype=float)

    if np.allclose(first, expected_start, rtol=0.0, atol=1e-8) and np.allclose(
        last, expected_end, rtol=0.0, atol=1e-8
    ):
        return points
    if np.allclose(first, expected_end, rtol=0.0, atol=1e-8) and np.allclose(
        last, expected_start, rtol=0.0, atol=1e-8
    ):
        return list(reversed(points))
    raise ValueError(
        f"Edge {edge_id} {attribute} endpoints do not match its incident node positions."
    )


def _trace_chains(graph: ig.Graph, degrees: Sequence[int]) -> tuple[list[_Chain], set[int]]:
    incident: list[list[tuple[int, int]]] = [[] for _ in range(graph.vcount())]
    for edge in graph.es:
        incident[edge.source].append((edge.index, edge.target))
        incident[edge.target].append((edge.index, edge.source))

    retained = {node for node, degree in enumerate(degrees) if degree != 2}
    cycle_anchors: set[int] = set()
    for component in graph.connected_components():
        if component and all(degrees[node] == 2 for node in component):
            anchor = min(component)
            retained.add(anchor)
            cycle_anchors.add(anchor)

    visited_edges: set[int] = set()
    chains: list[_Chain] = []
    for start in sorted(retained):
        for edge_id, next_node in incident[start]:
            if edge_id in visited_edges:
                continue
            visited_edges.add(edge_id)
            nodes = [start, next_node]
            edges = [edge_id]
            current = next_node

            while current not in retained:
                choices = [item for item in incident[current] if item[0] not in visited_edges]
                if len(choices) != 1:
                    raise ValueError(
                        "Unable to trace a unique degree-2 chain through "
                        f"node {current}; found {len(choices)} unused incident edges."
                    )
                next_edge, next_node = choices[0]
                visited_edges.add(next_edge)
                edges.append(next_edge)
                nodes.append(next_node)
                current = next_node

            chains.append(_Chain(tuple(nodes), tuple(edges)))

    if len(visited_edges) != graph.ecount():
        raise ValueError(
            f"Unable to trace all graph edges: visited {len(visited_edges)} of {graph.ecount()}."
        )
    return chains, cycle_anchors


def _concatenate_chain_path(
    graph: ig.Graph,
    chain: _Chain,
    positions: Sequence[np.ndarray],
    *,
    attribute: str,
    integer: bool,
) -> list[tuple[float, float, float]] | list[tuple[int, int, int]]:
    merged: list[tuple[float, float, float]] | list[tuple[int, int, int]] = []
    for path_index, edge_id in enumerate(chain.edges):
        points = _oriented_path(
            graph,
            edge_id,
            chain.nodes[path_index],
            chain.nodes[path_index + 1],
            positions,
            attribute=attribute,
            integer=integer,
        )
        if not merged:
            merged.extend(points)
            continue
        if not np.allclose(merged[-1], points[0], rtol=0.0, atol=1e-8):
            raise ValueError(f"Edge paths do not meet within chain at node {chain.nodes[path_index]}.")
        merged.extend(points[1:])
    return merged


def _common_chain_attribute(graph: ig.Graph, chain: _Chain, attribute: str) -> object:
    values = [graph.es[edge_id][attribute] for edge_id in chain.edges]
    first = values[0]
    if any(value != first for value in values[1:]):
        raise ValueError(
            f"Edges merged into one centreline have inconsistent '{attribute}' values."
        )
    return first


def _json_points(points: Sequence[Sequence[float | int]]) -> str:
    return json.dumps([list(point) for point in points], separators=(",", ":"))


def clean_protograph_graph(
    graph: ig.Graph,
    *,
    progress: NodeProgress | None = None,
) -> tuple[ig.Graph, ProtographCleaningStats]:
    """Remove degree-2 vertices while retaining their positions in merged edge paths."""
    if graph.is_directed():
        raise ValueError("Protograph cleaning requires an undirected GraphML graph.")
    if graph.vcount() == 0:
        raise ValueError("Input GraphML contains no nodes.")
    if graph.ecount() == 0:
        raise ValueError("Input GraphML contains no edges.")
    edge_attributes = set(graph.es.attributes())
    if "centerline_voxel_points" not in edge_attributes:
        raise ValueError("GraphML edges must provide 'centerline_voxel_points'.")

    degrees = graph.degree(loops=True)
    degree_two_nodes = sum(degree == 2 for degree in degrees)
    if degree_two_nodes == 0:
        raise ValueError("Input GraphML must contain at least one degree-2 node.")

    positions = _load_node_positions(graph, progress)
    chains, cycle_anchors = _trace_chains(graph, degrees)
    retained = sorted({chain.nodes[0] for chain in chains} | {chain.nodes[-1] for chain in chains})
    retained.extend(
        node
        for node, degree in enumerate(degrees)
        if degree == 0 and node not in retained
    )
    retained = sorted(set(retained))
    old_to_new = {old: new for new, old in enumerate(retained)}

    output = ig.Graph(directed=False)
    output.add_vertices(len(retained))
    # igraph reconstructs the GraphML XML node id as an ``id`` attribute.
    # Keeping it alongside the existing ``name`` attribute makes later reads
    # report a duplicate-id warning, so let the writer regenerate XML ids.
    copied_vertex_attributes = [
        attribute for attribute in graph.vs.attributes() if attribute != "id"
    ]
    for attribute in copied_vertex_attributes:
        output.vs[attribute] = [graph.vs[node][attribute] for node in retained]
    for attribute in graph.attributes():
        output[attribute] = graph[attribute]

    output.add_edges(
        [(old_to_new[chain.nodes[0]], old_to_new[chain.nodes[-1]]) for chain in chains]
    )

    continuous_paths = [
        _concatenate_chain_path(
            graph,
            chain,
            positions,
            attribute="centerline_voxel_points",
            integer=False,
        )
        for chain in chains
    ]
    output.es["centerline_voxel_points"] = [_json_points(path) for path in continuous_paths]

    has_discrete_paths = "centerline_voxels" in edge_attributes
    if has_discrete_paths:
        discrete_paths = [
            _concatenate_chain_path(
                graph,
                chain,
                positions,
                attribute="centerline_voxels",
                integer=True,
            )
            for chain in chains
        ]
        output.es["centerline_voxels"] = [_json_points(path) for path in discrete_paths]
        output.es["num_centerline_voxels"] = [len(path) for path in discrete_paths]

    for attribute in ("component_index", "component_label"):
        if attribute in edge_attributes:
            output.es[attribute] = [
                _common_chain_attribute(graph, chain, attribute) for chain in chains
            ]

    if "laplacian_edge_id" in edge_attributes:
        output.es["laplacian_edge_id"] = list(range(len(chains)))
    if "proto_edge_id" in edge_attributes:
        output.es["proto_edge_id"] = list(range(len(chains)))

    vertex_attributes = set(copied_vertex_attributes)
    if "laplacian_id" in vertex_attributes:
        laplacian_ids = [graph.vs[node]["laplacian_id"] for node in retained]
        if "source_laplacian_id" in edge_attributes:
            output.es["source_laplacian_id"] = [
                laplacian_ids[old_to_new[chain.nodes[0]]] for chain in chains
            ]
        if "target_laplacian_id" in edge_attributes:
            output.es["target_laplacian_id"] = [
                laplacian_ids[old_to_new[chain.nodes[-1]]] for chain in chains
            ]

    if "component_edge_index" in edge_attributes:
        component_attributes = [
            attribute
            for attribute in ("component_index", "component_label")
            if attribute in output.es.attributes()
        ]
        next_index: defaultdict[tuple[object, ...], int] = defaultdict(int)
        component_edge_indices: list[int] = []
        for edge in output.es:
            key = tuple(edge[attribute] for attribute in component_attributes)
            component_edge_indices.append(next_index[key])
            next_index[key] += 1
        output.es["component_edge_index"] = component_edge_indices

    endpoint_pairs = Counter(
        tuple(sorted((edge.source, edge.target))) for edge in output.es if edge.source != edge.target
    )
    parallel_path_pairs = sum(multiplicity > 1 for multiplicity in endpoint_pairs.values())
    stats = ProtographCleaningStats(
        input_nodes=graph.vcount(),
        input_edges=graph.ecount(),
        degree_two_nodes=degree_two_nodes,
        removed_nodes=degree_two_nodes - len(cycle_anchors),
        output_nodes=output.vcount(),
        output_edges=output.ecount(),
        parallel_path_pairs=parallel_path_pairs,
        retained_cycle_anchors=len(cycle_anchors),
    )
    return output, stats


def _require_graphml_path(path: str | Path, *, label: str) -> Path:
    candidate = Path(path).expanduser()
    if candidate.suffix.lower() != ".graphml":
        raise ValueError(f"{label} must have a .graphml extension: {candidate}")
    return candidate


def clean_protograph_file(
    input_path: str | Path,
    output_path: str | Path,
    *,
    overwrite: bool = False,
    progress: NodeProgress | None = None,
) -> ProtographCleaningStats:
    """Load, clean, and atomically write a GraphML proto-graph."""
    source = _require_graphml_path(input_path, label="Input")
    destination = _require_graphml_path(output_path, label="Output")
    if not source.is_file():
        raise FileNotFoundError(f"Input GraphML does not exist or is not a file: {source}")
    if source.resolve() == destination.resolve():
        raise ValueError("Input and output GraphML paths must be different.")
    if destination.exists() and not destination.is_file():
        raise ValueError(f"Output path exists but is not a file: {destination}")
    if destination.exists() and not overwrite:
        raise FileExistsError(f"Output GraphML already exists: {destination}")

    try:
        graph = ig.Graph.Read_GraphML(str(source))
    except Exception as exc:
        raise ValueError(f"Unable to read input GraphML '{source}': {exc}") from exc
    cleaned, stats = clean_protograph_graph(graph, progress=progress)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{destination.stem}-",
            suffix=".graphml",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temp_path = Path(temporary.name)
        cleaned.write_graphml(str(temp_path))
        os.replace(temp_path, destination)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    return stats


class _ProgressBar:
    def __init__(self, *, width: int = 32) -> None:
        self.width = width
        self.last_filled = -1

    def __call__(self, processed: int, total: int) -> None:
        fraction = processed / total if total else 1.0
        filled = min(self.width, int(fraction * self.width))
        if filled == self.last_filled and processed != total:
            return
        self.last_filled = filled
        bar = "#" * filled + "-" * (self.width - filled)
        print(
            f"\rProcessing nodes [{bar}] {processed}/{total} ({fraction:6.2%})",
            end="\n" if processed == total else "",
            file=sys.stderr,
            flush=True,
        )


def _prompt_for_overwrite(path: Path) -> bool:
    try:
        response = input(f"Output file already exists: {path}\nOverwrite it? [y/N]: ")
    except EOFError:
        return False
    return response.strip().lower() in {"y", "yes"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Remove degree-2 GraphML nodes and preserve their positions as ordered "
            "points inside merged centreline edges."
        )
    )
    parser.add_argument("-i", "--input", required=True, help="Input GraphML containing degree-2 nodes.")
    parser.add_argument("-o", "--output", required=True, help="Output path for the cleaned GraphML.")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show node-processing progress and a cleaning summary.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_path = Path(args.output).expanduser()
    overwrite = False
    if output_path.exists():
        if not output_path.is_file():
            print(f"Error: output path exists but is not a file: {output_path}", file=sys.stderr)
            return 1
        overwrite = _prompt_for_overwrite(output_path)
        if not overwrite:
            print("Cancelled; the existing output file was not changed.", file=sys.stderr)
            return 0

    if args.verbose:
        print(f"Loading GraphML: {Path(args.input).expanduser()}", file=sys.stderr)
    try:
        stats = clean_protograph_file(
            args.input,
            output_path,
            overwrite=overwrite,
            progress=_ProgressBar() if args.verbose else None,
        )
    except (FileNotFoundError, FileExistsError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.verbose:
        print(
            "Cleaned GraphML: "
            f"nodes {stats.input_nodes} -> {stats.output_nodes}; "
            f"edges {stats.input_edges} -> {stats.output_edges}; "
            f"removed degree-2 nodes={stats.removed_nodes}; "
            f"parallel endpoint pairs preserved={stats.parallel_path_pairs}.",
            file=sys.stderr,
        )
        if stats.retained_cycle_anchors:
            print(
                "Retained one anchor node for each closed degree-2-only component: "
                f"{stats.retained_cycle_anchors}.",
                file=sys.stderr,
            )
    print(f"Wrote cleaned GraphML: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
