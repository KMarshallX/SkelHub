"""PyVista-based GraphML viewer for 3D vessel graphs."""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib
from pathlib import Path
from typing import Any, Sequence

import igraph as ig
import numpy as np


NODE_SIZE_RANGE = (0.5, 40.0)
EDGE_THICKNESS_RANGE = (0.1, 10.0)
FILE_PANEL_X = 10
FILE_PANEL_TOP_MARGIN = 12
FILE_PANEL_WIDTH = 300
FILE_PANEL_ROW_HEIGHT = 22
COMMAND_BUTTON_BOTTOM_MARGIN = 18
COMMAND_BUTTON_RIGHT_MARGIN = 28
COMMAND_BUTTON_GAP = 12
COMMAND_BUTTON_HEIGHT = 26
COMMAND_TEXT_Y_OFFSET = 6
SLIDER_COLOR = "#9ea4aa"


class GraphVisualizationError(RuntimeError):
    """Raised when a graph cannot be prepared or displayed."""


@dataclass(slots=True)
class GraphVisualizationData:
    """Graph coordinates and topology prepared for rendering."""

    node_positions: np.ndarray
    edge_indices: np.ndarray
    node_count: int
    edge_count: int
    source_path: str


@dataclass(slots=True)
class GraphVisualizationOptions:
    """User-configurable graph appearance."""

    edge_thickness: float = 2.0
    node_size: float = 6.0
    window_title: str = "SkelHub Graph Viewer"


@dataclass(slots=True)
class GraphVisualizationMeshes:
    """PyVista meshes built from graph visualization data."""

    nodes: Any | None
    edges: Any | None


@dataclass(slots=True)
class CameraState:
    """Camera state captured from a PyVista/VTK camera."""

    position: tuple[float, float, float]
    focal_point: tuple[float, float, float]
    view_up: tuple[float, float, float]
    clipping_range: tuple[float, float] | None = None
    parallel_scale: float | None = None


@dataclass(slots=True)
class LoadedGraphFile:
    """A GraphML file loaded into one viewer session."""

    path: Path
    graph_data: GraphVisualizationData
    initial_camera_state: CameraState | None = None


@dataclass(slots=True)
class UIHitbox:
    """Clickable viewer overlay region in display coordinates."""

    name: str
    x: int
    y: int
    width: int
    height: int
    action: str
    index: int | None = None

    def contains(self, x_pos: int, y_pos: int) -> bool:
        return self.x <= x_pos <= self.x + self.width and self.y <= y_pos <= self.y + self.height


@dataclass(slots=True)
class GraphViewerSession:
    """Mutable state for an interactive graph viewer session."""

    options: GraphVisualizationOptions = field(default_factory=GraphVisualizationOptions)
    loaded_files: list[LoadedGraphFile] = field(default_factory=list)
    active_index: int | None = None
    preview_node_size: float | None = None
    preview_edge_thickness: float | None = None
    graph_actors: list[Any] = field(default_factory=list)
    file_panel_actors: list[Any] = field(default_factory=list)
    command_button_actors: list[Any] = field(default_factory=list)
    file_hitboxes: list[UIHitbox] = field(default_factory=list)
    command_hitboxes: list[UIHitbox] = field(default_factory=list)
    file_list_open: bool = False
    error_actor: Any | None = None

    def __post_init__(self) -> None:
        _validate_options(self.options)
        if self.preview_node_size is None:
            self.preview_node_size = self.options.node_size
        if self.preview_edge_thickness is None:
            self.preview_edge_thickness = self.options.edge_thickness

    @property
    def active_file(self) -> LoadedGraphFile | None:
        if self.active_index is None:
            return None
        if self.active_index < 0 or self.active_index >= len(self.loaded_files):
            return None
        return self.loaded_files[self.active_index]

    @property
    def active_graph_data(self) -> GraphVisualizationData | None:
        active = self.active_file
        return active.graph_data if active is not None else None

    def load_graph(self, input_path: str | Path) -> LoadedGraphFile:
        graph_path = Path(input_path).expanduser().resolve()
        for index, loaded_file in enumerate(self.loaded_files):
            if loaded_file.path == graph_path:
                self.active_index = index
                return loaded_file

        graph_data = load_graph_visualization_data(graph_path)
        loaded_file = LoadedGraphFile(path=graph_path, graph_data=graph_data)
        self.loaded_files.append(loaded_file)
        self.active_index = len(self.loaded_files) - 1
        return loaded_file

    def close_active_file(self) -> None:
        if self.active_index is None:
            return

        del self.loaded_files[self.active_index]
        if not self.loaded_files:
            self.active_index = None
            return
        if self.active_index >= len(self.loaded_files):
            self.active_index = len(self.loaded_files) - 1

    def activate_previous(self) -> None:
        if not self.loaded_files:
            self.active_index = None
            return
        if self.active_index is None:
            self.active_index = 0
            return
        self.active_index = (self.active_index - 1) % len(self.loaded_files)

    def activate_next(self) -> None:
        if not self.loaded_files:
            self.active_index = None
            return
        if self.active_index is None:
            self.active_index = 0
            return
        self.active_index = (self.active_index + 1) % len(self.loaded_files)

    def set_preview_node_size(self, value: float) -> None:
        self.preview_node_size = float(value)

    def set_preview_edge_thickness(self, value: float) -> None:
        self.preview_edge_thickness = float(value)

    def apply_preview_options(self) -> None:
        self.options.node_size = float(self.preview_node_size)
        self.options.edge_thickness = float(self.preview_edge_thickness)
        _validate_options(self.options)

    def status_text(self) -> str:
        active = self.active_file
        if active is None:
            return "No GraphML loaded"
        return f"{self.active_index + 1}/{len(self.loaded_files)}  {active.path.name}"

    def compact_status_text(self, *, max_length: int = 34) -> str:
        text = self.status_text()
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."


