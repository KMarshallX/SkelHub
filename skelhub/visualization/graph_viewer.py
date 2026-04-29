"""PyVista-based GraphML viewer for 3D vessel graphs."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
from pathlib import Path
from typing import Any, Sequence

import igraph as ig
import numpy as np


class GraphVisualizationError(RuntimeError):
    """Raised when a graph cannot be prepared or displayed."""


@dataclass(slots=True)
class GraphVisualizationData:
    """Graph coordinates and topology prepared for rendering."""

    node_positions: np.ndarray
    edge_indices: np.ndarray
    node_count: int
    edge_count: int
    source_path: str


@dataclass(slots=True)
class GraphVisualizationOptions:
    """User-configurable graph appearance."""

    edge_thickness: float = 2.0
    node_size: float = 6.0
    window_title: str = "SkelHub Graph Viewer"


@dataclass(slots=True)
class GraphVisualizationMeshes:
    """PyVista meshes built from graph visualization data."""

    nodes: Any | None
    edges: Any | None


def _coerce_coordinate_array(
    values: Sequence[object],
    *,
    axis_name: str,
    node_count: int,
) -> np.ndarray:
    try:
        coords = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise GraphVisualizationError(
            f"GraphML node attribute '{axis_name}' must be numeric for all {node_count} nodes."
        ) from exc

    if coords.shape != (node_count,):
        raise GraphVisualizationError(
            f"GraphML node attribute '{axis_name}' must contain exactly one value per node."
        )

    return coords


def _positions_from_xyz(graph: ig.Graph, attribute_names: tuple[str, str, str]) -> np.ndarray | None:
    x_name, y_name, z_name = attribute_names
    available = set(graph.vs.attribute_names())
    if not {x_name, y_name, z_name}.issubset(available):
        return None

    node_count = graph.vcount()
    x_vals = _coerce_coordinate_array(graph.vs[x_name], axis_name=x_name, node_count=node_count)
    y_vals = _coerce_coordinate_array(graph.vs[y_name], axis_name=y_name, node_count=node_count)
    z_vals = _coerce_coordinate_array(graph.vs[z_name], axis_name=z_name, node_count=node_count)
    return np.column_stack((x_vals, y_vals, z_vals))


def _extract_node_positions(graph: ig.Graph) -> np.ndarray:
    for attribute_names in (("X", "Y", "Z"), ("x", "y", "z")):
        positions = _positions_from_xyz(graph, attribute_names)
        if positions is not None:
            return positions

    raise GraphVisualizationError(
        "GraphML file does not contain renderable 3D coordinates. "
        "Expected node attributes 'X', 'Y', 'Z'."
    )


def _extract_edge_indices(graph: ig.Graph) -> np.ndarray:
    if graph.ecount() == 0:
        return np.empty((0, 2), dtype=int)
    return np.asarray([edge.tuple for edge in graph.es], dtype=int)


def _validate_graph_data(node_positions: np.ndarray, edge_indices: np.ndarray) -> None:
    if node_positions.shape[0] == 0:
        raise GraphVisualizationError("GraphML file does not contain any nodes to render.")
    if not np.isfinite(node_positions).all():
        raise GraphVisualizationError("GraphML file contains non-finite node coordinates and cannot be rendered.")
    if edge_indices.size and (edge_indices.min() < 0 or edge_indices.max() >= node_positions.shape[0]):
        raise GraphVisualizationError("GraphML file contains an edge referencing a missing node.")


def load_graph_visualization_data(input_path: str | Path) -> GraphVisualizationData:
    """Load GraphML node coordinates and edge pairs for PyVista rendering."""
    graph_path = Path(input_path)
    if not graph_path.is_file():
        raise GraphVisualizationError(f"GraphML input does not exist: {graph_path}")

    try:
        graph = ig.Graph.Read_GraphML(str(graph_path))
    except Exception as exc:  # pragma: no cover - igraph raises several concrete types
        raise GraphVisualizationError(f"Failed to load GraphML file '{graph_path}': {exc}") from exc

    node_positions = _extract_node_positions(graph)
    edge_indices = _extract_edge_indices(graph)
    _validate_graph_data(node_positions, edge_indices)
    return GraphVisualizationData(
        node_positions=node_positions,
        edge_indices=edge_indices,
        node_count=graph.vcount(),
        edge_count=graph.ecount(),
        source_path=str(graph_path),
    )


def _import_pyvista() -> Any:
    try:
        return importlib.import_module("pyvista")
    except ImportError as exc:
        raise GraphVisualizationError(
            "PyVista graph visualization could not be initialized. "
            "Install the visualization dependency with `python -m pip install -e .`."
        ) from exc


def _validate_options(options: GraphVisualizationOptions) -> None:
    if options.edge_thickness <= 0:
        raise GraphVisualizationError("--edge_thickness must be greater than zero.")
    if options.node_size <= 0:
        raise GraphVisualizationError("--node_size must be greater than zero.")


def _edge_polyline_array(edge_indices: np.ndarray) -> np.ndarray:
    if edge_indices.size == 0:
        return np.empty(0, dtype=int)
    line_sizes = np.full((edge_indices.shape[0], 1), 2, dtype=int)
    return np.hstack((line_sizes, edge_indices)).ravel()


def build_graph_meshes(
    graph_data: GraphVisualizationData,
    options: GraphVisualizationOptions,
    *,
    pv_module: Any | None = None,
) -> GraphVisualizationMeshes:
    """Build simple PyVista node and edge meshes from graph data."""
    _validate_options(options)
    pv = _import_pyvista() if pv_module is None else pv_module

    node_cloud = pv.PolyData(graph_data.node_positions)
    node_mesh = node_cloud.glyph(
        geom=pv.Sphere(radius=float(options.node_size)),
        orient=False,
        scale=False,
    )

    edge_mesh = None
    if graph_data.edge_indices.size:
        line_data = pv.PolyData(graph_data.node_positions)
        line_data.lines = _edge_polyline_array(graph_data.edge_indices)
        edge_mesh = line_data.tube(radius=float(options.edge_thickness), n_sides=12)

    return GraphVisualizationMeshes(nodes=node_mesh, edges=edge_mesh)


def build_graph_plotter(
    graph_data: GraphVisualizationData | None,
    options: GraphVisualizationOptions,
    *,
    pv_module: Any | None = None,
    off_screen: bool = False,
) -> Any:
    """Create a PyVista plotter containing an optional graph scene."""
    _validate_options(options)
    pv = _import_pyvista() if pv_module is None else pv_module
    plotter = pv.Plotter(title=options.window_title, off_screen=off_screen)
    plotter.set_background("white")
    plotter.add_axes()

    if graph_data is not None:
        meshes = build_graph_meshes(graph_data, options, pv_module=pv)
        if meshes.edges is not None:
            plotter.add_mesh(meshes.edges, color="forestgreen", smooth_shading=True)
        if meshes.nodes is not None:
            plotter.add_mesh(meshes.nodes, color="crimson", smooth_shading=True)
        plotter.reset_camera()

    return plotter


def launch_graph_viewer(
    input_path: str | Path | None = None,
    *,
    edge_thickness: float = 2.0,
    node_size: float = 6.0,
) -> int:
    """Launch an interactive PyVista window for an optional GraphML file."""
    options = GraphVisualizationOptions(edge_thickness=edge_thickness, node_size=node_size)
    _validate_options(options)
    graph_data = load_graph_visualization_data(input_path) if input_path is not None else None
    plotter = build_graph_plotter(graph_data, options)
    plotter.show()
    return 0
