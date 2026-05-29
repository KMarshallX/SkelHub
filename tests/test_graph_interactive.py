from pathlib import Path

import numpy as np

from skelhub.visualization.graph_viewer import (
    GraphViewerSession,
    LoadedVisualizationFile,
    NiftiVisualizationData,
    _begin_node_id_edit,
    _handle_interactive_key_press,
    _scroll_tools_panel,
    _tools_scroll_max,
    _tools_scrollbar_geometry,
    fit_active_preview,
    load_graph_visualization_data,
    render_interactive_controls,
    render_command_buttons,
    render_graph_sliders,
    render_tools_panel,
    select_graph_node,
    select_graph_node_at_display_position,
    select_graph_node_by_id,
    selected_node_degree,
    toggle_interactive,
)


class FakeRenderer:
    def __init__(self) -> None:
        self._point = (0.0, 0.0, 0.0)
        self.reset_clipping_count = 0

    def SetWorldPoint(self, x_pos: float, y_pos: float, z_pos: float, _w_pos: float) -> None:
        self._point = (x_pos, y_pos, z_pos)

    def WorldToDisplay(self) -> None:
        return

    def GetDisplayPoint(self) -> tuple[float, float, float]:
        return self._point

    def ResetCameraClippingRange(self) -> None:
        self.reset_clipping_count += 1


class FakeCamera:
    def __init__(self) -> None:
        self.position = (0.0, -30.0, 0.0)
        self.focal_point = (0.0, 0.0, 0.0)
        self.up = (0.0, 0.0, 1.0)
        self.clipping_range = (0.1, 1000.0)
        self.parallel_scale = 1.0
        self.view_angle = 30.0
        self.parallel_projection = False

    def GetPosition(self):
        return self.position

    def SetPosition(self, *value):
        self.position = tuple(float(item) for item in value)

    def GetFocalPoint(self):
        return self.focal_point

    def SetFocalPoint(self, *value):
        self.focal_point = tuple(float(item) for item in value)

    def GetViewUp(self):
        return self.up

    def SetViewUp(self, *value):
        self.up = tuple(float(item) for item in value)

    def GetClippingRange(self):
        return self.clipping_range

    def SetClippingRange(self, *value):
        self.clipping_range = tuple(float(item) for item in value)

    def GetParallelScale(self):
        return self.parallel_scale

    def SetParallelScale(self, value):
        self.parallel_scale = float(value)

    def GetViewAngle(self):
        return self.view_angle

    def SetViewAngle(self, value):
        self.view_angle = float(value)

    def GetParallelProjection(self):
        return self.parallel_projection

    def SetParallelProjection(self, value):
        self.parallel_projection = bool(value)


class FakePlotter:
    window_size = (800, 600)

    def __init__(self) -> None:
        self.renderer = FakeRenderer()
        self.camera = FakeCamera()
        self.meshes = []
        self.removed = []
        self.texts = []
        self.slider_callbacks = []
        self.slider_widget_calls = []
        self.render_count = 0

    def add_mesh(self, mesh, **kwargs):
        actor = ("mesh", mesh, kwargs)
        self.meshes.append(actor)
        return actor

    def add_actor(self, actor, render=False):
        self.meshes.append(("actor", actor, render))
        return actor

    def add_text(self, text, **kwargs):
        self.texts.append(text)
        return ("text", text, kwargs)

    def add_overlay_rect(self, **kwargs):
        return ("rect", kwargs)

    def add_slider_widget(self, *args, **kwargs):
        if args:
            self.slider_callbacks.append(args[0])
        self.slider_widget_calls.append((args, kwargs))
        return ("slider", args, kwargs)

    def clear_slider_widgets(self):
        return

    def remove_actor(self, actor, render=False):
        self.removed.append((actor, render))

    def render(self):
        self.render_count += 1


class ShortFakePlotter(FakePlotter):
    window_size = (420, 360)


class ImmediateSliderCallbackPlotter(FakePlotter):
    def add_slider_widget(self, *args, **kwargs):
        if args:
            args[0](kwargs["value"])
        return super().add_slider_widget(*args, **kwargs)


class FakePV:
    class PolyData:
        def __init__(self, points):
            self.points = points
            self.lines = None

        def tube(self, **kwargs):
            return ("tube", self.points, self.lines, kwargs)

    @staticmethod
    def Sphere(**kwargs):
        return ("sphere", kwargs)


