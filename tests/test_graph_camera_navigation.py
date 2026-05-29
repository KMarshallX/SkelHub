from __future__ import annotations

from pathlib import Path

import numpy as np

from skelhub.visualization import graph_viewer
from skelhub.visualization.graph_viewer import (
    GraphViewerSession,
    GraphVisualizationData,
    LoadedVisualizationFile,
    NiftiVisualizationData,
    UIHitbox,
)


class FakeCamera:
    def __init__(
        self,
        *,
        position: tuple[float, float, float] = (0.0, 0.0, 10.0),
        focal_point: tuple[float, float, float] = (0.0, 0.0, 0.0),
        view_up: tuple[float, float, float] = (0.0, 1.0, 0.0),
    ) -> None:
        self.position = position
        self.focal_point = focal_point
        self.view_up = view_up

    def GetPosition(self) -> tuple[float, float, float]:
        return self.position

    def SetPosition(self, *position: float) -> None:
        self.position = tuple(float(value) for value in position)  # type: ignore[assignment]

    def GetFocalPoint(self) -> tuple[float, float, float]:
        return self.focal_point

    def SetFocalPoint(self, *focal_point: float) -> None:
        self.focal_point = tuple(float(value) for value in focal_point)  # type: ignore[assignment]

    def GetViewUp(self) -> tuple[float, float, float]:
        return self.view_up

    def SetViewUp(self, *view_up: float) -> None:
        self.view_up = tuple(float(value) for value in view_up)  # type: ignore[assignment]


class FakePlotter:
    def __init__(self, camera: FakeCamera) -> None:
        self.camera = camera
        self.render_count = 0
        self.clipping_reset_count = 0

    def render(self) -> None:
        self.render_count += 1

    def reset_camera_clipping_range(self) -> None:
        self.clipping_reset_count += 1


