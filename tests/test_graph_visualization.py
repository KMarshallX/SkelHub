"""Tests for GraphML visualization loading and PyVista rendering setup."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from skelhub.cli.main import build_parser
from skelhub.visualization import (
    GraphVisualizationData,
    GraphVisualizationError,
    GraphVisualizationOptions,
    build_graph_meshes,
    build_graph_plotter,
    launch_graph_viewer,
    load_graph_visualization_data,
)
from skelhub.visualization import graph_viewer


def _write_graphml(
    path: Path,
    coords: list[tuple[object, object, object]],
    *,
    coordinate_names: tuple[str, str, str] = ("X", "Y", "Z"),
    coordinate_type: str = "double",
) -> None:
    key_ids = ("xkey", "ykey", "zkey")
    node_xml = []
    for index, (x_val, y_val, z_val) in enumerate(coords):
        node_xml.append(
            f"""    <node id="n{index}">
      <data key="{key_ids[0]}">{x_val}</data>
      <data key="{key_ids[1]}">{y_val}</data>
      <data key="{key_ids[2]}">{z_val}</data>
    </node>"""
        )

    edge_xml = []
    for index in range(max(len(coords) - 1, 0)):
        edge_xml.append(f'    <edge id="e{index}" source="n{index}" target="n{index + 1}"/>')

    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
"""
        + "\n".join(
            f'  <key id="{key_id}" for="node" attr.name="{name}" attr.type="{coordinate_type}"/>'
            for key_id, name in zip(key_ids, coordinate_names)
        )
        + """
  <graph id="G" edgedefault="undirected">
"""
        + "\n".join(node_xml)
        + ("\n" if node_xml else "")
        + "\n".join(edge_xml)
        + """
  </graph>
</graphml>
""",
        encoding="utf-8",
    )


class _FakeMesh:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakePolyData:
    def __init__(self, points: np.ndarray) -> None:
        self.points = np.asarray(points)
        self.lines: np.ndarray | None = None

    def glyph(self, *, geom: Any, orient: bool, scale: bool) -> _FakeMesh:
        assert orient is False
        return _FakeMesh(f"glyph:{geom.radius}:{scale}")

    def tube(self, *, radius: float, n_sides: int) -> _FakeMesh:
        return _FakeMesh(f"tube:{radius}:{n_sides}")


class _FakeSphere:
    def __init__(self, *, radius: float) -> None:
        self.radius = radius


class _FakePlotter:
    instances: list["_FakePlotter"] = []

    def __init__(self, *, title: str, off_screen: bool = False) -> None:
        self.title = title
        self.off_screen = off_screen
        self.meshes: list[tuple[Any, dict[str, Any]]] = []
        self.background: str | None = None
        self.axes_added = False
        self.camera_reset = False
        self.shown = False
        _FakePlotter.instances.append(self)

    def set_background(self, color: str) -> None:
        self.background = color

    def add_axes(self) -> None:
        self.axes_added = True

    def add_mesh(self, mesh: Any, **kwargs: Any) -> None:
        self.meshes.append((mesh, kwargs))

    def reset_camera(self) -> None:
        self.camera_reset = True

    def show(self) -> None:
        self.shown = True


class _FakePyVista:
    PolyData = _FakePolyData
    Sphere = _FakeSphere
    Plotter = _FakePlotter


def test_load_graph_visualization_data_reads_xyz_coordinates(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.graphml"
    _write_graphml(graph_path, [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)])

    graph_data = load_graph_visualization_data(graph_path)

    assert graph_data.node_count == 2
    assert graph_data.edge_count == 1
    assert graph_data.node_positions.tolist() == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    assert graph_data.edge_indices.tolist() == [[0, 1]]