def _coerce_coordinate_array(
    values: Sequence[object],
    *,
    axis_name: str,
    node_count: int,
) -> np.ndarray:
    try:
        coords = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise GraphVisualizationError(
            f"GraphML node attribute '{axis_name}' must be numeric for all {node_count} nodes."
        ) from exc

    if coords.shape != (node_count,):
        raise GraphVisualizationError(
            f"GraphML node attribute '{axis_name}' must contain exactly one value per node."
        )

    return coords


def _positions_from_xyz(graph: ig.Graph, attribute_names: tuple[str, str, str]) -> np.ndarray | None:
    x_name, y_name, z_name = attribute_names
    available = set(graph.vs.attribute_names())
    if not {x_name, y_name, z_name}.issubset(available):
        return None

    node_count = graph.vcount()
    x_vals = _coerce_coordinate_array(graph.vs[x_name], axis_name=x_name, node_count=node_count)
    y_vals = _coerce_coordinate_array(graph.vs[y_name], axis_name=y_name, node_count=node_count)
    z_vals = _coerce_coordinate_array(graph.vs[z_name], axis_name=z_name, node_count=node_count)
    return np.column_stack((x_vals, y_vals, z_vals))


def _extract_node_positions(graph: ig.Graph) -> np.ndarray:
    for attribute_names in (("X", "Y", "Z"), ("x", "y", "z")):
        positions = _positions_from_xyz(graph, attribute_names)
        if positions is not None:
            return positions

    raise GraphVisualizationError(
        "GraphML file does not contain renderable 3D coordinates. "
        "Expected node attributes 'X', 'Y', 'Z'."
    )


def _extract_edge_indices(graph: ig.Graph) -> np.ndarray:
    if graph.ecount() == 0:
        return np.empty((0, 2), dtype=int)
    return np.asarray([edge.tuple for edge in graph.es], dtype=int)


def _validate_graph_data(node_positions: np.ndarray, edge_indices: np.ndarray) -> None:
    if node_positions.shape[0] == 0:
        raise GraphVisualizationError("GraphML file does not contain any nodes to render.")
    if not np.isfinite(node_positions).all():
        raise GraphVisualizationError("GraphML file contains non-finite node coordinates and cannot be rendered.")
    if edge_indices.size and (edge_indices.min() < 0 or edge_indices.max() >= node_positions.shape[0]):
        raise GraphVisualizationError("GraphML file contains an edge referencing a missing node.")


def load_graph_visualization_data(input_path: str | Path) -> GraphVisualizationData:
    """Load GraphML node coordinates and edge pairs for PyVista rendering."""
    graph_path = Path(input_path)
    if not graph_path.is_file():
        raise GraphVisualizationError(f"GraphML input does not exist: {graph_path}")

    try:
        graph = ig.Graph.Read_GraphML(str(graph_path))
    except Exception as exc:  # pragma: no cover - igraph raises several concrete types
        raise GraphVisualizationError(f"Failed to load GraphML file '{graph_path}': {exc}") from exc

    node_positions = _extract_node_positions(graph)
    edge_indices = _extract_edge_indices(graph)
    _validate_graph_data(node_positions, edge_indices)
    return GraphVisualizationData(
        node_positions=node_positions,
        edge_indices=edge_indices,
        node_count=graph.vcount(),
        edge_count=graph.ecount(),
        source_path=str(graph_path),
    )


