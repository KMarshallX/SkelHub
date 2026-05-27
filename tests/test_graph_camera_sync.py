from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from skelhub.visualization import graph_viewer


class FakeCamera:
    def __init__(self) -> None:
        self.position = (5.0, 5.0, 25.0)
        self.focal_point = (5.0, 5.0, 5.0)
        self.up = (0.0, 1.0, 0.0)
        self.clipping_range = (0.1, 100.0)
        self.parallel_scale = 4.0
        self.view_angle = 24.0
        self.parallel_projection = True

    def GetPosition(self):
        return self.position

    def SetPosition(self, *values):
        self.position = tuple(values)

    def GetFocalPoint(self):
        return self.focal_point

    def SetFocalPoint(self, *values):
        self.focal_point = tuple(values)

    def GetViewUp(self):
        return self.up

    def SetViewUp(self, *values):
        self.up = tuple(values)

    def GetClippingRange(self):
        return self.clipping_range

    def SetClippingRange(self, *values):
        self.clipping_range = tuple(values)

    def GetParallelScale(self):
        return self.parallel_scale

    def SetParallelScale(self, value):
        self.parallel_scale = value

    def GetViewAngle(self):
        return self.view_angle

    def SetViewAngle(self, value):
        self.view_angle = value

    def GetParallelProjection(self):
        return self.parallel_projection

    def SetParallelProjection(self, value):
        self.parallel_projection = bool(value)


class FakePlotter:
    def __init__(self) -> None:
        self.camera = FakeCamera()
        self.clipping_reset_count = 0
        self.render_count = 0

    def reset_camera_clipping_range(self) -> None:
        self.clipping_reset_count += 1

    def render(self) -> None:
        self.render_count += 1

    def reset_camera(self) -> None:
        self.camera.SetPosition(5.0, 5.0, 25.0)
        self.camera.SetFocalPoint(5.0, 5.0, 5.0)


def _graph(name: str, upper: float = 10.0) -> graph_viewer.LoadedVisualizationFile:
    data = graph_viewer.GraphVisualizationData(
        node_positions=np.array([[0.0, 0.0, 0.0], [upper, upper, upper]]),
        edge_indices=np.empty((0, 2), dtype=int),
        node_count=2,
        edge_count=0,
        source_path=name,
    )
    return graph_viewer.LoadedVisualizationFile(Path(name), "graphml", data)


def _nifti(
    name: str,
    positions: np.ndarray,
    *,
    affine: np.ndarray | None = None,
    shape=(10, 20, 30),
) -> graph_viewer.LoadedVisualizationFile:
    image_affine = np.eye(4) if affine is None else affine
    data = graph_viewer.NiftiVisualizationData(
        voxel_positions=positions,
        voxel_count=int(len(positions)),
        shape=shape,
        source_path=name,
        display_positions=graph_viewer._transform_points(positions, image_affine),
        affine=image_affine,
        spatial_unit="mm",
    )
    return graph_viewer.LoadedVisualizationFile(Path(name), "nifti", data)


