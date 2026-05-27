from pathlib import Path

import numpy as np
import pytest

from skelhub.visualization import graph_viewer


class FakeCamera:
    def __init__(self) -> None:
        self.position = (0.0, 0.0, 10.0)
        self.focal_point = (0.0, 0.0, 0.0)
        self.up = (0.0, 1.0, 0.0)
        self.clipping_range = (0.1, 100.0)
        self.parallel_scale = 1.0
        self.view_angle = 30.0
        self.parallel_projection = False

    def GetPosition(self) -> tuple[float, float, float]:
        return self.position

    def SetPosition(self, *position: float) -> None:
        self.position = tuple(position)

    def GetFocalPoint(self) -> tuple[float, float, float]:
        return self.focal_point

    def SetFocalPoint(self, *focal_point: float) -> None:
        self.focal_point = tuple(focal_point)

    def GetViewUp(self) -> tuple[float, float, float]:
        return self.up

    def SetViewUp(self, *up: float) -> None:
        self.up = tuple(up)

    def GetClippingRange(self) -> tuple[float, float]:
        return self.clipping_range

    def SetClippingRange(self, *clipping_range: float) -> None:
        self.clipping_range = tuple(clipping_range)

    def GetParallelScale(self) -> float:
        return self.parallel_scale

    def SetParallelScale(self, parallel_scale: float) -> None:
        self.parallel_scale = parallel_scale

    def GetViewAngle(self) -> float:
        return self.view_angle

    def SetViewAngle(self, view_angle: float) -> None:
        self.view_angle = view_angle

    def GetParallelProjection(self) -> bool:
        return self.parallel_projection

    def SetParallelProjection(self, parallel_projection: bool) -> None:
        self.parallel_projection = bool(parallel_projection)


class FakeCommand:
    def __init__(self) -> None:
        self.abort_flag = 0

    def SetAbortFlag(self, abort_flag: int) -> None:
        self.abort_flag = abort_flag


class FakeNativeInteractor:
    def __init__(self) -> None:
        self.callbacks = {}
        self.commands = {}

    def AddObserver(self, event_name, callback, *_args):
        observer_id = len(self.callbacks) + 1
        self.callbacks[event_name] = callback
        self.commands[observer_id] = FakeCommand()
        return observer_id

    def GetCommand(self, observer_id):
        return self.commands[observer_id]


class FakeInteractor:
    def __init__(self) -> None:
        self.interactor = FakeNativeInteractor()
        self.callbacks = {}

    def add_observer(self, event_name, callback) -> None:
        self.callbacks[event_name] = callback


class FakePlotter:
    def __init__(self, *, with_interactor: bool = False) -> None:
        self.camera = FakeCamera()
        self.render_count = 0
        self.clipping_reset_count = 0
        if with_interactor:
            self.iren = FakeInteractor()

    def render(self) -> None:
        self.render_count += 1

    def reset_camera_clipping_range(self) -> None:
        self.clipping_reset_count += 1


def _graph_session() -> graph_viewer.GraphViewerSession:
    data = graph_viewer.GraphVisualizationData(
        node_positions=np.array([[0.0, 0.0, 0.0]]),
        edge_indices=np.empty((0, 2), dtype=int),
        node_count=1,
        edge_count=0,
        source_path="sample.graphml",
    )
    loaded = graph_viewer.LoadedVisualizationFile(Path("sample.graphml"), "graphml", data)
    return graph_viewer.GraphViewerSession(loaded_files=[loaded], active_index=0)


def _nifti_session() -> graph_viewer.GraphViewerSession:
    data = graph_viewer.NiftiVisualizationData(
        voxel_positions=np.array([[0.0, 0.0, 0.0]]),
        voxel_count=1,
        shape=(1, 1, 1),
        source_path="sample.nii.gz",
    )
    loaded = graph_viewer.LoadedVisualizationFile(Path("sample.nii.gz"), "nifti", data)
    return graph_viewer.GraphViewerSession(loaded_files=[loaded], active_index=0)


def test_graph_camera_forward_travel_passes_original_focal_point_and_can_reverse() -> None:
    plotter = FakePlotter()
    session = _graph_session()

    for _ in range(48):
        assert graph_viewer._travel_active_graph_camera(plotter, session, direction=1.0)

    assert plotter.camera.position[2] == pytest.approx(-2.0)
    assert plotter.camera.focal_point[2] == pytest.approx(-12.0)

    for _ in range(48):
        assert graph_viewer._travel_active_graph_camera(plotter, session, direction=-1.0)

    assert plotter.camera.position == pytest.approx((0.0, 0.0, 10.0))
    assert plotter.camera.focal_point == pytest.approx((0.0, 0.0, 0.0))
    assert plotter.clipping_reset_count == 96


def test_wheel_observers_consume_graphml_only() -> None:
    plotter = FakePlotter(with_interactor=True)
    session = _graph_session()
    assert graph_viewer.install_ui_mouse_observers(plotter, session)
    native = plotter.iren.interactor

    native.callbacks["MouseWheelForwardEvent"](native, "MouseWheelForwardEvent")
    forward_command = native.commands[3]
    assert forward_command.abort_flag == 1
    assert plotter.camera.position[2] == pytest.approx(9.75)

    session.active_index = None
    native.callbacks["MouseWheelForwardEvent"](native, "MouseWheelForwardEvent")
    assert forward_command.abort_flag == 0
    assert plotter.camera.position[2] == pytest.approx(9.75)

    nifti_session = _nifti_session()
    nifti_plotter = FakePlotter(with_interactor=True)
    assert graph_viewer.install_ui_mouse_observers(nifti_plotter, nifti_session)
    nifti_native = nifti_plotter.iren.interactor
    nifti_native.callbacks["MouseWheelBackwardEvent"](nifti_native, "MouseWheelBackwardEvent")
    assert nifti_native.commands[4].abort_flag == 0
    assert nifti_plotter.camera.position == (0.0, 0.0, 10.0)


def test_reset_view_restores_initial_camera_after_graph_travel(monkeypatch) -> None:
    plotter = FakePlotter()
    session = _graph_session()
    session.active_file.initial_camera_state = graph_viewer._capture_camera_state(plotter)
    monkeypatch.setattr(graph_viewer, "_set_status", lambda *_args: None)
    monkeypatch.setattr(graph_viewer, "render_cursor_crosshair", lambda *_args: None)

    assert graph_viewer._travel_active_graph_camera(plotter, session, direction=1.0)
    graph_viewer.reset_active_view(plotter, session)

    assert plotter.camera.position == pytest.approx((0.0, 0.0, 10.0))
    assert plotter.camera.focal_point == pytest.approx((0.0, 0.0, 0.0))


def test_graph_travel_redraws_enabled_cursor(monkeypatch) -> None:
    plotter = FakePlotter()
    session = _graph_session()
    session.cursor_enabled = True
    redraw_calls = []
    monkeypatch.setattr(graph_viewer, "render_cursor_crosshair", lambda *_args: redraw_calls.append(True))

    assert graph_viewer._travel_active_graph_camera(plotter, session, direction=1.0)
    assert redraw_calls == [True]