class FakeKey:
    def __init__(self, key_sym: str = "", key_code: str = "") -> None:
        self.key_sym = key_sym
        self.key_code = key_code

    def GetKeySym(self) -> str:
        return self.key_sym

    def GetKeyCode(self) -> str:
        return self.key_code


def _write_graphml(path: Path) -> None:
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="x" for="node" attr.name="X" attr.type="double"/>
  <key id="y" for="node" attr.name="Y" attr.type="double"/>
  <key id="z" for="node" attr.name="Z" attr.type="double"/>
  <graph id="G" edgedefault="undirected">
    <node id="n0"><data key="x">0</data><data key="y">0</data><data key="z">0</data></node>
    <node id="n1"><data key="x">8</data><data key="y">0</data><data key="z">0</data></node>
    <node id="n2"><data key="x">4</data><data key="y">5</data><data key="z">3</data></node>
    <edge source="n0" target="n1"/>
    <edge source="n1" target="n2"/>
  </graph>
</graphml>
""",
        encoding="utf-8",
    )


def _graph_session(tmp_path: Path) -> GraphViewerSession:
    graph_path = tmp_path / "sample.graphml"
    _write_graphml(graph_path)
    return GraphViewerSession(loaded_files=[LoadedVisualizationFile(graph_path, "graphml", load_graph_visualization_data(graph_path))], active_index=0)


def test_graphml_node_ids_are_loaded_from_graphml_id(tmp_path: Path) -> None:
    graph_path = tmp_path / "sample.graphml"
    _write_graphml(graph_path)

    graph_data = load_graph_visualization_data(graph_path)

    assert graph_data.node_ids == ("n0", "n1", "n2")


def test_toggle_interactive_only_enables_graphml(tmp_path: Path) -> None:
    plotter = FakePlotter()
    empty = GraphViewerSession()
    toggle_interactive(plotter, empty, pv_module=FakePV)
    assert not empty.interactive_enabled

    nifti = GraphViewerSession(
        loaded_files=[
            LoadedVisualizationFile(
                Path("volume.nii.gz"),
                "nifti",
                NiftiVisualizationData(np.empty((0, 3)), 0, (1, 1, 1), "volume.nii.gz"),
            )
        ],
        active_index=0,
    )
    toggle_interactive(plotter, nifti, pv_module=FakePV)
    assert not nifti.interactive_enabled

    session = _graph_session(tmp_path)
    toggle_interactive(plotter, session, pv_module=FakePV)
    assert session.interactive_enabled


def test_selecting_node_updates_position_id_and_highlight(tmp_path: Path) -> None:
    plotter = FakePlotter()
    session = _graph_session(tmp_path)
    session.interactive_enabled = True

    assert select_graph_node(plotter, session, 2, pv_module=FakePV)

    assert session.selected_node_index == 2
    assert session.selected_node_actors
    assert select_graph_node_by_id(plotter, session, "n1", pv_module=FakePV)
    assert session.selected_node_index == 1
    assert plotter.removed


def test_left_right_keys_wrap_between_graphml_nodes(tmp_path: Path) -> None:
    plotter = FakePlotter()
    session = _graph_session(tmp_path)
    session.interactive_enabled = True
    select_graph_node(plotter, session, 0, pv_module=FakePV)

    assert _handle_interactive_key_press(plotter, session, FakeKey("Left"), pv_module=FakePV)
    assert session.selected_node_index == 2
    assert _handle_interactive_key_press(plotter, session, FakeKey("Right"), pv_module=FakePV)
    assert session.selected_node_index == 0


def test_node_id_field_is_editable_but_xyz_and_degree_fields_are_read_only(tmp_path: Path) -> None:
    plotter = FakePlotter()
    session = _graph_session(tmp_path)
    session.tools_panel_visible = True
    session.selected_node_index = 1
    render_interactive_controls(plotter, session)

    actions = {hitbox.action for hitbox in session.command_hitboxes}
    assert "edit-node-id" in actions
    assert not any(action.startswith("edit-cursor") for action in actions)
    assert "Node dgr:" in plotter.texts
    assert selected_node_degree(session) == 2

    _begin_node_id_edit(plotter, session)
    session.node_id_edit_buffer = "n2"
    assert _handle_interactive_key_press(plotter, session, FakeKey("Return", "\r"), pv_module=FakePV)
    assert session.selected_node_index == 2

    _begin_node_id_edit(plotter, session)
    session.node_id_edit_buffer = "missing"
    assert _handle_interactive_key_press(plotter, session, FakeKey("Return", "\r"), pv_module=FakePV)
    assert session.selected_node_index == 2
    assert session.node_id_edit_invalid


def test_display_click_selects_nearest_node_when_interactive(tmp_path: Path) -> None:
    plotter = FakePlotter()
    session = _graph_session(tmp_path)
    session.interactive_enabled = True

    assert select_graph_node_at_display_position(plotter, session, 8, 0, pv_module=FakePV)
    assert session.selected_node_index == 1

    session.interactive_enabled = False
    assert not select_graph_node_at_display_position(plotter, session, 8, 0, pv_module=FakePV)


def test_tools_panel_scrollbar_appears_and_scrolls_for_short_window(tmp_path: Path) -> None:
    plotter = ShortFakePlotter()
    session = _graph_session(tmp_path)
    session.tools_panel_visible = True

    render_tools_panel(plotter, session)

    assert _tools_scroll_max(plotter) > 0
    assert _tools_scrollbar_geometry(plotter, session) is not None
    assert _scroll_tools_panel(plotter, session, 120)
    assert session.tools_scroll_offset > 0
    _scroll_tools_panel(plotter, session, 10_000)
    assert session.tools_scroll_offset == _tools_scroll_max(plotter)
    _scroll_tools_panel(plotter, session, -10_000)
    assert session.tools_scroll_offset == 0


def test_fit_preview_replaces_refresh_button_label(tmp_path: Path) -> None:
    plotter = FakePlotter()
    session = _graph_session(tmp_path)
    session.tools_panel_visible = True

    render_command_buttons(plotter, session)

    assert "Fit preview" in plotter.texts
    assert "Refresh" not in plotter.texts
    actions = {hitbox.action for hitbox in session.command_hitboxes}
    assert "fit-preview" in actions
    assert "refresh" not in actions


def test_step_button_hitboxes_are_not_rendered(tmp_path: Path) -> None:
    plotter = FakePlotter()
    session = _graph_session(tmp_path)
    session.tools_panel_visible = True

    render_tools_panel(plotter, session)
    actions = {hitbox.action for hitbox in session.command_hitboxes}

    assert "node-increase" not in actions
    assert "node-decrease" not in actions
    assert "edge-increase" not in actions
    assert "edge-decrease" not in actions


def test_slider_release_callback_commits_graph_preview_value(tmp_path: Path) -> None:
    plotter = FakePlotter()
    session = _graph_session(tmp_path)
    session.tools_panel_visible = True

    render_graph_sliders(plotter, session)
    assert len(plotter.slider_callbacks) == 2
    assert all(kwargs["interaction_event"] == "end" for _args, kwargs in plotter.slider_widget_calls)

    plotter.slider_callbacks[1](2.2)

    assert session.preview_edge_thickness == 2.2
    assert session.options.edge_thickness == 2.2


def test_slider_creation_and_panel_scroll_do_not_refresh_graph(tmp_path: Path) -> None:
    plotter = ImmediateSliderCallbackPlotter()
    session = _graph_session(tmp_path)
    session.tools_panel_visible = True

    render_graph_sliders(plotter, session)
    render_count = plotter.render_count
    assert session.options.node_size == 2.5
    assert session.options.edge_thickness == 1.0

    assert _scroll_tools_panel(plotter, session, 120)
    assert plotter.render_count == render_count + 1
    assert session.options.node_size == 2.5
    assert session.options.edge_thickness == 1.0


def test_fit_preview_preserves_angle_and_updates_shared_camera(tmp_path: Path) -> None:
    plotter = FakePlotter()
    session = _graph_session(tmp_path)
    before_position = np.asarray(plotter.camera.position, dtype=float)
    before_focal = np.asarray(plotter.camera.focal_point, dtype=float)
    before_direction = (before_focal - before_position) / np.linalg.norm(before_focal - before_position)
    before_up = plotter.camera.up

    assert fit_active_preview(plotter, session)

    after_position = np.asarray(plotter.camera.position, dtype=float)
    after_focal = np.asarray(plotter.camera.focal_point, dtype=float)
    after_direction = (after_focal - after_position) / np.linalg.norm(after_focal - after_position)
    assert np.allclose(after_direction, before_direction)
    assert plotter.camera.up == before_up
    assert not np.allclose(after_position, before_position)
    assert np.allclose(after_focal, np.asarray([4.0, 2.5, 1.5]))
    assert session.shared_camera_state is not None
    assert plotter.renderer.reset_clipping_count == 1