def test_load_graph_visualization_data_reads_lowercase_coordinates(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.graphml"
    _write_graphml(graph_path, [(1.0, 2.0, 3.0)], coordinate_names=("x", "y", "z"))

    graph_data = load_graph_visualization_data(graph_path)

    assert graph_data.node_positions.tolist() == [[1.0, 2.0, 3.0]]


def test_load_graph_visualization_data_requires_coordinates(tmp_path: Path) -> None:
    graph_path = tmp_path / "missing_coords.graphml"
    graph_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <graph id="G" edgedefault="undirected">
    <node id="n0"/>
  </graph>
</graphml>
""",
        encoding="utf-8",
    )

    with pytest.raises(GraphVisualizationError, match="Expected node attributes 'X', 'Y', 'Z'"):
        load_graph_visualization_data(graph_path)


def test_load_graph_visualization_data_rejects_non_numeric_coordinates(tmp_path: Path) -> None:
    graph_path = tmp_path / "bad_coords.graphml"
    _write_graphml(graph_path, [("not-a-number", 2.0, 3.0)], coordinate_type="string")

    with pytest.raises(GraphVisualizationError, match="must be numeric"):
        load_graph_visualization_data(graph_path)


def test_load_graph_visualization_data_rejects_empty_graph(tmp_path: Path) -> None:
    graph_path = tmp_path / "empty.graphml"
    _write_graphml(graph_path, [])

    with pytest.raises(GraphVisualizationError, match="does not contain any nodes"):
        load_graph_visualization_data(graph_path)


def test_build_graph_meshes_creates_nodes_and_edges() -> None:
    graph_data = GraphVisualizationData(
        node_positions=np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=float),
        edge_indices=np.asarray([[0, 1]], dtype=int),
        node_count=2,
        edge_count=1,
        source_path="memory.graphml",
    )

    meshes = build_graph_meshes(
        graph_data,
        GraphVisualizationOptions(edge_thickness=2.5, node_size=7.0),
        pv_module=_FakePyVista,
    )

    assert meshes.nodes is not None
    assert meshes.edges is not None
    assert meshes.nodes.name == "glyph:7.0:False"
    assert meshes.edges.name == "tube:2.5:12"


def test_build_graph_meshes_handles_zero_edges() -> None:
    graph_data = GraphVisualizationData(
        node_positions=np.asarray([[0.0, 0.0, 0.0]], dtype=float),
        edge_indices=np.empty((0, 2), dtype=int),
        node_count=1,
        edge_count=0,
        source_path="memory.graphml",
    )

    meshes = build_graph_meshes(graph_data, GraphVisualizationOptions(), pv_module=_FakePyVista)

    assert meshes.nodes is not None
    assert meshes.edges is None


def test_build_graph_plotter_populates_graph_scene() -> None:
    _FakePlotter.instances.clear()
    graph_data = GraphVisualizationData(
        node_positions=np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=float),
        edge_indices=np.asarray([[0, 1]], dtype=int),
        node_count=2,
        edge_count=1,
        source_path="memory.graphml",
    )

    plotter = build_graph_plotter(graph_data, GraphVisualizationOptions(), pv_module=_FakePyVista)

    assert plotter.background == "white"
    assert plotter.axes_added is True
    assert plotter.camera_reset is True
    assert len(plotter.meshes) == 2


def test_launch_graph_viewer_without_input_starts_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakePlotter.instances.clear()
    monkeypatch.setattr(graph_viewer, "_import_pyvista", lambda: _FakePyVista)

    result = launch_graph_viewer(None)

    assert result == 0
    assert len(_FakePlotter.instances) == 1
    assert _FakePlotter.instances[0].shown is True
    assert _FakePlotter.instances[0].meshes == []


def test_launch_graph_viewer_with_input_loads_graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakePlotter.instances.clear()
    graph_path = tmp_path / "graph.graphml"
    _write_graphml(graph_path, [(0.0, 0.0, 0.0), (1.0, 2.0, 3.0)])
    monkeypatch.setattr(graph_viewer, "_import_pyvista", lambda: _FakePyVista)

    result = launch_graph_viewer(graph_path)

    assert result == 0
    assert _FakePlotter.instances[0].shown is True
    assert len(_FakePlotter.instances[0].meshes) == 2


def test_launch_graph_viewer_validates_appearance_options() -> None:
    with pytest.raises(GraphVisualizationError, match="edge_thickness"):
        launch_graph_viewer(None, edge_thickness=0)
    with pytest.raises(GraphVisualizationError, match="node_size"):
        launch_graph_viewer(None, node_size=0)


def test_missing_pyvista_reports_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_import_error(_name: str) -> Any:
        raise ImportError("No module named 'pyvista'")

    monkeypatch.setattr(graph_viewer.importlib, "import_module", _raise_import_error)

    with pytest.raises(GraphVisualizationError, match="PyVista graph visualization could not be initialized"):
        graph_viewer._import_pyvista()


def test_cli_graphviz_help_mentions_pyvista() -> None:
    parser = build_parser()
    assert "PyVista" in parser.format_help()