def _distance(camera: FakeCamera, center: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> float:
    return float(np.linalg.norm(np.asarray(camera.position) - np.asarray(center)))


def _graph_file() -> LoadedVisualizationFile:
    return LoadedVisualizationFile(
        path=Path("/tmp/graph.graphml"),
        kind="graphml",
        data=GraphVisualizationData(
            node_positions=np.asarray([[-1.0, -1.0, -1.0], [1.0, 1.0, 1.0]], dtype=float),
            edge_indices=np.empty((0, 2), dtype=int),
            node_count=2,
            edge_count=0,
            source_path="/tmp/graph.graphml",
        ),
    )


def _nifti_file() -> LoadedVisualizationFile:
    return LoadedVisualizationFile(
        path=Path("/tmp/volume.nii.gz"),
        kind="nifti",
        data=NiftiVisualizationData(
            voxel_positions=np.asarray([[0.0, 0.0, 0.0], [2.0, 2.0, 2.0]], dtype=float),
            voxel_count=2,
            shape=(3, 3, 3),
            source_path="/tmp/volume.nii.gz",
            affine=np.eye(4, dtype=float),
        ),
    )


def _session(active_file: LoadedVisualizationFile | None = None) -> GraphViewerSession:
    files = [] if active_file is None else [active_file]
    return GraphViewerSession(loaded_files=files, active_index=0 if files else None)


def test_wheel_zoom_in_decreases_distance_to_object_center() -> None:
    camera = FakeCamera(position=(0.0, 0.0, 10.0), focal_point=(2.0, 3.0, 4.0))
    plotter = FakePlotter(camera)
    session = _session(_graph_file())

    assert graph_viewer._zoom_active_camera(plotter, session, direction=1.0) is True

    assert _distance(camera) < 10.0
    assert camera.focal_point == (2.0, 3.0, 4.0)
    assert plotter.render_count == 1
    assert plotter.clipping_reset_count == 1


def test_wheel_zoom_out_increases_distance_to_object_center() -> None:
    camera = FakeCamera(position=(0.0, 0.0, 10.0), focal_point=(2.0, 3.0, 4.0))
    plotter = FakePlotter(camera)
    session = _session(_graph_file())

    assert graph_viewer._zoom_active_camera(plotter, session, direction=-1.0) is True

    assert _distance(camera) > 10.0
    assert camera.focal_point == (2.0, 3.0, 4.0)


def test_wheel_zoom_step_is_larger_when_camera_is_farther_away() -> None:
    near_camera = FakeCamera(position=(0.0, 0.0, 5.0))
    far_camera = FakeCamera(position=(0.0, 0.0, 50.0))
    session = _session(_graph_file())

    graph_viewer._zoom_active_camera(FakePlotter(near_camera), session, direction=1.0)
    graph_viewer._zoom_active_camera(FakePlotter(far_camera), session, direction=1.0)

    near_step = 5.0 - _distance(near_camera)
    far_step = 50.0 - _distance(far_camera)
    assert far_step > near_step


def test_wheel_zoom_clamps_before_crossing_object_center() -> None:
    camera = FakeCamera(position=(0.0, 0.0, 0.001), focal_point=(2.0, 3.0, 4.0))
    session = _session(_graph_file())

    for _ in range(100):
        graph_viewer._zoom_active_camera(FakePlotter(camera), session, direction=1.0)

    assert _distance(camera) >= graph_viewer.CAMERA_MIN_DISTANCE
    assert camera.focal_point == (2.0, 3.0, 4.0)


def test_left_drag_orbit_changes_camera_position_and_preserves_distance() -> None:
    camera = FakeCamera(position=(0.0, 0.0, 10.0), focal_point=(2.0, 3.0, 4.0))
    plotter = FakePlotter(camera)
    session = _session(_graph_file())
    start_distance = _distance(camera)

    assert graph_viewer._begin_camera_orbit_drag(plotter, session, 100, 100) is True
    assert graph_viewer._update_camera_orbit_drag(plotter, session, 140, 120) is True

    assert not np.allclose(camera.position, (0.0, 0.0, 10.0))
    assert np.isclose(_distance(camera), start_distance)
    assert camera.focal_point == (2.0, 3.0, 4.0)


def test_orbit_world_displacement_is_larger_when_camera_is_farther_away() -> None:
    near_camera = FakeCamera(position=(0.0, 0.0, 5.0))
    far_camera = FakeCamera(position=(0.0, 0.0, 50.0))
    session = _session(_graph_file())

    graph_viewer._begin_camera_orbit_drag(FakePlotter(near_camera), session, 100, 100)
    graph_viewer._update_camera_orbit_drag(FakePlotter(near_camera), session, 120, 100)
    session.camera_orbit_dragging = False
    session.camera_orbit_last_position = None
    graph_viewer._begin_camera_orbit_drag(FakePlotter(far_camera), session, 100, 100)
    graph_viewer._update_camera_orbit_drag(FakePlotter(far_camera), session, 120, 100)

    near_displacement = float(np.linalg.norm(np.asarray(near_camera.position) - np.asarray((0.0, 0.0, 5.0))))
    far_displacement = float(np.linalg.norm(np.asarray(far_camera.position) - np.asarray((0.0, 0.0, 50.0))))
    assert far_displacement > near_displacement


def test_nifti_active_file_uses_object_centered_zoom() -> None:
    camera = FakeCamera(position=(1.0, 1.0, 10.0), focal_point=(2.0, 3.0, 4.0))
    plotter = FakePlotter(camera)
    session = _session(_nifti_file())

    assert graph_viewer._zoom_active_camera(plotter, session, direction=1.0) is True

    assert _distance(camera, center=(1.0, 1.0, 1.0)) < 9.0
    assert camera.focal_point == (2.0, 3.0, 4.0)


class FakeCommand:
    def __init__(self) -> None:
        self.abort_flag = 0

    def SetAbortFlag(self, value: int) -> None:
        self.abort_flag = int(value)


class FakeNativeInteractor:
    def __init__(self) -> None:
        self.callbacks: dict[str, object] = {}
        self.commands: dict[int, FakeCommand] = {}

    def AddObserver(self, event_name: str, callback: object, *_args: object) -> int:
        observer_id = len(self.commands) + 1
        self.callbacks[event_name] = callback
        self.commands[observer_id] = FakeCommand()
        return observer_id

    def GetCommand(self, observer_id: int) -> FakeCommand:
        return self.commands[observer_id]


class FakeInteractor:
    def __init__(self) -> None:
        self.interactor = FakeNativeInteractor()
        self.callbacks: dict[str, object] = {}

    def add_observer(self, event_name: str, callback: object) -> None:
        self.callbacks[event_name] = callback


class FakeCaller:
    def __init__(self, position: tuple[int, int]) -> None:
        self.position = position

    def GetEventPosition(self) -> tuple[int, int]:
        return self.position


def test_cursor_drag_takes_priority_over_camera_orbit(monkeypatch) -> None:
    camera = FakeCamera()
    plotter = FakePlotter(camera)
    plotter.iren = FakeInteractor()  # type: ignore[attr-defined]
    session = _session(_graph_file())
    orbit_calls: list[tuple[int, int]] = []

    monkeypatch.setattr(graph_viewer, "dispatch_ui_click", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(graph_viewer, "_begin_cursor_drag", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        graph_viewer,
        "_begin_camera_orbit_drag",
        lambda _plotter, _session, x_pos, y_pos: orbit_calls.append((x_pos, y_pos)) or True,
    )

    assert graph_viewer.install_ui_mouse_observers(plotter, session) is True
    callback = plotter.iren.interactor.callbacks["LeftButtonPressEvent"]  # type: ignore[attr-defined]
    callback(FakeCaller((12, 34)), "LeftButtonPressEvent")  # type: ignore[operator]

    assert orbit_calls == []
