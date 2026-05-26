"""Tests for optimized GraphML display rendering."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyvista as pv
import pytest
from vtkmodules.vtkRenderingCore import vtkGlyph3DMapper

from skelhub.cli.main import build_parser
from skelhub.visualization import graph_viewer


def _graph_data() -> graph_viewer.GraphVisualizationData:
    return graph_viewer.GraphVisualizationData(
        node_positions=np.asarray(
            [[0.0, 0.0, 0.0], [12.0, 0.0, 0.0], [24.0, 0.0, 0.0]],
            dtype=float,
        ),
        edge_indices=np.asarray([[0, 1], [1, 2]], dtype=int),
        node_count=3,
        edge_count=2,
        source_path="memory.graphml",
    )


def _dense_graph_data() -> graph_viewer.GraphVisualizationData:
    node_count = graph_viewer.DENSE_GRAPH_NODE_THRESHOLD
    return graph_viewer.GraphVisualizationData(
        node_positions=np.column_stack(
            (np.arange(node_count, dtype=float), np.zeros(node_count), np.zeros(node_count))
        ),
        edge_indices=np.asarray([[0, 1], [1, 2]], dtype=int),
        node_count=node_count,
        edge_count=2,
        source_path="dense.graphml",
    )


def _active_graph_session(
    data: graph_viewer.GraphVisualizationData | None = None,
) -> graph_viewer.GraphViewerSession:
    session = graph_viewer.GraphViewerSession()
    session.loaded_files.append(
        graph_viewer.LoadedVisualizationFile(
            path=Path("memory.graphml"),
            kind="graphml",
            data=_graph_data() if data is None else data,
        )
    )
    session.active_index = 0
    return session


def test_graphviz_defaults_match_viewer_session_and_cli() -> None:
    session = graph_viewer.create_graph_viewer_session()
    args = build_parser().parse_args(["graphviz"])

    assert session.options.node_size == 2.5
    assert session.options.edge_thickness == 1.0
    assert args.node_size == 2.5
    assert args.edge_thickness == 1.0


def test_graph_render_mode_uses_dense_path_at_threshold() -> None:
    assert graph_viewer._graph_render_mode(_graph_data()) == "detailed"
    assert graph_viewer._graph_render_mode(_dense_graph_data()) == "dense"


def test_instanced_node_actor_keeps_one_shared_sphere_source() -> None:
    actor = graph_viewer._build_instanced_node_actor(
        _graph_data(),
        graph_viewer.GraphVisualizationOptions(node_size=6.0),
        pv_module=pv,
    )

    mapper = actor.GetMapper()

    assert isinstance(mapper, vtkGlyph3DMapper)
    assert mapper.GetInput().GetNumberOfPoints() == 3
    assert mapper.GetSource(0).GetNumberOfCells() == pv.Sphere(radius=6.0).n_cells
    assert mapper.GetSource(0).GetNumberOfCells() < 3 * pv.Sphere(radius=6.0).n_cells


def test_refresh_uses_instanced_nodes_and_updated_edge_thickness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plotter = pv.Plotter(off_screen=True)
    session = _active_graph_session()
    monkeypatch.setattr(graph_viewer, "_set_status", lambda *_args: None)
    monkeypatch.setattr(graph_viewer, "render_graph_sliders", lambda *_args: None)

    try:
        graph_viewer.render_active_graph(plotter, session, pv_module=pv)
        session.set_preview_node_size(9.0)
        session.set_preview_edge_thickness(3.0)

        graph_viewer.refresh_active_graph(plotter, session, pv_module=pv)

        edge_actor, node_actor = session.graph_actors
        mapper = node_actor.GetMapper()
        edge_bounds = edge_actor.GetMapper().GetInput().GetBounds()
        node_bounds = mapper.GetSource(0).GetBounds()

        assert isinstance(mapper, vtkGlyph3DMapper)
        assert session.options.node_size == 9.0
        assert session.options.edge_thickness == 3.0
        assert node_bounds == pytest.approx(pv.Sphere(radius=9.0).bounds)
        assert edge_bounds[3] == pytest.approx(3.0)
    finally:
        plotter.close()


def test_dense_scene_uses_original_points_and_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plotter = pv.Plotter(off_screen=True)
    session = _active_graph_session(_dense_graph_data())
    monkeypatch.setattr(graph_viewer, "_set_status", lambda *_args: None)
    monkeypatch.setattr(graph_viewer, "render_graph_sliders", lambda *_args: None)
    monkeypatch.setattr(
        graph_viewer,
        "_build_instanced_node_actor",
        lambda *_args, **_kwargs: pytest.fail("dense rendering must not construct sphere glyphs"),
    )

    try:
        graph_viewer.render_active_graph(plotter, session, pv_module=pv)

        assert session.dense_edge_actor is not None
        assert session.dense_node_actor is not None
        assert session.dense_edge_actor.GetMapper().GetInput().GetNumberOfLines() == 2
        assert session.dense_node_actor.GetMapper().GetInput().GetNumberOfPoints() == graph_viewer.DENSE_GRAPH_NODE_THRESHOLD
        assert session.status_text().startswith("1/1  [GraphML Dense]")
    finally:
        plotter.close()


def test_dense_refresh_updates_actor_properties_without_rebuild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plotter = pv.Plotter(off_screen=True)
    session = _active_graph_session(_dense_graph_data())
    monkeypatch.setattr(graph_viewer, "_set_status", lambda *_args: None)
    monkeypatch.setattr(graph_viewer, "render_graph_sliders", lambda *_args: None)

    try:
        graph_viewer.render_active_graph(plotter, session, pv_module=pv)
        initial_actors = tuple(session.graph_actors)
        session.set_preview_node_size(7.0)
        session.set_preview_edge_thickness(3.0)

        graph_viewer.refresh_active_graph(plotter, session, pv_module=pv)

        assert tuple(session.graph_actors) == initial_actors
        assert session.dense_node_actor.GetProperty().GetPointSize() == pytest.approx(7.0)
        assert session.dense_edge_actor.GetProperty().GetLineWidth() == pytest.approx(3.0)
    finally:
        plotter.close()
