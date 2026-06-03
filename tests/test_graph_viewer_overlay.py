from pathlib import Path

import numpy as np

from skelhub.visualization import graph_viewer as gv


def _loaded_graph(name: str) -> gv.LoadedVisualizationFile:
    return gv.LoadedVisualizationFile(
        path=Path(name),
        kind="graphml",
        data=gv.GraphVisualizationData(
            node_positions=np.array([[0.0, 0.0, 0.0]], dtype=float),
            edge_indices=np.empty((0, 2), dtype=int),
            node_count=1,
            edge_count=0,
            source_path=name,
            node_ids=("0",),
        ),
    )


def _loaded_nifti(name: str) -> gv.LoadedVisualizationFile:
    return gv.LoadedVisualizationFile(
        path=Path(name),
        kind="nifti",
        data=object(),
    )


class _FakeProperty:
    def __init__(self) -> None:
        self.opacity: float | None = None
        self.lighting_off = False
        self.ambient: float | None = None
        self.diffuse: float | None = None
        self.specular: float | None = None

    def SetOpacity(self, value: float) -> None:
        self.opacity = float(value)

    def LightingOff(self) -> None:
        self.lighting_off = True

    def SetAmbient(self, value: float) -> None:
        self.ambient = float(value)

    def SetDiffuse(self, value: float) -> None:
        self.diffuse = float(value)

    def SetSpecular(self, value: float) -> None:
        self.specular = float(value)


class _FakeActor:
    def __init__(self) -> None:
        self.property = _FakeProperty()
        self.force_opaque: bool | None = None
        self.force_translucent: bool | None = None

    def GetProperty(self) -> _FakeProperty:
        return self.property

    def SetForceOpaque(self, value: bool) -> None:
        self.force_opaque = bool(value)

    def SetForceTranslucent(self, value: bool) -> None:
        self.force_translucent = bool(value)


class _FakePlotter:
    def __init__(self) -> None:
        self.mesh_calls: list[dict[str, object]] = []
        self.render_called = False

    def add_mesh(self, mesh, **kwargs):
        del mesh
        self.mesh_calls.append(kwargs)
        return _FakeActor()

    def render(self) -> None:
        self.render_called = True


class _FakePV:
    @staticmethod
    def PolyData(points):
        return points


def test_overlay_base_dropdown_opens_base_menu(monkeypatch) -> None:
    session = gv.GraphViewerSession()
    session.layout_mode = "overlay"
    session.command_hitboxes.append(
        gv.UIHitbox(
            name="base-dropdown",
            x=0,
            y=0,
            width=20,
            height=20,
            action="toggle-overlay-file-menu",
            index=0,
            view_id="a",
        )
    )
    monkeypatch.setattr(gv, "render_tools_panel", lambda *args, **kwargs: None)

    assert gv.dispatch_ui_click(None, session, 10, 10)
    assert session.overlay_menu_open == "base"


def test_overlay_dropdown_empty_clears_layer(monkeypatch) -> None:
    session = gv.GraphViewerSession()
    session.layout_mode = "overlay"
    session.loaded_files = [_loaded_graph("base.graphml"), _loaded_graph("overlay.graphml")]
    session.views["a"].base_file_index = 0
    session.views["a"].overlay_file_index = 1
    session.overlay_menu_open = "base"
    session.command_hitboxes.append(
        gv.UIHitbox(
            name="base-empty-row",
            x=0,
            y=0,
            width=20,
            height=20,
            action="assign-overlay-file",
            index=None,
            view_id="a",
        )
    )
    monkeypatch.setattr(gv, "render_active_graph", lambda *args, **kwargs: None)

    assert gv.dispatch_ui_click(None, session, 10, 10)
    assert session.views["a"].base_file_index is None
    assert session.views["a"].overlay_file_index == 1


def test_overlay_dropdown_allows_same_file_for_base_and_overlay(monkeypatch) -> None:
    session = gv.GraphViewerSession()
    session.layout_mode = "overlay"
    session.loaded_files = [_loaded_graph("shared.graphml"), _loaded_graph("other.graphml")]
    session.views["a"].base_file_index = 0
    session.views["a"].overlay_file_index = 1
    session.overlay_menu_open = "overlay"
    session.command_hitboxes.append(
        gv.UIHitbox(
            name="overlay-shared-row",
            x=0,
            y=0,
            width=20,
            height=20,
            action="assign-overlay-file",
            index=0,
            view_id="a",
        )
    )
    monkeypatch.setattr(gv, "render_active_graph", lambda *args, **kwargs: None)

    assert gv.dispatch_ui_click(None, session, 10, 10)
    assert session.views["a"].base_file_index == 0
    assert session.views["a"].overlay_file_index == 0


def test_overlay_node_slider_targets_only_graph_layer_when_base_is_nifti(monkeypatch) -> None:
    session = gv.GraphViewerSession()
    session.layout_mode = "overlay"
    session.loaded_files = [_loaded_nifti("base.nii.gz"), _loaded_graph("overlay.graphml")]
    session.views["a"].base_file_index = 0
    session.views["a"].overlay_file_index = 1
    monkeypatch.setattr(gv, "refresh_active_graph", lambda *args, **kwargs: None)

    assert gv._commit_graph_preview_value(None, session, option="node", value=12.0)
    assert session.views["a"].base_preview_node_size == session.views["a"].base_options.node_size
    assert session.views["a"].overlay_preview_node_size == 12.0