def _silence_scene(monkeypatch) -> None:
    monkeypatch.setattr(graph_viewer, "_add_detailed_graph_scene", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(graph_viewer, "_build_instanced_nifti_actor", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(graph_viewer, "_set_status", lambda *_args: None)
    monkeypatch.setattr(graph_viewer, "render_tools_panel", lambda *_args: None)


def test_nifti_loader_retains_voxel_indices_and_computes_world_centres(tmp_path: Path) -> None:
    affine = np.array(
        [[0.0, 2.0, 0.0, 10.0], [0.0, 0.0, -3.0, -20.0], [-4.0, 0.0, 0.0, 30.0], [0, 0, 0, 1]]
    )
    volume = np.zeros((3, 4, 5), dtype=np.uint8)
    volume[1, 2, 3] = 1
    path = tmp_path / "affine.nii.gz"
    image = nib.Nifti1Image(volume, affine)
    image.header.set_xyzt_units("mm")
    nib.save(image, path)

    loaded = graph_viewer.load_nifti_visualization_data(path)

    np.testing.assert_allclose(loaded.voxel_positions, [[1.0, 2.0, 3.0]])
    np.testing.assert_allclose(loaded.display_positions, [[14.0, -29.0, 26.0]])
    np.testing.assert_allclose(loaded.affine, affine)
    assert loaded.spatial_unit == "mm"


def test_nifti_cursor_and_bounds_are_world_coordinates() -> None:
    affine = np.array(
        [[0.0, 2.0, 0.0, 10.0], [0.0, 0.0, -3.0, -20.0], [-4.0, 0.0, 0.0, 30.0], [0, 0, 0, 1]]
    )
    loaded = _nifti("physical.nii.gz", np.array([[1.0, 2.0, 3.0]]), affine=affine)

    assert graph_viewer._scene_cursor_center(loaded) == pytest.approx((14.0, -29.0, 26.0))
    lower, upper = graph_viewer._scene_bounds(loaded)
    assert lower == pytest.approx((13.0, -30.5, 24.0))
    assert upper == pytest.approx((15.0, -27.5, 28.0))


def test_empty_nifti_bounds_transform_the_full_volume_corners() -> None:
    affine = np.array([[2, 0, 0, 5], [0, -3, 0, 6], [0, 0, 4, -7], [0, 0, 0, 1]], dtype=float)
    loaded = _nifti("empty.nii.gz", np.empty((0, 3)), affine=affine, shape=(2, 4, 6))

    lower, upper = graph_viewer._scene_bounds(loaded)

    assert lower == pytest.approx((4.0, -4.5, -9.0))
    assert upper == pytest.approx((8.0, 7.5, 15.0))


def test_nifti_mesh_and_instanced_actor_use_world_centres_and_affine_geometry() -> None:
    pv = pytest.importorskip("pyvista")
    affine = np.array([[0, 2, 0, 10], [0, 0, -3, -20], [-4, 0, 0, 30], [0, 0, 0, 1]], dtype=float)
    loaded = _nifti("oriented.nii.gz", np.array([[1.0, 2.0, 3.0]]), affine=affine)

    source = graph_viewer._nifti_voxel_geometry(loaded.data, pv)
    bounds = np.asarray(source.bounds).reshape(3, 2)
    mesh = graph_viewer.build_nifti_meshes(loaded.data, pv_module=pv).blocks
    actor = graph_viewer._build_instanced_nifti_actor(loaded.data, pv_module=pv)
    mapper = actor.GetMapper()

    assert bounds[:, 1] - bounds[:, 0] == pytest.approx((2.0, 3.0, 4.0))
    assert mesh.bounds == pytest.approx((13.0, 15.0, -30.5, -27.5, 24.0, 28.0))
    np.testing.assert_allclose(np.asarray(mapper.GetInput().GetPoints().GetData()), [[14.0, -29.0, 26.0]])
    assert mapper.GetSource(0).GetBounds() == pytest.approx((-1.0, 1.0, -1.5, 1.5, -2.0, 2.0))


def test_sync_toggle_defaults_on_and_captures_exact_camera_when_reenabled(monkeypatch) -> None:
    plotter = FakePlotter()
    session = graph_viewer.GraphViewerSession(loaded_files=[_graph("file.graphml")], active_index=0)
    monkeypatch.setattr(graph_viewer, "render_tools_panel", lambda *_args: None)

    assert session.camera_sync_enabled is True
    graph_viewer.toggle_camera_sync(plotter, session)
    assert session.camera_sync_enabled is False
    assert session.shared_camera_state is None

    plotter.camera.SetPosition(12.0, 13.0, 14.0)
    graph_viewer.toggle_camera_sync(plotter, session)
    assert session.shared_camera_state is not None
    assert session.shared_camera_state.position == pytest.approx((12.0, 13.0, 14.0))


def test_switch_between_graphml_and_nifti_restores_absolute_world_camera(monkeypatch) -> None:
    affine = np.diag([0.1, 0.2, 0.3, 1.0])
    plotter = FakePlotter()
    session = graph_viewer.GraphViewerSession(
        loaded_files=[_graph("graph.graphml"), _nifti("image.nii.gz", np.array([[1.0, 2.0, 3.0]]), affine=affine)],
        active_index=0,
    )
    _silence_scene(monkeypatch)
    plotter.camera.SetPosition(19.0, -25.0, -30.0)
    plotter.camera.SetFocalPoint(22.0, -28.0, -34.0)
    plotter.camera.SetViewAngle(17.0)
    plotter.camera.SetParallelProjection(False)
    expected = graph_viewer._capture_camera_state(plotter)

    graph_viewer.switch_next_graph(plotter, session)

    assert session.active_kind == "nifti"
    restored = graph_viewer._capture_camera_state(plotter)
    assert restored == expected
    assert plotter.clipping_reset_count == 1


def test_file_switch_uses_default_framing_when_sync_disabled(monkeypatch) -> None:
    plotter = FakePlotter()
    session = graph_viewer.GraphViewerSession(
        loaded_files=[_graph("small.graphml"), _graph("large.graphml", 20.0)],
        active_index=0,
        camera_sync_enabled=False,
    )
    _silence_scene(monkeypatch)
    plotter.camera.SetPosition(80.0, 70.0, 60.0)

    graph_viewer.switch_next_graph(plotter, session)

    assert plotter.camera.focal_point == pytest.approx((5.0, 5.0, 5.0))
    assert plotter.camera.position == pytest.approx((5.0, 5.0, 25.0))


def test_reset_view_replaces_shared_world_camera_when_sync_is_enabled(monkeypatch) -> None:
    plotter = FakePlotter()
    loaded = _graph("file.graphml")
    loaded.initial_camera_state = graph_viewer._capture_camera_state(plotter)
    session = graph_viewer.GraphViewerSession(loaded_files=[loaded], active_index=0)
    plotter.camera.SetPosition(20.0, 20.0, 40.0)
    monkeypatch.setattr(graph_viewer, "_set_status", lambda *_args: None)
    monkeypatch.setattr(graph_viewer, "render_cursor_crosshair", lambda *_args: None)

    graph_viewer.reset_active_view(plotter, session)

    assert session.shared_camera_state is not None
    assert session.shared_camera_state.position == pytest.approx((5.0, 5.0, 25.0))
    assert session.shared_camera_state.focal_point == pytest.approx((5.0, 5.0, 5.0))


def test_closing_last_file_clears_shared_camera(monkeypatch) -> None:
    plotter = FakePlotter()
    session = graph_viewer.GraphViewerSession(loaded_files=[_graph("only.graphml")], active_index=0)
    session.shared_camera_state = graph_viewer._capture_camera_state(plotter)
    _silence_scene(monkeypatch)

    graph_viewer.close_active_graph(plotter, session)

    assert session.active_file is None
    assert session.shared_camera_state is None
