"""Focused coverage for the PyVista graph viewer state and overlays."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from skelhub import visualization
from skelhub.visualization import graph_viewer


class _FakePolyData:
    def __init__(self, points: np.ndarray | None = None) -> None:
        self.points = points
        self.lines: np.ndarray | None = None


class _FakePV:
    PolyData = _FakePolyData


class _FakeActor:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class _FakePlotter:
    def __init__(self) -> None:
        self.mesh_calls: list[tuple[object, dict[str, object]]] = []
        self.slider_calls: list[dict[str, object]] = []

    def add_mesh(self, mesh: object, **kwargs: object) -> _FakeActor:
        self.mesh_calls.append((mesh, kwargs))
        return _FakeActor(**kwargs)

    def add_slider_widget(self, *args: object, **kwargs: object) -> _FakeActor:
        self.slider_calls.append({"args": args, **kwargs})
        return _FakeActor(**kwargs)


def _graph_data(node_count: int = 3) -> graph_viewer.GraphVisualizationData:
    positions = np.arange(node_count * 3, dtype=float).reshape((node_count, 3))
    edges = np.asarray([[0, 1], [1, 2]], dtype=int) if node_count >= 3 else np.empty((0, 2), dtype=int)
    return graph_viewer.GraphVisualizationData(
        node_positions=positions,
        edge_indices=edges,
        node_count=node_count,
        edge_count=int(edges.shape[0]),
        source_path="sample.graphml",
        node_ids=tuple(str(index) for index in range(node_count)),
    )


def test_small_graph_uses_simplified_point_line_scene() -> None:
    plotter = _FakePlotter()

    actors, edge_actor, node_actor = graph_viewer._add_graph_scene(
        plotter,
        _graph_data(),
        graph_viewer.GraphVisualizationOptions(),
        pv_module=_FakePV,
    )

    assert actors == [edge_actor, node_actor]
    assert len(plotter.mesh_calls) == 2
    assert plotter.mesh_calls[0][1]["render_lines_as_tubes"] is True
    assert plotter.mesh_calls[1][1]["style"] == "points"
    assert plotter.mesh_calls[1][1]["render_points_as_spheres"] is True


def test_graphml_status_uses_plain_graphml_label() -> None:
    session = graph_viewer.GraphViewerSession()
    session.loaded_files.append(
        graph_viewer.LoadedVisualizationFile(
            path=Path("/tmp/sample.graphml"),
            kind="graphml",
            data=_graph_data(),
        )
    )
    session.active_index = 0

    assert session.status_text() == "1/1  [GraphML]  sample.graphml"


def test_tools_panel_has_no_render_mode_buttons(monkeypatch) -> None:
    session = graph_viewer.GraphViewerSession()
    session.loaded_files.append(
        graph_viewer.LoadedVisualizationFile(
            path=Path("/tmp/sample.graphml"),
            kind="graphml",
            data=_graph_data(),
        )
    )
    session.active_index = 0
    session.tools_panel_visible = True
    plotter = _FakePlotter()

    monkeypatch.setattr(graph_viewer, "_plotter_window_size", lambda _plotter: (900, 700))
    monkeypatch.setattr(graph_viewer, "_add_overlay_rect", lambda *args, **kwargs: _FakeActor(**kwargs))
    monkeypatch.setattr(graph_viewer, "_add_overlay_text", lambda *args, **kwargs: _FakeActor(**kwargs))

    graph_viewer.render_tools_panel(plotter, session)

    actions = {hitbox.action for hitbox in session.command_hitboxes}
    assert "render-detailed" not in actions
    assert "render-simplified" not in actions


def test_detailed_mesh_helpers_are_not_public_exports() -> None:
    assert not hasattr(visualization, "GraphVisualizationMeshes")
    assert not hasattr(visualization, "build_graph_meshes")