def _import_pyvista() -> Any:
    try:
        return importlib.import_module("pyvista")
    except ImportError as exc:
        raise GraphVisualizationError(
            "PyVista graph visualization could not be initialized. "
            "Install the visualization dependency with `python -m pip install -e .`."
        ) from exc


def _validate_options(options: GraphVisualizationOptions) -> None:
    if options.edge_thickness <= 0:
        raise GraphVisualizationError("--edge_thickness must be greater than zero.")
    if options.node_size <= 0:
        raise GraphVisualizationError("--node_size must be greater than zero.")


def _edge_polyline_array(edge_indices: np.ndarray) -> np.ndarray:
    if edge_indices.size == 0:
        return np.empty(0, dtype=int)
    line_sizes = np.full((edge_indices.shape[0], 1), 2, dtype=int)
    return np.hstack((line_sizes, edge_indices)).ravel()


def build_graph_meshes(
    graph_data: GraphVisualizationData,
    options: GraphVisualizationOptions,
    *,
    pv_module: Any | None = None,
) -> GraphVisualizationMeshes:
    """Build simple PyVista node and edge meshes from graph data."""
    _validate_options(options)
    pv = _import_pyvista() if pv_module is None else pv_module

    node_cloud = pv.PolyData(graph_data.node_positions)
    node_mesh = node_cloud.glyph(
        geom=pv.Sphere(radius=float(options.node_size)),
        orient=False,
        scale=False,
    )

    edge_mesh = None
    if graph_data.edge_indices.size:
        line_data = pv.PolyData(graph_data.node_positions)
        line_data.lines = _edge_polyline_array(graph_data.edge_indices)
        edge_mesh = line_data.tube(radius=float(options.edge_thickness), n_sides=12)

    return GraphVisualizationMeshes(nodes=node_mesh, edges=edge_mesh)


def build_graph_plotter(
    graph_data: GraphVisualizationData | None,
    options: GraphVisualizationOptions,
    *,
    pv_module: Any | None = None,
    off_screen: bool = False,
) -> Any:
    """Create a PyVista plotter containing an optional graph scene."""
    _validate_options(options)
    pv = _import_pyvista() if pv_module is None else pv_module
    plotter = pv.Plotter(title=options.window_title, off_screen=off_screen)
    plotter.set_background("white")
    plotter.add_axes()

    if graph_data is not None:
        meshes = build_graph_meshes(graph_data, options, pv_module=pv)
        if meshes.edges is not None:
            plotter.add_mesh(meshes.edges, color="forestgreen", smooth_shading=True)
        if meshes.nodes is not None:
            plotter.add_mesh(meshes.nodes, color="crimson", smooth_shading=True)
        plotter.reset_camera()

    return plotter


def create_graph_viewer_session(
    input_path: str | Path | None = None,
    *,
    edge_thickness: float = 2.0,
    node_size: float = 6.0,
) -> GraphViewerSession:
    """Create viewer session state and optionally load the initial GraphML file."""
    session = GraphViewerSession(
        options=GraphVisualizationOptions(edge_thickness=edge_thickness, node_size=node_size)
    )
    if input_path is not None:
        session.load_graph(input_path)
    return session


def _plotter_window_size(plotter: Any) -> tuple[int, int]:
    if hasattr(plotter, "window_size"):
        width, height = plotter.window_size
        return int(width), int(height)
    render_window = getattr(plotter, "render_window", None)
    if render_window is not None and hasattr(render_window, "GetSize"):
        width, height = render_window.GetSize()
        return int(width), int(height)
    return 1280, 800


def _remove_actor_list(plotter: Any, actors: list[Any]) -> None:
    if not actors or not hasattr(plotter, "remove_actor"):
        actors.clear()
        return
    for actor in actors:
        if actor is None:
            continue
        try:
            plotter.remove_actor(actor, render=False)
        except TypeError:
            plotter.remove_actor(actor)
    actors.clear()


def _text_actor_property(actor: Any) -> Any | None:
    if hasattr(actor, "GetTextProperty"):
        return actor.GetTextProperty()
    if hasattr(actor, "prop") and hasattr(actor.prop, "GetTextProperty"):
        return actor.prop.GetTextProperty()
    return None


def _add_actor2d(plotter: Any, actor: Any) -> None:
    renderer = getattr(plotter, "renderer", None)
    if renderer is not None and hasattr(renderer, "AddActor2D"):
        renderer.AddActor2D(actor)
        return
    if hasattr(plotter, "add_actor"):
        try:
            plotter.add_actor(actor, render=False)
        except TypeError:
            plotter.add_actor(actor)