def test_overlay_refresh_commits_graph_preview_when_active_file_is_nifti(monkeypatch) -> None:
    session = gv.GraphViewerSession()
    session.layout_mode = "overlay"
    session.loaded_files = [_loaded_graph("base.graphml"), _loaded_nifti("overlay.nii.gz")]
    session.views["a"].base_file_index = 0
    session.views["a"].overlay_file_index = 1
    session.views["a"].file_index = 1
    session.views["a"].base_preview_node_size = 11.0
    session.views["a"].base_preview_edge_thickness = 4.0
    rendered = {"called": False}

    def _render(*args, **kwargs) -> None:
        rendered["called"] = True

    monkeypatch.setattr(gv, "render_active_graph", _render)

    gv.refresh_active_graph(None, session)

    assert rendered["called"]
    assert session.views["a"].base_options.node_size == 11.0
    assert session.views["a"].base_options.edge_thickness == 4.0


def test_overlay_base_opacity_updates_base_graph_actors() -> None:
    session = gv.GraphViewerSession()
    session.layout_mode = "overlay"
    actor = _FakeActor()
    session.views["a"].overlay_base_graph_actors.append(actor)

    assert gv._commit_graph_preview_value(None, session, option="base_opacity", value=0.35)
    assert actor.property.opacity == 0.35
    assert session.views["a"].base_opacity == 0.35


def test_overlay_nifti_opacity_one_rebuilds_actor(monkeypatch) -> None:
    session = gv.GraphViewerSession()
    session.layout_mode = "overlay"
    actor = _FakeActor()
    session.views["a"].overlay_overlay_nifti_actor = actor
    refreshed = {"called": False}

    def _refresh(*args, **kwargs) -> None:
        refreshed["called"] = True

    monkeypatch.setattr(gv, "refresh_active_graph", _refresh)

    assert gv._commit_graph_preview_value(None, session, option="overlay_opacity", value=1.0)
    assert session.views["a"].overlay_opacity == 1.0
    assert refreshed["called"]


def test_actor_opacity_one_forces_actor_opaque() -> None:
    actor = _FakeActor()

    gv._set_actor_opacity(actor, 0.998)

    assert actor.force_opaque is True
    assert actor.force_translucent is False
    assert actor.property.opacity == 1.0


def test_overlay_target_dropdown_sets_appearance_target(monkeypatch) -> None:
    session = gv.GraphViewerSession()
    session.layout_mode = "overlay"
    session.overlay_target_menu_open = True
    session.command_hitboxes.append(
        gv.UIHitbox(
            name="appearance-target-overlay",
            x=0,
            y=0,
            width=20,
            height=20,
            action="set-overlay-target",
            index=1,
        )
    )
    monkeypatch.setattr(gv, "render_tools_panel", lambda *args, **kwargs: None)

    assert gv.dispatch_ui_click(None, session, 10, 10)
    assert session.views["a"].overlay_target == "overlay"
    assert not session.overlay_target_menu_open


def test_overlay_interactive_target_dropdown_sets_target(monkeypatch) -> None:
    session = gv.GraphViewerSession()
    session.layout_mode = "overlay"
    session.interactive_overlay_target_menu_open = True
    session.command_hitboxes.append(
        gv.UIHitbox(
            name="interactive-target-overlay",
            x=0,
            y=0,
            width=20,
            height=20,
            action="set-interactive-overlay-target",
            index=1,
        )
    )
    monkeypatch.setattr(gv, "clear_interactive_selection", lambda *args, **kwargs: None)
    monkeypatch.setattr(gv, "render_tools_panel", lambda *args, **kwargs: None)

    assert gv.dispatch_ui_click(None, session, 10, 10)
    assert session.interactive_overlay_target == "overlay"
    assert not session.interactive_overlay_target_menu_open


def test_overlay_selected_node_highlight_uses_interactive_color_and_layer_size() -> None:
    session = gv.GraphViewerSession()
    session.layout_mode = "overlay"
    session.loaded_files = [_loaded_graph("base.graphml"), _loaded_graph("overlay.graphml")]
    session.views["a"].base_file_index = 0
    session.views["a"].overlay_file_index = 1
    session.views["a"].interactive_enabled = True
    session.views["a"].selected_node_index = 0
    session.views["a"].overlay_options.node_size = 13.0
    session.interactive_overlay_target = "overlay"
    plotter = _FakePlotter()

    gv.render_selected_node_highlight(plotter, session, pv_module=_FakePV(), view_id="a")

    assert plotter.mesh_calls[-1]["color"] == gv.INTERACTIVE_SELECTED_COLOR
    assert plotter.mesh_calls[-1]["point_size"] > 13.0
    assert plotter.mesh_calls[-1]["lighting"] is False
    assert plotter.mesh_calls[-1]["opacity"] == 1.0
    actor = session.views["a"].selected_node_actors[-1]
    assert actor.property.opacity == 1.0
    assert actor.property.lighting_off is True
    assert actor.property.ambient == 1.0
    assert actor.property.diffuse == 0.0
    assert actor.property.specular == 0.0


def test_overlay_render_preserves_interactive_selection_and_redraws_highlight(monkeypatch) -> None:
    session = gv.GraphViewerSession()
    session.layout_mode = "overlay"
    session.loaded_files = [_loaded_graph("base.graphml")]
    session.views["a"].base_file_index = 0
    session.views["a"].interactive_enabled = True
    session.views["a"].selected_node_index = 0
    highlighted = {"called": False}

    monkeypatch.setattr(gv, "_add_graph_scene", lambda *args, **kwargs: ([], None, _FakeActor()))
    monkeypatch.setattr(gv, "_set_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(gv, "render_tools_panel", lambda *args, **kwargs: None)
    monkeypatch.setattr(gv, "render_selected_node_highlight", lambda *args, **kwargs: highlighted.update(called=True))

    gv._render_overlay_layers(_FakePlotter(), session, session.views["a"], pv_module=_FakePV(), reset_camera=False)

    assert session.views["a"].interactive_enabled is True
    assert session.views["a"].selected_node_index == 0
    assert highlighted["called"]
