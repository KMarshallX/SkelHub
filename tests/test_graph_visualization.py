"""Tests for GraphML visualization loading and PyVista rendering setup."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
import pytest

from skelhub.cli.main import build_parser
from skelhub.visualization import (
    GraphVisualizationData,
    GraphVisualizationError,
    GraphVisualizationOptions,
    NiftiVisualizationData,
    build_graph_meshes,
    build_graph_plotter,
    build_nifti_meshes,
    close_active_graph,
    create_graph_viewer_session,
    handle_dropped_graphml_paths,
    handle_dropped_visualization_paths,
    launch_graph_viewer,
    load_graph_visualization_data,
    load_nifti_visualization_data,
    refresh_active_graph,
    render_active_graph,
    switch_next_graph,
    switch_previous_graph,
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


def _write_nifti(path: Path, data: np.ndarray) -> None:
    image = nib.Nifti1Image(np.asarray(data), affine=np.eye(4, dtype=float))
    nib.save(image, str(path))


class _FakeMesh:
    def __init__(self, name: str) -> None:
        self.name = name
        self.text_property = _FakeTextProperty()

    def GetTextProperty(self) -> "_FakeTextProperty":
        return self.text_property


class _FakeTextProperty:
    def __init__(self) -> None:
        self.background_color: tuple[float, float, float] | None = None
        self.background_opacity: float | None = None
        self.frame = False
        self.frame_width: int | None = None
        self.frame_color: tuple[float, float, float] | None = None

    def SetBackgroundColor(self, *color: float) -> None:
        self.background_color = tuple(color)

    def SetBackgroundOpacity(self, opacity: float) -> None:
        self.background_opacity = opacity

    def SetFrame(self, frame: bool) -> None:
        self.frame = frame

    def SetFrameWidth(self, width: int) -> None:
        self.frame_width = width

    def SetFrameColor(self, *color: float) -> None:
        self.frame_color = tuple(color)


class _FakeCamera:
    def __init__(self) -> None:
        self.position = (1.0, 2.0, 3.0)
        self.focal_point = (0.0, 0.0, 0.0)
        self.up = (0.0, 1.0, 0.0)
        self.clipping_range = (0.1, 1000.0)
        self.parallel_scale = 1.0

    def GetPosition(self) -> tuple[float, float, float]:
        return self.position

    def SetPosition(self, *value: float) -> None:
        self.position = tuple(value)  # type: ignore[assignment]

    def GetFocalPoint(self) -> tuple[float, float, float]:
        return self.focal_point

    def SetFocalPoint(self, *value: float) -> None:
        self.focal_point = tuple(value)  # type: ignore[assignment]

    def GetViewUp(self) -> tuple[float, float, float]:
        return self.up

    def SetViewUp(self, *value: float) -> None:
        self.up = tuple(value)  # type: ignore[assignment]

    def GetClippingRange(self) -> tuple[float, float]:
        return self.clipping_range

    def SetClippingRange(self, *value: float) -> None:
        self.clipping_range = tuple(value)  # type: ignore[assignment]

    def GetParallelScale(self) -> float:
        return self.parallel_scale

    def SetParallelScale(self, value: float) -> None:
        self.parallel_scale = value


class _FakePolyData:
    def __init__(self, points: np.ndarray) -> None:
        self.points = np.asarray(points)
        self.lines: np.ndarray | None = None

    def glyph(self, *, geom: Any, orient: bool, scale: bool) -> _FakeMesh:
        assert orient is False
        return _FakeMesh(f"glyph:{geom.radius}:{scale}")

    def tube(self, *, radius: float, n_sides: int) -> _FakeMesh:
        return _FakeMesh(f"tube:{radius}:{n_sides}")


class _FakeCube:
    def __init__(self, *, x_length: float, y_length: float, z_length: float) -> None:
        self.radius = f"cube:{x_length}:{y_length}:{z_length}"


class _FakeSphere:
    def __init__(self, *, radius: float) -> None:
        self.radius = radius


class _FakeInteractor:
    def __init__(self) -> None:
        self.observers: list[tuple[str, Any]] = []

    def add_observer(self, event_name: str, callback: Any) -> None:
        self.observers.append((event_name, callback))


class _FakePlotter:
    instances: list["_FakePlotter"] = []

    def __init__(self, *, title: str, off_screen: bool = False) -> None:
        self.title = title
        self.off_screen = off_screen
        self.meshes: list[tuple[Any, dict[str, Any]]] = []
        self.background: str | None = None
        self.axes_added = False
        self.camera_reset = False
        self.reset_count = 0
        self.camera = _FakeCamera()
        self.shown = False
        self.rendered = False
        self.removed_actors: list[Any] = []
        self.rectangles: list[dict[str, Any]] = []
        self.texts: list[tuple[str, dict[str, Any]]] = []
        self.text_actors: list[_FakeMesh] = []
        self.buttons: list[tuple[Any, dict[str, Any]]] = []
        self.sliders: list[tuple[Any, dict[str, Any]]] = []
        self.iren = _FakeInteractor()
        self.window_size = (1280, 800)
        _FakePlotter.instances.append(self)

    def set_background(self, color: str) -> None:
        self.background = color

    def add_axes(self) -> None:
        self.axes_added = True

    def add_mesh(self, mesh: Any, **kwargs: Any) -> None:
        actor = _FakeMesh(f"actor:{mesh.name}")
        self.meshes.append((mesh, kwargs))
        return actor

    def remove_actor(self, actor: Any, **_kwargs: Any) -> None:
        self.removed_actors.append(actor)

    def reset_camera(self) -> None:
        self.camera_reset = True
        self.reset_count += 1
        self.camera.position = (10.0, 20.0, 30.0)
        self.camera.focal_point = (1.0, 1.0, 1.0)
        self.camera.up = (0.0, 0.0, 1.0)
        self.camera.clipping_range = (0.2, 2000.0)
        self.camera.parallel_scale = 2.0

    def render(self) -> None:
        self.rendered = True

    def add_text(self, text: str, **kwargs: Any) -> _FakeMesh:
        actor = _FakeMesh(f"text:{text}")
        self.texts.append((text, kwargs))
        self.text_actors.append(actor)
        return actor

    def add_overlay_rect(
        self,
        *,
        x: int,
        y: int,
        width: int,
        height: int,
        color: tuple[float, float, float],
        opacity: float,
    ) -> _FakeMesh:
        actor = _FakeMesh(f"rect:{x}:{y}:{width}:{height}")
        self.rectangles.append(
            {
                "actor": actor,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "color": color,
                "opacity": opacity,
            }
        )
        return actor

    def add_checkbox_button_widget(self, callback: Any, **kwargs: Any) -> None:
        self.buttons.append((callback, kwargs))

    def add_slider_widget(self, callback: Any, rng: Any, **kwargs: Any) -> None:
        self.sliders.append((callback, {"rng": rng, **kwargs}))
        return None

    def clear_slider_widgets(self) -> None:
        self.sliders.clear()

    def show(self) -> None:
        self.shown = True


class _FakePyVista:
    PolyData = _FakePolyData
    Sphere = _FakeSphere
    Cube = _FakeCube
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


def test_load_nifti_visualization_data_accepts_binary_integer_volume(tmp_path: Path) -> None:
    nifti_path = tmp_path / "mask.nii.gz"
    volume = np.zeros((2, 3, 4), dtype=np.uint8)
    volume[0, 1, 2] = 1
    volume[1, 2, 3] = 1
    _write_nifti(nifti_path, volume)

    nifti_data = load_nifti_visualization_data(nifti_path)

    assert nifti_data.shape == (2, 3, 4)
    assert nifti_data.voxel_count == 2
    assert nifti_data.voxel_positions.tolist() == [[0.0, 1.0, 2.0], [1.0, 2.0, 3.0]]


def test_load_nifti_visualization_data_accepts_binary_float_volume(tmp_path: Path) -> None:
    nifti_path = tmp_path / "skeleton.nii"
    volume = np.zeros((2, 2, 2), dtype=np.float32)
    volume[1, 1, 1] = 1.0
    _write_nifti(nifti_path, volume)

    nifti_data = load_nifti_visualization_data(nifti_path)

    assert nifti_data.voxel_count == 1
    assert nifti_data.voxel_positions.tolist() == [[1.0, 1.0, 1.0]]


def test_load_nifti_visualization_data_rejects_non_binary_float_values(tmp_path: Path) -> None:
    nifti_path = tmp_path / "fuzzy.nii.gz"
    volume = np.zeros((2, 2, 2), dtype=np.float32)
    volume[0, 0, 0] = 0.5
    _write_nifti(nifti_path, volume)

    with pytest.raises(GraphVisualizationError, match="must be binarized"):
        load_nifti_visualization_data(nifti_path)


def test_load_nifti_visualization_data_rejects_non_3d_volume(tmp_path: Path) -> None:
    nifti_path = tmp_path / "slice.nii"
    _write_nifti(nifti_path, np.zeros((2, 2), dtype=np.uint8))

    with pytest.raises(GraphVisualizationError, match="3D volume"):
        load_nifti_visualization_data(nifti_path)


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


def test_build_nifti_meshes_creates_voxel_blocks() -> None:
    nifti_data = NiftiVisualizationData(
        voxel_positions=np.asarray([[0.0, 0.0, 0.0], [1.0, 2.0, 3.0]], dtype=float),
        voxel_count=2,
        shape=(2, 3, 4),
        source_path="memory.nii.gz",
    )

    meshes = build_nifti_meshes(nifti_data, pv_module=_FakePyVista)

    assert meshes.blocks is not None
    assert meshes.blocks.name == "glyph:cube:1.0:1.0:1.0:False"


def test_build_nifti_meshes_handles_empty_foreground() -> None:
    nifti_data = NiftiVisualizationData(
        voxel_positions=np.empty((0, 3), dtype=float),
        voxel_count=0,
        shape=(2, 3, 4),
        source_path="empty.nii.gz",
    )

    meshes = build_nifti_meshes(nifti_data, pv_module=_FakePyVista)

    assert meshes.blocks is None


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


def test_graph_viewer_session_starts_empty() -> None:
    session = create_graph_viewer_session(None)

    assert session.loaded_files == []
    assert session.active_index is None
    assert session.active_graph_data is None
    assert session.status_text() == "No file loaded"


def test_graph_viewer_session_initial_input_becomes_active(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.graphml"
    _write_graphml(graph_path, [(0.0, 0.0, 0.0)])

    session = create_graph_viewer_session(graph_path, edge_thickness=3.5, node_size=8.5)

    assert len(session.loaded_files) == 1
    assert session.active_index == 0
    assert session.active_file is not None
    assert session.active_file.path == graph_path.resolve()
    assert session.options.edge_thickness == 3.5
    assert session.options.node_size == 8.5


def test_graph_viewer_session_initial_nifti_input_becomes_active(tmp_path: Path) -> None:
    nifti_path = tmp_path / "mask.nii.gz"
    volume = np.zeros((2, 2, 2), dtype=np.uint8)
    volume[1, 0, 1] = 1
    _write_nifti(nifti_path, volume)

    session = create_graph_viewer_session(nifti_path)

    assert len(session.loaded_files) == 1
    assert session.active_file is not None
    assert session.active_file.kind == "nifti"
    assert session.active_nifti_data is not None
    assert session.active_nifti_data.voxel_count == 1
    assert session.active_graph_data is None


def test_graph_viewer_session_loading_multiple_files_displays_one_active_graph(tmp_path: Path) -> None:
    graph_a = tmp_path / "a.graphml"
    graph_b = tmp_path / "b.graphml"
    _write_graphml(graph_a, [(0.0, 0.0, 0.0)])
    _write_graphml(graph_b, [(1.0, 0.0, 0.0), (2.0, 0.0, 0.0)])
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(None)

    handle_dropped_graphml_paths(plotter, session, [graph_a, graph_b], pv_module=_FakePyVista)

    assert len(session.loaded_files) == 2
    assert session.active_file is not None
    assert session.active_file.path == graph_a.resolve()
    assert session.active_graph_data is not None
    assert session.active_graph_data.node_count == 1
    assert len(plotter.meshes) == 1


def test_graph_viewer_session_loads_graphml_and_nifti_together(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.graphml"
    nifti_path = tmp_path / "mask.nii.gz"
    _write_graphml(graph_path, [(0.0, 0.0, 0.0)])
    volume = np.zeros((2, 2, 2), dtype=np.uint8)
    volume[0, 1, 1] = 1
    _write_nifti(nifti_path, volume)
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(None)

    loaded = handle_dropped_visualization_paths(
        plotter,
        session,
        [graph_path, nifti_path],
        pv_module=_FakePyVista,
    )

    assert len(loaded) == 2
    assert [loaded_file.kind for loaded_file in session.loaded_files] == ["graphml", "nifti"]
    assert session.active_file is not None
    assert session.active_file.path == graph_path.resolve()
    assert len(plotter.meshes) == 1


def test_graph_viewer_session_duplicate_load_reactivates_existing_file(tmp_path: Path) -> None:
    graph_a = tmp_path / "a.graphml"
    graph_b = tmp_path / "b.graphml"
    _write_graphml(graph_a, [(0.0, 0.0, 0.0)])
    _write_graphml(graph_b, [(1.0, 0.0, 0.0)])
    session = create_graph_viewer_session(None)

    session.load_graph(graph_a)
    session.load_graph(graph_b)
    session.load_graph(graph_a)

    assert len(session.loaded_files) == 2
    assert session.active_index == 0


def test_graph_viewer_session_duplicate_nifti_load_reactivates_existing_file(tmp_path: Path) -> None:
    nifti_a = tmp_path / "a.nii.gz"
    nifti_b = tmp_path / "b.nii"
    _write_nifti(nifti_a, np.ones((1, 1, 1), dtype=np.uint8))
    _write_nifti(nifti_b, np.ones((1, 1, 1), dtype=np.uint8))
    session = create_graph_viewer_session(None)

    session.load_visualization(nifti_a)
    session.load_visualization(nifti_b)
    session.load_visualization(nifti_a)

    assert len(session.loaded_files) == 2
    assert session.active_index == 0


def test_graph_viewer_session_prev_next_wrap(tmp_path: Path) -> None:
    graph_a = tmp_path / "a.graphml"
    graph_b = tmp_path / "b.graphml"
    _write_graphml(graph_a, [(0.0, 0.0, 0.0)])
    _write_graphml(graph_b, [(1.0, 0.0, 0.0)])
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(None)
    session.load_graph(graph_a)
    session.load_graph(graph_b)

    switch_next_graph(plotter, session, pv_module=_FakePyVista)
    assert session.active_index == 0
    switch_previous_graph(plotter, session, pv_module=_FakePyVista)
    assert session.active_index == 1


def test_close_active_graph_updates_active_selection_or_empty_state(tmp_path: Path) -> None:
    graph_a = tmp_path / "a.graphml"
    graph_b = tmp_path / "b.graphml"
    _write_graphml(graph_a, [(0.0, 0.0, 0.0)])
    _write_graphml(graph_b, [(1.0, 0.0, 0.0)])
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(None)
    session.load_graph(graph_a)
    session.load_graph(graph_b)

    close_active_graph(plotter, session, pv_module=_FakePyVista)
    assert len(session.loaded_files) == 1
    assert session.active_index == 0
    assert session.active_file is not None
    assert session.active_file.path == graph_a.resolve()

    close_active_graph(plotter, session, pv_module=_FakePyVista)
    assert session.loaded_files == []
    assert session.active_index is None
    assert session.active_graph_data is None


def test_slider_preview_updates_session_without_rebuild_until_refresh(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.graphml"
    _write_graphml(graph_path, [(0.0, 0.0, 0.0)])
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(graph_path, edge_thickness=2.0, node_size=6.0)
    render_active_graph(plotter, session, pv_module=_FakePyVista)
    mesh_count = len(plotter.meshes)

    session.set_preview_node_size(9.0)
    session.set_preview_edge_thickness(3.0)

    assert session.options.node_size == 6.0
    assert session.options.edge_thickness == 2.0
    assert len(plotter.meshes) == mesh_count


def test_refresh_rebuilds_graph_with_latest_slider_values(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.graphml"
    _write_graphml(graph_path, [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)])
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(graph_path, edge_thickness=2.0, node_size=6.0)
    render_active_graph(plotter, session, pv_module=_FakePyVista)

    session.set_preview_node_size(9.0)
    session.set_preview_edge_thickness(3.0)
    refresh_active_graph(plotter, session, pv_module=_FakePyVista)

    assert session.options.node_size == 9.0
    assert session.options.edge_thickness == 3.0
    assert plotter.removed_actors
    assert plotter.meshes[-2][0].name == "tube:3.0:12"
    assert plotter.meshes[-1][0].name == "glyph:9.0:False"


def test_render_active_nifti_creates_block_actor(tmp_path: Path) -> None:
    nifti_path = tmp_path / "mask.nii.gz"
    volume = np.zeros((2, 2, 2), dtype=np.uint8)
    volume[0, 0, 1] = 1
    _write_nifti(nifti_path, volume)
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(nifti_path)

    render_active_graph(plotter, session, pv_module=_FakePyVista)

    assert len(plotter.meshes) == 1
    assert plotter.meshes[0][0].name == "glyph:cube:1.0:1.0:1.0:False"
    assert plotter.meshes[0][1]["color"] == "#4c78a8"


def test_render_empty_nifti_foreground_resets_camera_without_mesh(tmp_path: Path) -> None:
    nifti_path = tmp_path / "empty.nii.gz"
    _write_nifti(nifti_path, np.zeros((2, 2, 2), dtype=np.uint8))
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(nifti_path)

    render_active_graph(plotter, session, pv_module=_FakePyVista)

    assert plotter.meshes == []
    assert plotter.reset_count == 1


def test_drag_drop_handler_accepts_graphml_and_rejects_other_paths(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.graphml"
    text_path = tmp_path / "notes.txt"
    _write_graphml(graph_path, [(0.0, 0.0, 0.0)])
    text_path.write_text("not graphml", encoding="utf-8")
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(None)

    loaded = handle_dropped_graphml_paths(plotter, session, [text_path, graph_path], pv_module=_FakePyVista)

    assert len(loaded) == 1
    assert len(session.loaded_files) == 1
    assert session.active_file is not None
    assert session.active_file.path == graph_path.resolve()


def test_drag_drop_handler_accepts_nifti_and_rejects_other_paths(tmp_path: Path) -> None:
    nifti_path = tmp_path / "mask.nii.gz"
    text_path = tmp_path / "notes.txt"
    _write_nifti(nifti_path, np.ones((1, 1, 1), dtype=np.uint8))
    text_path.write_text("not supported", encoding="utf-8")
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(None)

    loaded = handle_dropped_visualization_paths(plotter, session, [text_path, nifti_path], pv_module=_FakePyVista)

    assert len(loaded) == 1
    assert len(session.loaded_files) == 1
    assert session.active_file is not None
    assert session.active_file.kind == "nifti"
    assert session.active_file.path == nifti_path.resolve()


def test_large_nifti_drop_requires_confirmation_or_bypass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nifti_path = tmp_path / "large.nii.gz"
    _write_nifti(nifti_path, np.ones((2, 2, 2), dtype=np.uint8))
    monkeypatch.setattr(graph_viewer, "LARGE_NIFTI_VOXEL_WARNING_THRESHOLD", 1)
    monkeypatch.setattr(graph_viewer, "_confirm_large_nifti", lambda _path, _count: False)
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(None)

    loaded = handle_dropped_visualization_paths(plotter, session, [nifti_path], pv_module=_FakePyVista)

    assert loaded == []
    assert session.loaded_files == []
    monkeypatch.setattr(graph_viewer, "_confirm_large_nifti", lambda _path, _count: True)
    loaded = handle_dropped_visualization_paths(plotter, session, [nifti_path], pv_module=_FakePyVista)

    assert len(loaded) == 1
    assert session.active_file is not None
    assert session.active_file.kind == "nifti"


def test_collapsed_file_label_uses_small_status_text(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.graphml"
    _write_graphml(graph_path, [(0.0, 0.0, 0.0)])
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(graph_path)

    graph_viewer.render_file_panel(plotter, session)

    label_text, label_kwargs = plotter.texts[-1]
    assert "1/1  [GraphML]  graph.graphml" in label_text
    assert label_kwargs["font_size"] == 9
    assert session.file_hitboxes[0].action == "open-file-list"


def test_hover_state_exposes_loaded_files_in_display_order(tmp_path: Path) -> None:
    graph_a = tmp_path / "a.graphml"
    graph_b = tmp_path / "b.graphml"
    _write_graphml(graph_a, [(0.0, 0.0, 0.0)])
    _write_graphml(graph_b, [(1.0, 0.0, 0.0)])
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(None)
    session.load_graph(graph_a)
    session.load_graph(graph_b)
    graph_viewer.render_file_panel(plotter, session)

    panel_hitbox = session.file_hitboxes[0]
    graph_viewer.update_file_list_hover(plotter, session, panel_hitbox.x + 2, panel_hitbox.y + 2)

    rendered_text = "\n".join(text for text, _kwargs in plotter.texts)
    assert session.file_list_open is True
    assert "1. [GraphML] a.graphml" in rendered_text
    assert "2. [GraphML] b.graphml" in rendered_text
    assert [hitbox.action for hitbox in session.file_hitboxes].count("switch-file") == 2


def test_hover_state_marks_mixed_file_types(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.graphml"
    nifti_path = tmp_path / "mask.nii.gz"
    _write_graphml(graph_path, [(0.0, 0.0, 0.0)])
    _write_nifti(nifti_path, np.ones((1, 1, 1), dtype=np.uint8))
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(None)
    session.load_visualization(graph_path)
    session.load_visualization(nifti_path)
    session.file_list_open = True

    graph_viewer.render_file_panel(plotter, session)

    rendered_text = "\n".join(text for text, _kwargs in plotter.texts)
    assert "[GraphML] graph.graphml" in rendered_text
    assert "[NIfTI] mask.nii.gz" in rendered_text


def test_filename_hitbox_click_switches_active_file(tmp_path: Path) -> None:
    graph_a = tmp_path / "a.graphml"
    graph_b = tmp_path / "b.graphml"
    _write_graphml(graph_a, [(0.0, 0.0, 0.0)])
    _write_graphml(graph_b, [(1.0, 0.0, 0.0)])
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(None)
    session.load_graph(graph_a)
    session.load_graph(graph_b)
    session.active_index = 0
    session.file_list_open = True
    graph_viewer.render_file_panel(plotter, session)
    second_file_hitbox = [hitbox for hitbox in session.file_hitboxes if hitbox.index == 1][0]

    handled = graph_viewer.dispatch_ui_click(
        plotter,
        session,
        second_file_hitbox.x + 2,
        second_file_hitbox.y + 2,
        pv_module=_FakePyVista,
    )

    assert handled is True
    assert session.active_index == 1
    assert session.active_file is not None
    assert session.active_file.path == graph_b.resolve()


def test_command_button_hitboxes_dispatch_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph_a = tmp_path / "a.graphml"
    graph_b = tmp_path / "b.graphml"
    _write_graphml(graph_a, [(0.0, 0.0, 0.0)])
    _write_graphml(graph_b, [(1.0, 0.0, 0.0)])
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(None)
    session.load_graph(graph_a)
    session.load_graph(graph_b)
    session.active_index = 0
    imported = []

    def _fake_import(_plotter: Any, _session: Any, **_kwargs: Any) -> bool:
        imported.append(True)
        return True

    monkeypatch.setattr(graph_viewer, "import_graph_from_dialog", _fake_import)
    graph_viewer.render_command_buttons(plotter, session)

    button_by_action = {hitbox.action: hitbox for hitbox in session.command_hitboxes}
    assert set(button_by_action) == {"import", "close", "previous", "next", "refresh", "reset-view"}
    graph_viewer.dispatch_ui_click(
        plotter,
        session,
        button_by_action["next"].x + 1,
        button_by_action["next"].y + 1,
        pv_module=_FakePyVista,
    )
    assert session.active_index == 1
    graph_viewer.dispatch_ui_click(
        plotter,
        session,
        button_by_action["previous"].x + 1,
        button_by_action["previous"].y + 1,
        pv_module=_FakePyVista,
    )
    assert session.active_index == 0
    graph_viewer.dispatch_ui_click(
        plotter,
        session,
        button_by_action["import"].x + 1,
        button_by_action["import"].y + 1,
        pv_module=_FakePyVista,
    )
    assert imported == [True]
    graph_viewer.dispatch_ui_click(
        plotter,
        session,
        button_by_action["close"].x + 1,
        button_by_action["close"].y + 1,
        pv_module=_FakePyVista,
    )
    assert len(session.loaded_files) == 1
    active_file = session.active_file
    assert active_file is not None
    assert active_file.initial_camera_state is not None
    saved_position = active_file.initial_camera_state.position
    reset_count = plotter.reset_count
    plotter.camera.position = (44.0, 55.0, 66.0)
    graph_viewer.dispatch_ui_click(
        plotter,
        session,
        button_by_action["reset-view"].x + 1,
        button_by_action["reset-view"].y + 1,
        pv_module=_FakePyVista,
    )
    assert plotter.camera.position == saved_position
    assert plotter.reset_count == reset_count


def test_command_buttons_are_right_aligned_evenly_spaced_and_colored() -> None:
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(None)

    graph_viewer.render_command_buttons(plotter, session)

    hitboxes = session.command_hitboxes
    assert all(hitbox.height == graph_viewer.COMMAND_BUTTON_HEIGHT for hitbox in hitboxes)
    gaps = [right.x - (left.x + left.width) for left, right in zip(hitboxes, hitboxes[1:])]
    assert gaps == [graph_viewer.COMMAND_BUTTON_GAP] * (len(hitboxes) - 1)
    assert hitboxes[-1].x + hitboxes[-1].width == plotter.window_size[0] - graph_viewer.COMMAND_BUTTON_RIGHT_MARGIN
    assert hitboxes[0].x > 0

    reset_index = [hitbox.action for hitbox in hitboxes].index("reset-view")
    refresh_index = [hitbox.action for hitbox in hitboxes].index("refresh")
    assert reset_index == refresh_index + 1
    assert plotter.rectangles[reset_index]["color"] == (0.05, 0.28, 0.68)
    assert plotter.rectangles[refresh_index]["color"] == (0.70, 0.08, 0.09)
    assert all(rectangle["height"] == graph_viewer.COMMAND_BUTTON_HEIGHT for rectangle in plotter.rectangles)
    for rectangle, hitbox in zip(plotter.rectangles, hitboxes):
        assert rectangle["x"] == hitbox.x
        assert rectangle["y"] == hitbox.y
        assert rectangle["width"] == hitbox.width
        assert rectangle["height"] == hitbox.height


def test_button_backgrounds_cover_expected_glyph_extents() -> None:
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(None)

    graph_viewer.render_command_buttons(plotter, session)

    labels = ["Import", "Close", "<", ">", "Refresh", "Reset View"]
    for rectangle, label in zip(plotter.rectangles, labels):
        expected_text_width = max(len(label) * 7, 8)
        assert rectangle["width"] >= expected_text_width + 4
        assert rectangle["height"] >= graph_viewer.COMMAND_TEXT_Y_OFFSET + 12


def test_reset_view_restores_saved_initial_camera_state(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.graphml"
    _write_graphml(graph_path, [(0.0, 0.0, 0.0)])
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(graph_path)

    render_active_graph(plotter, session, pv_module=_FakePyVista)
    active_file = session.active_file
    assert active_file is not None
    assert active_file.initial_camera_state is not None
    saved_position = active_file.initial_camera_state.position
    saved_focal_point = active_file.initial_camera_state.focal_point
    reset_count = plotter.reset_count

    plotter.camera.position = (99.0, 88.0, 77.0)
    plotter.camera.focal_point = (9.0, 8.0, 7.0)
    graph_viewer.reset_active_view(plotter, session)

    assert plotter.camera.position == saved_position
    assert plotter.camera.focal_point == saved_focal_point
    assert plotter.reset_count == reset_count


def test_reset_view_falls_back_to_reset_camera_without_saved_state(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.graphml"
    _write_graphml(graph_path, [(0.0, 0.0, 0.0)])
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(graph_path)

    graph_viewer.reset_active_view(plotter, session)

    assert plotter.reset_count == 1
    assert session.active_file is not None
    assert session.active_file.initial_camera_state is not None


def test_slider_setup_uses_separated_right_aligned_compact_positions() -> None:
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(None)

    graph_viewer.add_graph_viewer_controls(plotter, session, pv_module=_FakePyVista)

    assert plotter.buttons == []
    assert len(plotter.sliders) == 2
    first_slider = plotter.sliders[0][1]
    second_slider = plotter.sliders[1][1]
    assert first_slider["pointa"] == (0.66, 0.93)
    assert first_slider["pointb"] == (0.86, 0.93)
    assert first_slider["style"] == "modern"
    assert first_slider["color"] == graph_viewer.SLIDER_COLOR
    assert first_slider["tube_width"] == 0.010
    assert second_slider["pointa"] == (0.66, 0.83)
    assert second_slider["pointb"] == (0.86, 0.83)
    assert second_slider["title"] == "Edge"
    assert first_slider["pointb"][0] <= 0.86
    assert first_slider["pointa"][1] - second_slider["pointa"][1] >= 0.09


def test_nifti_active_file_hides_graph_sliders_but_keeps_buttons(tmp_path: Path) -> None:
    nifti_path = tmp_path / "mask.nii.gz"
    _write_nifti(nifti_path, np.ones((1, 1, 1), dtype=np.uint8))
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(nifti_path)

    graph_viewer.add_graph_viewer_controls(plotter, session, pv_module=_FakePyVista)

    assert plotter.sliders == []
    assert session.sliders_visible is False
    assert {hitbox.action for hitbox in session.command_hitboxes} == {
        "import",
        "close",
        "previous",
        "next",
        "refresh",
        "reset-view",
    }


def test_switching_between_graphml_and_nifti_updates_slider_visibility(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.graphml"
    nifti_path = tmp_path / "mask.nii.gz"
    _write_graphml(graph_path, [(0.0, 0.0, 0.0)])
    _write_nifti(nifti_path, np.ones((1, 1, 1), dtype=np.uint8))
    plotter = _FakePlotter(title="test")
    session = create_graph_viewer_session(None)
    session.load_visualization(graph_path)
    session.load_visualization(nifti_path)
    session.active_index = 0
    graph_viewer.add_graph_viewer_controls(plotter, session, pv_module=_FakePyVista)

    assert len(plotter.sliders) == 2
    session.active_index = 1
    render_active_graph(plotter, session, pv_module=_FakePyVista)
    assert plotter.sliders == []
    assert session.command_hitboxes
    session.active_index = 0
    render_active_graph(plotter, session, pv_module=_FakePyVista)
    assert len(plotter.sliders) == 2


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


def test_launch_graph_viewer_with_nifti_input_loads_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakePlotter.instances.clear()
    nifti_path = tmp_path / "mask.nii.gz"
    _write_nifti(nifti_path, np.ones((1, 1, 1), dtype=np.uint8))
    monkeypatch.setattr(graph_viewer, "_import_pyvista", lambda: _FakePyVista)

    result = launch_graph_viewer(nifti_path)

    assert result == 0
    assert _FakePlotter.instances[0].shown is True
    assert len(_FakePlotter.instances[0].meshes) == 1


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
    assert "NIfTI" in parser.format_help()
