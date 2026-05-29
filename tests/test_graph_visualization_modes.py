from __future__ import annotations

from pathlib import Path

import numpy as np

from skelhub.visualization.graph_viewer import (
    GraphViewerSession,
    GraphVisualizationData,
    LoadedVisualizationFile,
    NiftiVisualizationData,
    UIHitbox,
    dispatch_ui_click,
)


def _graph_data(node_count: int) -> GraphVisualizationData:
    return GraphVisualizationData(
        node_positions=np.zeros((node_count, 3), dtype=float),
        edge_indices=np.empty((0, 2), dtype=int),
        node_count=node_count,
        edge_count=0,
        source_path=f"/tmp/graph-{node_count}.graphml",
    )


def _graph_file(name: str, node_count: int) -> LoadedVisualizationFile:
    return LoadedVisualizationFile(
        path=Path(f"/tmp/{name}.graphml"),
        kind="graphml",
        data=_graph_data(node_count),
    )


def test_small_graphml_defaults_to_detailed() -> None:
    session = GraphViewerSession(loaded_files=[_graph_file("small", 3)], active_index=0)

    assert session.graph_render_mode() == "detailed"
    assert "[GraphML Dense]" not in session.status_text()


def test_dense_graphml_defaults_to_simplified() -> None:
    session = GraphViewerSession(loaded_files=[_graph_file("dense", 1_000)], active_index=0)

    assert session.graph_render_mode() == "dense"
    assert "[GraphML Dense]" in session.status_text()


def test_detailed_override_applies_to_dense_graphml() -> None:
    session = GraphViewerSession(loaded_files=[_graph_file("dense", 1_000)], active_index=0)

    assert session.set_active_graph_render_mode("detailed") is True

    assert session.graph_render_mode() == "detailed"
    assert "[GraphML Dense]" not in session.status_text()


def test_simplified_override_applies_to_small_graphml() -> None:
    session = GraphViewerSession(loaded_files=[_graph_file("small", 3)], active_index=0)

    assert session.set_active_graph_render_mode("dense") is True

    assert session.graph_render_mode() == "dense"
    assert "[GraphML Dense]" in session.status_text()


def test_graph_render_mode_is_preserved_per_file_when_switching() -> None:
    small_file = _graph_file("small", 3)
    dense_file = _graph_file("dense", 1_000)
    session = GraphViewerSession(loaded_files=[small_file, dense_file], active_index=0)

    assert session.set_active_graph_render_mode("dense") is True
    session.active_index = 1
    assert session.set_active_graph_render_mode("detailed") is True

    session.active_index = 0
    assert session.graph_render_mode() == "dense"
    session.active_index = 1
    assert session.graph_render_mode() == "detailed"


def test_nifti_active_file_ignores_graph_render_mode() -> None:
    nifti_file = LoadedVisualizationFile(
        path=Path("/tmp/volume.nii.gz"),
        kind="nifti",
        data=NiftiVisualizationData(
            voxel_positions=np.empty((0, 3), dtype=float),
            voxel_count=0,
            shape=(1, 1, 1),
            source_path="/tmp/volume.nii.gz",
        ),
    )
    session = GraphViewerSession(loaded_files=[nifti_file], active_index=0)

    assert session.graph_render_mode() is None
    assert session.set_active_graph_render_mode("dense") is False


def test_render_mode_click_updates_only_active_graphml(monkeypatch) -> None:
    small_file = _graph_file("small", 3)
    other_file = _graph_file("other", 3)
    session = GraphViewerSession(loaded_files=[small_file, other_file], active_index=0)
    session.command_hitboxes.append(
        UIHitbox(
            name="button-render-simplified",
            x=0,
            y=0,
            width=20,
            height=20,
            action="render-simplified",
        )
    )
    render_calls: list[bool] = []

    def _fake_render_active_graph(*args, **kwargs) -> None:
        render_calls.append(kwargs["reset_camera"])

    monkeypatch.setattr("skelhub.visualization.graph_viewer.render_active_graph", _fake_render_active_graph)

    assert dispatch_ui_click(object(), session, 10, 10) is True

    assert small_file.graph_render_mode_override == "dense"
    assert other_file.graph_render_mode_override is None
    assert render_calls == [False]


def test_detailed_click_updates_only_active_graphml(monkeypatch) -> None:
    dense_file = _graph_file("dense", 1_000)
    other_file = _graph_file("other", 1_000)
    session = GraphViewerSession(loaded_files=[dense_file, other_file], active_index=0)
    session.command_hitboxes.append(
        UIHitbox(
            name="button-render-detailed",
            x=0,
            y=0,
            width=20,
            height=20,
            action="render-detailed",
        )
    )
    render_calls: list[bool] = []

    def _fake_render_active_graph(*args, **kwargs) -> None:
        render_calls.append(kwargs["reset_camera"])

    monkeypatch.setattr("skelhub.visualization.graph_viewer.render_active_graph", _fake_render_active_graph)

    assert dispatch_ui_click(object(), session, 10, 10) is True

    assert dense_file.graph_render_mode_override == "detailed"
    assert other_file.graph_render_mode_override is None
    assert render_calls == [False]
