from __future__ import annotations

import textwrap

import nibabel as nib
import numpy as np
import pytest

from skelhub.cli import main as cli_main
from skelhub.visualization import (
    GraphVisualizationData,
    GraphVisualizationError,
    GraphVisualizationOptions,
    GraphViewerSession,
    NiftiVisualizationData,
    create_graph_viewer_session,
    load_graph_visualization_data,
    load_nifti_visualization_data,
)
from skelhub.visualization import graph_viewer
from skelhub.visualization import loading, session


def _write_graphml(path, *, include_z: bool = True) -> None:
    z_key = '<key id="z" for="node" attr.name="Z" attr.type="double"/>' if include_z else ""
    z0 = '<data key="z">0.0</data>' if include_z else ""
    z1 = '<data key="z">1.0</data>' if include_z else ""
    path.write_text(
        textwrap.dedent(
            f"""\
            <?xml version="1.0" encoding="UTF-8"?>
            <graphml xmlns="http://graphml.graphdrawing.org/xmlns">
              <key id="x" for="node" attr.name="X" attr.type="double"/>
              <key id="y" for="node" attr.name="Y" attr.type="double"/>
              {z_key}
              <graph id="G" edgedefault="undirected">
                <node id="n0"><data key="x">0.0</data><data key="y">0.0</data>{z0}</node>
                <node id="n1"><data key="x">1.0</data><data key="y">2.0</data>{z1}</node>
                <edge source="n0" target="n1"/>
              </graph>
            </graphml>
            """
        ),
        encoding="utf-8",
    )


def _write_nifti(path, values: np.ndarray) -> None:
    image = nib.Nifti1Image(values, np.eye(4, dtype=float))
    nib.save(image, str(path))


def test_legacy_graph_viewer_facade_preserves_public_and_private_names() -> None:
    assert graph_viewer.GraphViewerSession is GraphViewerSession
    assert graph_viewer.GraphVisualizationData is GraphVisualizationData
    assert graph_viewer.GraphVisualizationError is GraphVisualizationError
    assert graph_viewer._visualization_file_kind is loading._visualization_file_kind
    assert graph_viewer.create_graph_viewer_session is session.create_graph_viewer_session
    assert hasattr(graph_viewer, "_tools_panel_geometry")


def test_package_exports_still_match_graph_viewer_facade() -> None:
    assert GraphVisualizationOptions is graph_viewer.GraphVisualizationOptions
    assert NiftiVisualizationData is graph_viewer.NiftiVisualizationData
    assert create_graph_viewer_session is graph_viewer.create_graph_viewer_session
    assert load_graph_visualization_data is graph_viewer.load_graph_visualization_data
    assert load_nifti_visualization_data is graph_viewer.load_nifti_visualization_data


def test_graphml_loader_success_and_missing_coordinate_error(tmp_path) -> None:
    graph_path = tmp_path / "sample.graphml"
    _write_graphml(graph_path)

    data = load_graph_visualization_data(graph_path)

    assert data.node_count == 2
    assert data.edge_count == 1
    assert data.node_positions.shape == (2, 3)
    assert data.edge_indices.tolist() == [[0, 1]]

    bad_path = tmp_path / "missing_z.graphml"
    _write_graphml(bad_path, include_z=False)
    with pytest.raises(GraphVisualizationError, match="does not contain renderable 3D coordinates"):
        load_graph_visualization_data(bad_path)


def test_nifti_loader_binary_success_and_non_binary_error(tmp_path) -> None:
    nifti_path = tmp_path / "binary.nii.gz"
    volume = np.zeros((2, 2, 2), dtype=np.uint8)
    volume[1, 0, 1] = 1
    _write_nifti(nifti_path, volume)

    data = load_nifti_visualization_data(nifti_path)

    assert data.voxel_count == 1
    assert data.shape == (2, 2, 2)
    assert data.display_positions is not None

    bad_path = tmp_path / "not_binary.nii.gz"
    bad_volume = volume.copy()
    bad_volume[0, 0, 0] = 2
    _write_nifti(bad_path, bad_volume)
    with pytest.raises(GraphVisualizationError, match="must be binarized"):
        load_nifti_visualization_data(bad_path)


def test_session_load_switch_assign_and_close_behaviors(tmp_path) -> None:
    graph_path = tmp_path / "sample.graphml"
    _write_graphml(graph_path)
    nifti_path = tmp_path / "binary.nii.gz"
    volume = np.zeros((2, 2, 2), dtype=np.uint8)
    volume[0, 0, 0] = 1
    _write_nifti(nifti_path, volume)

    viewer_session = create_graph_viewer_session(edge_thickness=2.0, node_size=4.0)
    first = viewer_session.load_visualization(graph_path)
    duplicate = viewer_session.load_visualization(graph_path)
    second = viewer_session.load_visualization(nifti_path)

    assert first is duplicate
    assert len(viewer_session.loaded_files) == 2
    assert viewer_session.active_file is second

    viewer_session.activate_previous()
    assert viewer_session.active_file is first

    viewer_session.layout_mode = "double"
    viewer_session.assign_view_file("b", 1)
    assert viewer_session.file_for_view("b") is second

    viewer_session.active_view_id = "b"
    viewer_session.close_active_file()
    assert len(viewer_session.loaded_files) == 1
    assert viewer_session.file_for_view("b") is None


def test_graphviz_cli_help_and_error_dispatch(monkeypatch, capsys) -> None:
    with pytest.raises(SystemExit) as help_exit:
        cli_main.main(["graphviz", "--help"])
    assert help_exit.value.code == 0
    assert "Open a 3D PyVista viewer" in capsys.readouterr().out

    def _raise_graphviz_error(*_args, **_kwargs):
        raise GraphVisualizationError("refactor smoke error")

    monkeypatch.setattr(cli_main, "launch_graph_viewer_from_path", _raise_graphviz_error)
    with pytest.raises(SystemExit) as error_exit:
        cli_main.main(["graphviz", "--input", "missing.graphml"])
    assert error_exit.value.code == 2
    assert "skelhub graphviz: error: refactor smoke error" in capsys.readouterr().err