def _add_overlay_rect(
    plotter: Any,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    color: tuple[float, float, float],
    opacity: float = 0.92,
) -> Any:
    if hasattr(plotter, "add_overlay_rect"):
        return plotter.add_overlay_rect(x=x, y=y, width=width, height=height, color=color, opacity=opacity)

    try:
        from vtkmodules.vtkCommonCore import vtkPoints
        from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
        from vtkmodules.vtkRenderingCore import vtkActor2D, vtkCoordinate, vtkPolyDataMapper2D
    except ImportError:
        return _add_overlay_text(
            plotter,
            " " * max(width // 5, 1),
            x=x,
            y=y,
            font_size=max(height - 8, 1),
            color="white",
            background_color=color,
            background_opacity=opacity,
        )

    points = vtkPoints()
    for point in ((x, y, 0), (x + width, y, 0), (x + width, y + height, 0), (x, y + height, 0)):
        points.InsertNextPoint(*point)

    polygon = vtkCellArray()
    polygon.InsertNextCell(4)
    for index in range(4):
        polygon.InsertCellPoint(index)

    poly_data = vtkPolyData()
    poly_data.SetPoints(points)
    poly_data.SetPolys(polygon)

    coordinate = vtkCoordinate()
    coordinate.SetCoordinateSystemToDisplay()

    mapper = vtkPolyDataMapper2D()
    mapper.SetInputData(poly_data)
    mapper.SetTransformCoordinate(coordinate)

    actor = vtkActor2D()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(*color)
    actor.GetProperty().SetOpacity(opacity)
    _add_actor2d(plotter, actor)
    return actor


def _add_overlay_text(
    plotter: Any,
    text: str,
    *,
    x: int,
    y: int,
    font_size: int,
    color: str,
    background_color: tuple[float, float, float] | None = None,
    background_opacity: float = 0.88,
) -> Any:
    try:
        actor = plotter.add_text(
            text,
            position=(x, y),
            font_size=font_size,
            color=color,
            font="arial",
        )
    except TypeError:
        actor = plotter.add_text(text, position=(x, y))
    text_property = _text_actor_property(actor)
    if text_property is not None and background_color is not None:
        text_property.SetBackgroundColor(*background_color)
        text_property.SetBackgroundOpacity(background_opacity)
        text_property.SetFrame(True)
        text_property.SetFrameWidth(1)
        text_property.SetFrameColor(*background_color)
    return actor


def render_file_panel(plotter: Any, session: GraphViewerSession) -> None:
    """Draw the compact top-left file status and optional unfolded file list."""
    _remove_actor_list(plotter, session.file_panel_actors)
    session.file_hitboxes.clear()

    _width, height = _plotter_window_size(plotter)
    panel_x = FILE_PANEL_X
    label_y = height - FILE_PANEL_TOP_MARGIN - FILE_PANEL_ROW_HEIGHT
    label_text = f" {session.compact_status_text()} "
    session.file_panel_actors.append(
        _add_overlay_text(
            plotter,
            label_text,
            x=panel_x,
            y=label_y,
            font_size=9,
            color="white",
            background_color=(0.12, 0.16, 0.21),
        )
    )
    session.file_hitboxes.append(
        UIHitbox(
            name="file-panel",
            x=panel_x,
            y=label_y - 2,
            width=FILE_PANEL_WIDTH,
            height=FILE_PANEL_ROW_HEIGHT + 4,
            action="open-file-list",
        )
    )

    if session.file_list_open:
        rows = session.loaded_files or []
        if not rows:
            session.file_panel_actors.append(
                _add_overlay_text(
                    plotter,
                    " No loaded files ",
                    x=panel_x,
                    y=label_y - FILE_PANEL_ROW_HEIGHT,
                    font_size=8,
                    color="#d7dde5",
                    background_color=(0.17, 0.21, 0.27),
                )
            )
        for index, loaded_file in enumerate(rows):
            row_y = label_y - FILE_PANEL_ROW_HEIGHT * (index + 1)
            is_active = index == session.active_index
            prefix = "> " if is_active else "  "
            name = loaded_file.path.name
            if len(name) > 36:
                name = name[:33] + "..."
            session.file_panel_actors.append(
                _add_overlay_text(
                    plotter,
                    f" {prefix}{index + 1}. {name} ",
                    x=panel_x,
                    y=row_y,
                    font_size=8,
                    color="white" if is_active else "#d7dde5",
                    background_color=(0.24, 0.34, 0.43) if is_active else (0.17, 0.21, 0.27),
                )
            )
            session.file_hitboxes.append(
                UIHitbox(
                    name=f"file-{index}",
                    x=panel_x,
                    y=row_y - 2,
                    width=FILE_PANEL_WIDTH,
                    height=FILE_PANEL_ROW_HEIGHT + 4,
                    action="switch-file",
                    index=index,
                )
            )
    if hasattr(plotter, "render"):
        plotter.render()


def _set_status(plotter: Any, session: GraphViewerSession) -> None:
    render_file_panel(plotter, session)


def _set_error(plotter: Any, session: GraphViewerSession, message: str | None) -> None:
    if session.error_actor is not None and hasattr(plotter, "remove_actor"):
        try:
            plotter.remove_actor(session.error_actor, render=False)
        except TypeError:
            plotter.remove_actor(session.error_actor)
        session.error_actor = None
    if message is None:
        return
    session.error_actor = _add_overlay_text(
        plotter,
        f" {message} ",
        x=10,
        y=72,
        font_size=8,
        color="white",
        background_color=(0.55, 0.07, 0.08),
    )


def _camera_tuple(camera: Any, property_name: str, getter_name: str) -> tuple[float, ...] | None:
    if hasattr(camera, getter_name):
        value = getattr(camera, getter_name)()
    elif hasattr(camera, property_name):
        value = getattr(camera, property_name)
    else:
        return None
    return tuple(float(item) for item in value)


def _camera_scalar(camera: Any, property_name: str, getter_name: str) -> float | None:
    if hasattr(camera, getter_name):
        return float(getattr(camera, getter_name)())
    if hasattr(camera, property_name):
        return float(getattr(camera, property_name))
    return None


def _capture_camera_state(plotter: Any) -> CameraState | None:
    camera = getattr(plotter, "camera", None)
    if camera is None:
        return None

    position = _camera_tuple(camera, "position", "GetPosition")
    focal_point = _camera_tuple(camera, "focal_point", "GetFocalPoint")
    view_up = _camera_tuple(camera, "up", "GetViewUp")
    if position is None or focal_point is None or view_up is None:
        return None

    clipping_range = _camera_tuple(camera, "clipping_range", "GetClippingRange")
    parallel_scale = _camera_scalar(camera, "parallel_scale", "GetParallelScale")
    return CameraState(
        position=position,  # type: ignore[arg-type]
        focal_point=focal_point,  # type: ignore[arg-type]
        view_up=view_up,  # type: ignore[arg-type]
        clipping_range=clipping_range,  # type: ignore[arg-type]
        parallel_scale=parallel_scale,
    )


def _set_camera_tuple(camera: Any, property_name: str, setter_name: str, value: tuple[float, ...] | None) -> None:
    if value is None:
        return
    if hasattr(camera, setter_name):
        getattr(camera, setter_name)(*value)
    elif hasattr(camera, property_name):
        setattr(camera, property_name, value)


def _set_camera_scalar(camera: Any, property_name: str, setter_name: str, value: float | None) -> None:
    if value is None:
        return
    if hasattr(camera, setter_name):
        getattr(camera, setter_name)(value)
    elif hasattr(camera, property_name):
        setattr(camera, property_name, value)


def _restore_camera_state(plotter: Any, state: CameraState) -> bool:
    camera = getattr(plotter, "camera", None)
    if camera is None:
        return False

    _set_camera_tuple(camera, "position", "SetPosition", state.position)
    _set_camera_tuple(camera, "focal_point", "SetFocalPoint", state.focal_point)
    _set_camera_tuple(camera, "up", "SetViewUp", state.view_up)
    _set_camera_tuple(camera, "clipping_range", "SetClippingRange", state.clipping_range)
    _set_camera_scalar(camera, "parallel_scale", "SetParallelScale", state.parallel_scale)
    return True


def _store_initial_camera_state(plotter: Any, session: GraphViewerSession) -> None:
    active_file = session.active_file
    if active_file is None or active_file.initial_camera_state is not None:
        return
    active_file.initial_camera_state = _capture_camera_state(plotter)


def _remove_graph_actors(plotter: Any, session: GraphViewerSession) -> None:
    if not session.graph_actors:
        return
    if hasattr(plotter, "remove_actor"):
        for actor in session.graph_actors:
            if actor is not None:
                try:
                    plotter.remove_actor(actor, render=False)
                except TypeError:
                    plotter.remove_actor(actor)
    session.graph_actors.clear()


def render_active_graph(
    plotter: Any,
    session: GraphViewerSession,
    *,
    pv_module: Any | None = None,
    reset_camera: bool = True,
) -> None:
    """Render the active session graph using committed appearance options."""
    _remove_graph_actors(plotter, session)
    graph_data = session.active_graph_data
    if graph_data is None:
        _set_status(plotter, session)
        if hasattr(plotter, "render"):
            plotter.render()
        return

    meshes = build_graph_meshes(graph_data, session.options, pv_module=pv_module)
    if meshes.edges is not None:
        actor = plotter.add_mesh(meshes.edges, color="forestgreen", smooth_shading=True)
        session.graph_actors.append(actor)
    if meshes.nodes is not None:
        actor = plotter.add_mesh(meshes.nodes, color="crimson", smooth_shading=True)
        session.graph_actors.append(actor)
    if reset_camera:
        plotter.reset_camera()
        _store_initial_camera_state(plotter, session)
    _set_status(plotter, session)
    if hasattr(plotter, "render"):
        plotter.render()


def refresh_active_graph(plotter: Any, session: GraphViewerSession, *, pv_module: Any | None = None) -> None:
    """Commit preview slider values and rebuild the active graph scene."""
    session.apply_preview_options()
    render_active_graph(plotter, session, pv_module=pv_module, reset_camera=False)


def reset_active_view(plotter: Any, session: GraphViewerSession) -> None:
    """Restore the initial camera state for the active graph when available."""
    active_file = session.active_file
    restored = False
    if active_file is not None and active_file.initial_camera_state is not None:
        restored = _restore_camera_state(plotter, active_file.initial_camera_state)

    if not restored and hasattr(plotter, "reset_camera"):
        plotter.reset_camera()
        _store_initial_camera_state(plotter, session)
    _set_status(plotter, session)
    if hasattr(plotter, "render"):
        plotter.render()


def import_graph_from_dialog(plotter: Any, session: GraphViewerSession, *, pv_module: Any | None = None) -> bool:
    """Open a small Tk file dialog and load the selected GraphML file."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:  # pragma: no cover - depends on local Tk availability
        _set_error(plotter, session, f"Import unavailable: {exc}")
        return False

    try:
        root = tk.Tk()
        root.withdraw()
        filename = filedialog.askopenfilename(
            title="Import GraphML",
            filetypes=(("GraphML files", "*.graphml"), ("All files", "*.*")),
        )
    except Exception as exc:  # pragma: no cover - depends on desktop availability
        _set_error(plotter, session, f"Import failed: {exc}")
        return False
    finally:
        if "root" in locals():
            root.destroy()

    if not filename:
        return False

    load_graph_paths(plotter, session, [filename], pv_module=pv_module)
    return True


def _graphml_paths(paths: Sequence[str | Path]) -> list[Path]:
    return [Path(path).expanduser() for path in paths if Path(path).suffix.lower() == ".graphml"]


def load_graph_paths(
    plotter: Any,
    session: GraphViewerSession,
    paths: Sequence[str | Path],
    *,
    pv_module: Any | None = None,
) -> list[LoadedGraphFile]:
    """Load GraphML paths into the session and render the first valid file in the batch."""
    loaded_files: list[LoadedGraphFile] = []
    first_loaded_index: int | None = None
    for path in _graphml_paths(paths):
        loaded_file = session.load_graph(path)
        loaded_files.append(loaded_file)
        if first_loaded_index is None:
            first_loaded_index = session.active_index

    if first_loaded_index is not None:
        session.active_index = first_loaded_index
        _set_error(plotter, session, None)
        render_active_graph(plotter, session, pv_module=pv_module)
    return loaded_files


def close_active_graph(plotter: Any, session: GraphViewerSession, *, pv_module: Any | None = None) -> None:
    session.close_active_file()
    render_active_graph(plotter, session, pv_module=pv_module)


def switch_previous_graph(plotter: Any, session: GraphViewerSession, *, pv_module: Any | None = None) -> None:
    session.activate_previous()
    render_active_graph(plotter, session, pv_module=pv_module)


def switch_next_graph(plotter: Any, session: GraphViewerSession, *, pv_module: Any | None = None) -> None:
    session.activate_next()
    render_active_graph(plotter, session, pv_module=pv_module)


def handle_dropped_graphml_paths(
    plotter: Any,
    session: GraphViewerSession,
    paths: Sequence[str | Path],
    *,
    pv_module: Any | None = None,
) -> list[LoadedGraphFile]:
    """Load GraphML files from a drop event, ignoring non-GraphML paths."""
    return load_graph_paths(plotter, session, paths, pv_module=pv_module)


def _extract_dropped_paths(caller: Any) -> list[str]:
    for method_name in ("GetFileNames", "GetDroppedFileNames"):
        if hasattr(caller, method_name):
            names = getattr(caller, method_name)()
            if names is None:
                continue
            if hasattr(names, "GetNumberOfValues"):
                return [names.GetValue(index) for index in range(names.GetNumberOfValues())]
            if isinstance(names, (list, tuple)):
                return [str(name) for name in names]
    if hasattr(caller, "GetEventInformation"):
        info = caller.GetEventInformation()
        if info:
            return str(info).splitlines()
    return []


def install_drop_observer(
    plotter: Any,
    session: GraphViewerSession,
    *,
    pv_module: Any | None = None,
) -> bool:
    """Install a best-effort VTK drop-file observer on the PyVista interactor."""
    interactor = getattr(plotter, "iren", None)
    if interactor is None:
        return False

    def _on_drop(caller: Any, _event: str) -> None:
        paths = _extract_dropped_paths(caller)
        if paths:
            handle_dropped_graphml_paths(plotter, session, paths, pv_module=pv_module)

    if hasattr(interactor, "add_observer"):
        interactor.add_observer("DropFilesEvent", _on_drop)
        return True
    if hasattr(interactor, "AddObserver"):
        interactor.AddObserver("DropFilesEvent", _on_drop)
        return True
    return False


def _all_hitboxes(session: GraphViewerSession) -> list[UIHitbox]:
    return session.file_hitboxes + session.command_hitboxes


def _event_position(caller: Any) -> tuple[int, int] | None:
    if hasattr(caller, "GetEventPosition"):
        x_pos, y_pos = caller.GetEventPosition()
        return int(x_pos), int(y_pos)
    if hasattr(caller, "get_event_position"):
        x_pos, y_pos = caller.get_event_position()
        return int(x_pos), int(y_pos)
    return None


def update_file_list_hover(plotter: Any, session: GraphViewerSession, x_pos: int, y_pos: int) -> bool:
    """Open the file list while the mouse is over the top-left file panel."""
    should_open = any(hitbox.contains(x_pos, y_pos) for hitbox in session.file_hitboxes)
    if should_open == session.file_list_open:
        return False
    session.file_list_open = should_open
    render_file_panel(plotter, session)
    return True


def dispatch_ui_click(
    plotter: Any,
    session: GraphViewerSession,
    x_pos: int,
    y_pos: int,
    *,
    pv_module: Any | None = None,
) -> bool:
    """Dispatch a mouse click to the custom overlay hitbox under the pointer."""
    for hitbox in reversed(_all_hitboxes(session)):
        if not hitbox.contains(x_pos, y_pos):
            continue
        if hitbox.action == "switch-file" and hitbox.index is not None:
            session.active_index = hitbox.index
            render_active_graph(plotter, session, pv_module=pv_module)
            return True
        if hitbox.action == "open-file-list":
            session.file_list_open = True
            render_file_panel(plotter, session)
            return True
        if hitbox.action == "import":
            import_graph_from_dialog(plotter, session, pv_module=pv_module)
            return True
        if hitbox.action == "close":
            close_active_graph(plotter, session, pv_module=pv_module)
            return True
        if hitbox.action == "previous":
            switch_previous_graph(plotter, session, pv_module=pv_module)
            return True
        if hitbox.action == "next":
            switch_next_graph(plotter, session, pv_module=pv_module)
            return True
        if hitbox.action == "refresh":
            refresh_active_graph(plotter, session, pv_module=pv_module)
            return True
        if hitbox.action == "reset-view":
            reset_active_view(plotter, session)
            return True
    return False


def install_ui_mouse_observers(
    plotter: Any,
    session: GraphViewerSession,
    *,
    pv_module: Any | None = None,
) -> bool:
    """Install hover and click observers for custom overlay controls."""
    interactor = getattr(plotter, "iren", None)
    if interactor is None:
        return False

    def _on_mouse_move(caller: Any, _event: str) -> None:
        position = _event_position(caller)
        if position is not None:
            update_file_list_hover(plotter, session, *position)

    def _on_left_click(caller: Any, _event: str) -> None:
        position = _event_position(caller)
        if position is not None:
            dispatch_ui_click(plotter, session, *position, pv_module=pv_module)

    if hasattr(interactor, "add_observer"):
        interactor.add_observer("MouseMoveEvent", _on_mouse_move)
        interactor.add_observer("LeftButtonPressEvent", _on_left_click)
        return True
    if hasattr(interactor, "AddObserver"):
        interactor.AddObserver("MouseMoveEvent", _on_mouse_move)
        interactor.AddObserver("LeftButtonPressEvent", _on_left_click)
        return True
    return False


def render_command_buttons(plotter: Any, session: GraphViewerSession) -> None:
    """Draw compact custom command buttons in a right-aligned lower row."""
    _remove_actor_list(plotter, session.command_button_actors)
    session.command_hitboxes.clear()
    buttons = (
        ("Import", "import", 68, (0.19, 0.26, 0.34)),
        ("Close", "close", 68, (0.20, 0.24, 0.30)),
        ("<", "previous", 40, (0.15, 0.22, 0.31)),
        (">", "next", 40, (0.15, 0.22, 0.31)),
        ("Refresh", "refresh", 78, (0.70, 0.08, 0.09)),
        ("Reset View", "reset-view", 98, (0.05, 0.28, 0.68)),
    )
    window_width, _height = _plotter_window_size(plotter)
    total_width = sum(width for _label, _action, width, _background in buttons)
    total_width += COMMAND_BUTTON_GAP * (len(buttons) - 1)
    x_pos = max(COMMAND_BUTTON_RIGHT_MARGIN, window_width - COMMAND_BUTTON_RIGHT_MARGIN - total_width)
    y_pos = COMMAND_BUTTON_BOTTOM_MARGIN
    for label, action, width, background in buttons:
        text_width = max(len(label) * 7, 8)
        text_x = x_pos + max((width - text_width) // 2, 2)
        text_y = y_pos + COMMAND_TEXT_Y_OFFSET
        session.command_button_actors.append(
            _add_overlay_rect(
                plotter,
                x=x_pos,
                y=y_pos,
                width=width,
                height=COMMAND_BUTTON_HEIGHT,
                color=background,
                opacity=0.92,
            )
        )
        session.command_button_actors.append(
            _add_overlay_text(
                plotter,
                label,
                x=text_x,
                y=text_y,
                font_size=8 if len(label) > 1 else 11,
                color="white",
            )
        )
        session.command_hitboxes.append(
            UIHitbox(
                name=f"button-{action}",
                x=x_pos,
                y=y_pos,
                width=width,
                height=COMMAND_BUTTON_HEIGHT,
                action=action,
            )
        )
        x_pos += width + COMMAND_BUTTON_GAP


def _style_slider_widget(widget: Any) -> None:
    if widget is None or not hasattr(widget, "GetRepresentation"):
        return
    representation = widget.GetRepresentation()
    for method_name, value in (
        ("SetSliderLength", 0.018),
        ("SetSliderWidth", 0.026),
        ("SetTubeWidth", 0.010),
        ("SetEndCapLength", 0.006),
        ("SetEndCapWidth", 0.014),
    ):
        if hasattr(representation, method_name):
            getattr(representation, method_name)(value)
    for property_name, color in (
        ("GetSliderProperty", (0.62, 0.65, 0.69)),
        ("GetTubeProperty", (0.78, 0.80, 0.83)),
        ("GetCapProperty", (0.52, 0.55, 0.59)),
    ):
        if not hasattr(representation, property_name):
            continue
        prop = getattr(representation, property_name)()
        if hasattr(prop, "SetColor"):
            prop.SetColor(*color)
        if hasattr(prop, "SetOpacity"):
            prop.SetOpacity(1.0)


def add_graph_viewer_controls(plotter: Any, session: GraphViewerSession, *, pv_module: Any | None = None) -> None:
    """Add pure-PyVista controls for file/session management and appearance preview."""
    render_file_panel(plotter, session)
    render_command_buttons(plotter, session)
    node_slider = plotter.add_slider_widget(
        lambda value: session.set_preview_node_size(value),
        NODE_SIZE_RANGE,
        value=session.preview_node_size,
        title="Node",
        pointa=(0.76, 0.93),
        pointb=(0.96, 0.93),
        color=SLIDER_COLOR,
        title_color="#40464d",
        style="modern",
        title_height=0.018,
        fmt="%.2g",
        slider_width=0.018,
        tube_width=0.010,
        interaction_event="always",
    )
    _style_slider_widget(node_slider)
    edge_slider = plotter.add_slider_widget(
        lambda value: session.set_preview_edge_thickness(value),
        EDGE_THICKNESS_RANGE,
        value=session.preview_edge_thickness,
        title="Edge",
        pointa=(0.76, 0.83),
        pointb=(0.96, 0.83),
        color=SLIDER_COLOR,
        title_color="#40464d",
        style="modern",
        title_height=0.018,
        fmt="%.2g",
        slider_width=0.018,
        tube_width=0.010,
        interaction_event="always",
    )
    _style_slider_widget(edge_slider)
    install_ui_mouse_observers(plotter, session, pv_module=pv_module)


def launch_graph_viewer(
    input_path: str | Path | None = None,
    *,
    edge_thickness: float = 2.0,
    node_size: float = 6.0,
) -> int:
    """Launch an interactive PyVista window for an optional GraphML file."""
    pv = _import_pyvista()
    session = create_graph_viewer_session(input_path, edge_thickness=edge_thickness, node_size=node_size)
    plotter = build_graph_plotter(None, session.options, pv_module=pv)
    render_active_graph(plotter, session, pv_module=pv)
    add_graph_viewer_controls(plotter, session, pv_module=pv)
    install_drop_observer(plotter, session, pv_module=pv)
    plotter.show()
    return 0
