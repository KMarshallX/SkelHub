"""PyVista-based viewer for 3D vessel graphs and binary NIfTI volumes."""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib
from pathlib import Path
from typing import Any, Literal, Sequence

import igraph as ig
import nibabel as nib
import numpy as np


VisualizationFileKind = Literal["graphml", "nifti"]
GraphRenderMode = Literal["detailed", "dense"]
CursorAxis = Literal["x", "y", "z"]
NODE_SIZE_RANGE = (0.5, 40.0)
EDGE_THICKNESS_RANGE = (0.1, 10.0)
DENSE_GRAPH_NODE_THRESHOLD = 1_000
LARGE_NIFTI_VOXEL_WARNING_THRESHOLD = 250_000
FILE_PANEL_X = 10
FILE_PANEL_TOP_MARGIN = 12
FILE_PANEL_WIDTH = 300
FILE_PANEL_ROW_HEIGHT = 22
TOOLS_PANEL_RIGHT_MARGIN = 18
TOOLS_PANEL_TOP_MARGIN = 12
TOOLS_BUTTON_WIDTH = 76
TOOLS_PANEL_WIDTH = 292
TOOLS_PANEL_HEIGHT = 436
TOOLS_PANEL_GAP = 8
TOOLS_PANEL_PADDING = 14
COMMAND_BUTTON_GAP = 10
COMMAND_BUTTON_HEIGHT = 26
CURSOR_ROWS_HEIGHT = 144
CURSOR_FIELD_LABEL_WIDTH = 28
CURSOR_CROSSHAIR_RADIUS = 11
SLIDER_STEP = 0.1
SLIDER_STEP_BUTTON_SIZE = 26
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

    edge_thickness: float = 1.0
    node_size: float = 2.5
    window_title: str = "SkelHub Graph Viewer"


@dataclass(slots=True)
class GraphVisualizationMeshes:
    """PyVista meshes built from graph visualization data."""

    nodes: Any | None
    edges: Any | None


@dataclass(slots=True)
class NiftiVisualizationData:
    """Binary NIfTI foreground voxels prepared for block rendering."""

    voxel_positions: np.ndarray
    voxel_count: int
    shape: tuple[int, int, int]
    source_path: str


@dataclass(slots=True)
class NiftiVisualizationMeshes:
    """PyVista meshes built from NIfTI visualization data."""

    blocks: Any | None


@dataclass(slots=True)
class CameraState:
    """Camera state captured from a PyVista/VTK camera."""

    position: tuple[float, float, float]
    focal_point: tuple[float, float, float]
    view_up: tuple[float, float, float]
    clipping_range: tuple[float, float] | None = None
    parallel_scale: float | None = None


@dataclass(slots=True)
class LoadedVisualizationFile:
    """A visualization file loaded into one viewer session."""

    path: Path
    kind: VisualizationFileKind
    data: GraphVisualizationData | NiftiVisualizationData
    initial_camera_state: CameraState | None = None
    cursor_position: tuple[float, float, float] | None = None
    cursor_enabled: bool = False


LoadedGraphFile = LoadedVisualizationFile


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
    loaded_files: list[LoadedVisualizationFile] = field(default_factory=list)
    active_index: int | None = None
    preview_node_size: float | None = None
    preview_edge_thickness: float | None = None
    graph_actors: list[Any] = field(default_factory=list)
    dense_node_actor: Any | None = None
    dense_edge_actor: Any | None = None
    file_panel_actors: list[Any] = field(default_factory=list)
    tools_button_actors: list[Any] = field(default_factory=list)
    tools_panel_actors: list[Any] = field(default_factory=list)
    command_button_actors: list[Any] = field(default_factory=list)
    cursor_actors: list[Any] = field(default_factory=list)
    slider_widgets: list[Any] = field(default_factory=list)
    file_hitboxes: list[UIHitbox] = field(default_factory=list)
    tools_hitboxes: list[UIHitbox] = field(default_factory=list)
    command_hitboxes: list[UIHitbox] = field(default_factory=list)
    sliders_visible: bool = False
    file_list_open: bool = False
    tools_panel_visible: bool = False
    cursor_dragging: bool = False
    cursor_drag_display_depth: float | None = None
    cursor_edit_axis: CursorAxis | None = None
    cursor_edit_buffer: str = ""
    cursor_edit_invalid: bool = False
    cursor_edit_replace_pending: bool = False
    error_actor: Any | None = None

    def __post_init__(self) -> None:
        _validate_options(self.options)
        if self.preview_node_size is None:
            self.preview_node_size = self.options.node_size
        if self.preview_edge_thickness is None:
            self.preview_edge_thickness = self.options.edge_thickness

    @property
    def active_file(self) -> LoadedVisualizationFile | None:
        if self.active_index is None:
            return None
        if self.active_index < 0 or self.active_index >= len(self.loaded_files):
            return None
        return self.loaded_files[self.active_index]

    @property
    def active_graph_data(self) -> GraphVisualizationData | None:
        active = self.active_file
        if active is None or active.kind != "graphml":
            return None
        return active.data  # type: ignore[return-value]

    @property
    def active_nifti_data(self) -> NiftiVisualizationData | None:
        active = self.active_file
        if active is None or active.kind != "nifti":
            return None
        return active.data  # type: ignore[return-value]

    @property
    def active_kind(self) -> VisualizationFileKind | None:
        active = self.active_file
        return active.kind if active is not None else None

    @property
    def cursor_enabled(self) -> bool:
        active = self.active_file
        return bool(active is not None and active.cursor_enabled)

    @cursor_enabled.setter
    def cursor_enabled(self, enabled: bool) -> None:
        active = self.active_file
        if active is not None:
            active.cursor_enabled = bool(enabled)

    def load_graph(self, input_path: str | Path) -> LoadedGraphFile:
        return self.load_visualization(input_path)

    def load_visualization(
        self,
        input_path: str | Path,
        *,
        allow_large_nifti: bool = False,
    ) -> LoadedVisualizationFile:
        graph_path = Path(input_path).expanduser().resolve()
        for index, loaded_file in enumerate(self.loaded_files):
            if loaded_file.path == graph_path:
                self.active_index = index
                return loaded_file

        kind = _visualization_file_kind(graph_path)
        if kind == "graphml":
            data: GraphVisualizationData | NiftiVisualizationData = load_graph_visualization_data(graph_path)
        elif kind == "nifti":
            data = load_nifti_visualization_data(graph_path)
            if data.voxel_count > LARGE_NIFTI_VOXEL_WARNING_THRESHOLD and not allow_large_nifti:
                raise GraphVisualizationError(
                    "NIfTI foreground voxel count "
                    f"{data.voxel_count} exceeds the interactive warning threshold "
                    f"{LARGE_NIFTI_VOXEL_WARNING_THRESHOLD}."
                )
        else:  # pragma: no cover - kept defensive for future file kinds
            raise GraphVisualizationError(f"Unsupported visualization file type: {graph_path}")

        loaded_file = LoadedVisualizationFile(path=graph_path, kind=kind, data=data)
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
            return "No file loaded"
        kind_label = _kind_label(active.kind)
        if active.kind == "graphml" and _graph_render_mode(active.data) == "dense":
            kind_label = "[GraphML Dense]"
        return f"{self.active_index + 1}/{len(self.loaded_files)}  {kind_label}  {active.path.name}"

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


def _is_nifti_path(path: str | Path) -> bool:
    path_text = str(path).lower()
    return path_text.endswith(".nii") or path_text.endswith(".nii.gz")


def _visualization_file_kind(path: str | Path) -> VisualizationFileKind:
    if Path(path).suffix.lower() == ".graphml":
        return "graphml"
    if _is_nifti_path(path):
        return "nifti"
    raise GraphVisualizationError(
        f"Unsupported visualization file type: {path}. Expected .graphml, .nii, or .nii.gz."
    )


def _kind_label(kind: VisualizationFileKind) -> str:
    return "[GraphML]" if kind == "graphml" else "[NIfTI]"


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


def _is_binary_array(values: np.ndarray) -> bool:
    unique_values = np.unique(values)
    if unique_values.size == 0:
        return True
    return bool(np.isin(unique_values, (0, 1)).all())


def _format_unique_preview(values: np.ndarray) -> str:
    unique_values = np.unique(values)
    preview = ", ".join(str(value) for value in unique_values[:10])
    if unique_values.size > 10:
        preview += ", ..."
    return preview


def load_nifti_visualization_data(input_path: str | Path) -> NiftiVisualizationData:
    """Load a binary NIfTI volume as foreground voxel positions for block rendering."""
    nifti_path = Path(input_path)
    if not nifti_path.is_file():
        raise GraphVisualizationError(f"NIfTI input does not exist: {nifti_path}")
    if not _is_nifti_path(nifti_path):
        raise GraphVisualizationError(f"NIfTI input must be a .nii or .nii.gz file: {nifti_path}")

    try:
        image = nib.load(str(nifti_path))
    except Exception as exc:  # pragma: no cover - nibabel raises several concrete types
        raise GraphVisualizationError(f"Failed to load NIfTI file '{nifti_path}': {exc}") from exc
    if not isinstance(image, nib.Nifti1Image):
        image = nib.Nifti1Image.from_image(image)

    data = np.asarray(image.dataobj)
    if data.ndim != 3:
        raise GraphVisualizationError(f"NIfTI file must contain a 3D volume. Got ndim={data.ndim}.")
    if not _is_binary_array(data):
        raise GraphVisualizationError(
            "NIfTI file must be binarized before import. "
            f"Expected values {{0, 1}}; found [{_format_unique_preview(data)}]."
        )

    voxel_positions = np.argwhere(data > 0).astype(float, copy=False)
    return NiftiVisualizationData(
        voxel_positions=voxel_positions,
        voxel_count=int(voxel_positions.shape[0]),
        shape=tuple(int(size) for size in data.shape),
        source_path=str(nifti_path),
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


def _graph_render_mode(graph_data: GraphVisualizationData) -> GraphRenderMode:
    return "dense" if graph_data.node_count >= DENSE_GRAPH_NODE_THRESHOLD else "detailed"


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


def _build_instanced_node_actor(
    graph_data: GraphVisualizationData,
    options: GraphVisualizationOptions,
    *,
    pv_module: Any | None = None,
) -> Any:
    """Build one shared sphere glyph source instanced at every graph node."""
    _validate_options(options)
    pv = _import_pyvista() if pv_module is None else pv_module

    try:
        from vtkmodules.vtkRenderingCore import vtkActor, vtkGlyph3DMapper
    except ImportError as exc:  # pragma: no cover - PyVista installations include VTK
        raise GraphVisualizationError("VTK glyph rendering could not be initialized.") from exc

    node_cloud = pv.PolyData(graph_data.node_positions)
    node_sphere = pv.Sphere(radius=float(options.node_size))
    mapper = vtkGlyph3DMapper()
    mapper.SetInputData(node_cloud)
    mapper.SetSourceData(node_sphere)
    mapper.OrientOff()
    mapper.ScalingOff()
    mapper.ScalarVisibilityOff()

    actor = vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(220 / 255, 20 / 255, 60 / 255)
    actor.GetProperty().SetInterpolationToPhong()
    return actor


def _add_detailed_graph_scene(
    plotter: Any,
    graph_data: GraphVisualizationData,
    options: GraphVisualizationOptions,
    *,
    pv_module: Any | None = None,
) -> list[Any]:
    """Add detailed graph edges and instanced nodes without rendering."""
    _validate_options(options)
    pv = _import_pyvista() if pv_module is None else pv_module
    actors: list[Any] = []

    if graph_data.edge_indices.size:
        line_data = pv.PolyData(graph_data.node_positions)
        line_data.lines = _edge_polyline_array(graph_data.edge_indices)
        edge_mesh = line_data.tube(radius=float(options.edge_thickness), n_sides=12)
        actors.append(
            plotter.add_mesh(edge_mesh, color="forestgreen", smooth_shading=True, render=False)
        )

    node_actor = _build_instanced_node_actor(graph_data, options, pv_module=pv)
    try:
        plotter.add_actor(node_actor, render=False)
    except TypeError:
        plotter.add_actor(node_actor)
    actors.append(node_actor)
    return actors


def _add_dense_graph_scene(
    plotter: Any,
    graph_data: GraphVisualizationData,
    options: GraphVisualizationOptions,
    *,
    pv_module: Any | None = None,
) -> tuple[list[Any], Any | None, Any]:
    """Add lightweight point/line actors for large interactive graphs."""
    _validate_options(options)
    pv = _import_pyvista() if pv_module is None else pv_module
    actors: list[Any] = []
    edge_actor = None

    if graph_data.edge_indices.size:
        line_data = pv.PolyData()
        line_data.points = graph_data.node_positions
        line_data.lines = _edge_polyline_array(graph_data.edge_indices)
        edge_actor = plotter.add_mesh(
            line_data,
            color="forestgreen",
            line_width=float(options.edge_thickness),
            render_lines_as_tubes=True,
            render=False,
        )
        actors.append(edge_actor)

    node_cloud = pv.PolyData(graph_data.node_positions)
    node_actor = plotter.add_mesh(
        node_cloud,
        color="crimson",
        style="points",
        point_size=float(options.node_size),
        render_points_as_spheres=True,
        render=False,
    )
    actors.append(node_actor)
    return actors, edge_actor, node_actor


def _add_graph_scene(
    plotter: Any,
    graph_data: GraphVisualizationData,
    options: GraphVisualizationOptions,
    *,
    pv_module: Any | None = None,
) -> list[Any]:
    """Add a detailed or automatically lightweight GraphML scene."""
    if _graph_render_mode(graph_data) == "dense":
        actors, _edge_actor, _node_actor = _add_dense_graph_scene(
            plotter, graph_data, options, pv_module=pv_module
        )
        return actors
    return _add_detailed_graph_scene(plotter, graph_data, options, pv_module=pv_module)


def build_nifti_meshes(
    nifti_data: NiftiVisualizationData,
    *,
    pv_module: Any | None = None,
) -> NiftiVisualizationMeshes:
    """Build a PyVista block mesh from binary NIfTI foreground voxels."""
    pv = _import_pyvista() if pv_module is None else pv_module
    if nifti_data.voxel_count == 0:
        return NiftiVisualizationMeshes(blocks=None)

    voxel_cloud = pv.PolyData(nifti_data.voxel_positions)
    cube = pv.Cube(x_length=1.0, y_length=1.0, z_length=1.0)
    block_mesh = voxel_cloud.glyph(geom=cube, orient=False, scale=False)
    return NiftiVisualizationMeshes(blocks=block_mesh)


def _build_instanced_nifti_actor(
    nifti_data: NiftiVisualizationData,
    *,
    pv_module: Any | None = None,
) -> Any | None:
    """Build one shared unit-cube source instanced at foreground voxels."""
    if nifti_data.voxel_count == 0:
        return None
    pv = _import_pyvista() if pv_module is None else pv_module

    try:
        from vtkmodules.vtkRenderingCore import vtkActor, vtkGlyph3DMapper
    except ImportError as exc:  # pragma: no cover - PyVista installations include VTK
        raise GraphVisualizationError("VTK NIfTI block rendering could not be initialized.") from exc

    voxel_cloud = pv.PolyData(nifti_data.voxel_positions)
    cube = pv.Cube(x_length=1.0, y_length=1.0, z_length=1.0)
    mapper = vtkGlyph3DMapper()
    mapper.SetInputData(voxel_cloud)
    mapper.SetSourceData(cube)
    mapper.OrientOff()
    mapper.ScalingOff()
    mapper.ScalarVisibilityOff()

    actor = vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(76 / 255, 120 / 255, 168 / 255)
    actor.GetProperty().SetEdgeVisibility(True)
    actor.GetProperty().SetEdgeColor(31 / 255, 41 / 255, 51 / 255)
    return actor


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
        _add_graph_scene(plotter, graph_data, options, pv_module=pv)
        plotter.reset_camera()

    return plotter


def create_graph_viewer_session(
    input_path: str | Path | None = None,
    *,
    edge_thickness: float = 1.0,
    node_size: float = 2.5,
) -> GraphViewerSession:
    """Create viewer session state and optionally load an initial visualization file."""
    session = GraphViewerSession(
        options=GraphVisualizationOptions(edge_thickness=edge_thickness, node_size=node_size)
    )
    if input_path is not None:
        session.load_visualization(input_path)
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
            name = f"{_kind_label(loaded_file.kind)} {loaded_file.path.name}"
            if len(name) > 42:
                name = name[:39] + "..."
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


def _scene_cursor_center(active_file: LoadedVisualizationFile) -> tuple[float, float, float]:
    """Return the initial cursor position in the active file's scene coordinates."""
    if active_file.kind == "graphml":
        positions = active_file.data.node_positions  # type: ignore[union-attr]
    else:
        nifti_data = active_file.data
        positions = nifti_data.voxel_positions  # type: ignore[union-attr]
        if positions.shape[0] == 0:
            return tuple((float(size) - 1.0) / 2.0 for size in nifti_data.shape)  # type: ignore[union-attr]
    lower = positions.min(axis=0)
    upper = positions.max(axis=0)
    return tuple(float(value) for value in (lower + upper) / 2.0)  # type: ignore[return-value]


def _ensure_cursor_position(session: GraphViewerSession) -> tuple[float, float, float] | None:
    active_file = session.active_file
    if active_file is None:
        return None
    if active_file.cursor_position is None:
        active_file.cursor_position = _scene_cursor_center(active_file)
    return active_file.cursor_position


def _clear_cursor_edit(session: GraphViewerSession) -> None:
    session.cursor_edit_axis = None
    session.cursor_edit_buffer = ""
    session.cursor_edit_invalid = False
    session.cursor_edit_replace_pending = False


def _format_cursor_coordinate(value: float) -> str:
    return f"{float(value):.6g}"


def _set_cursor_position(session: GraphViewerSession, position: Sequence[float]) -> bool:
    active_file = session.active_file
    if active_file is None:
        return False
    values = tuple(float(value) for value in position)
    if len(values) != 3 or not np.isfinite(values).all():
        return False
    active_file.cursor_position = values  # type: ignore[assignment]
    return True


def _cursor_display_point(plotter: Any, position: Sequence[float]) -> tuple[float, float, float] | None:
    renderer = getattr(plotter, "renderer", None)
    if renderer is None or not all(
        hasattr(renderer, method_name) for method_name in ("SetWorldPoint", "WorldToDisplay", "GetDisplayPoint")
    ):
        return None
    renderer.SetWorldPoint(float(position[0]), float(position[1]), float(position[2]), 1.0)
    renderer.WorldToDisplay()
    display_point = renderer.GetDisplayPoint()
    if display_point is None or len(display_point) < 3 or not np.isfinite(display_point[:3]).all():
        return None
    return tuple(float(value) for value in display_point[:3])  # type: ignore[return-value]


def _cursor_world_point(plotter: Any, x_pos: int, y_pos: int, depth: float) -> tuple[float, float, float] | None:
    renderer = getattr(plotter, "renderer", None)
    if renderer is None or not all(
        hasattr(renderer, method_name) for method_name in ("SetDisplayPoint", "DisplayToWorld", "GetWorldPoint")
    ):
        return None
    renderer.SetDisplayPoint(float(x_pos), float(y_pos), float(depth))
    renderer.DisplayToWorld()
    world_point = renderer.GetWorldPoint()
    if world_point is None or len(world_point) < 4 or float(world_point[3]) == 0.0:
        return None
    position = tuple(float(world_point[index]) / float(world_point[3]) for index in range(3))
    return position if np.isfinite(position).all() else None


def render_cursor_crosshair(plotter: Any, session: GraphViewerSession) -> None:
    """Project and draw the active file's 3D cursor as a viewport crosshair."""
    _remove_actor_list(plotter, session.cursor_actors)
    if not session.cursor_enabled:
        return
    position = _ensure_cursor_position(session)
    if position is None:
        session.cursor_enabled = False
        return
    display_point = _cursor_display_point(plotter, position)
    if display_point is None:
        return
    center_x, center_y = (int(round(display_point[0])), int(round(display_point[1])))
    radius = CURSOR_CROSSHAIR_RADIUS
    session.cursor_actors.extend(
        (
            _add_overlay_rect(
                plotter,
                x=center_x - radius,
                y=center_y - 1,
                width=2 * radius + 1,
                height=2,
                color=(0.93, 0.33, 0.08),
                opacity=0.98,
            ),
            _add_overlay_rect(
                plotter,
                x=center_x - 1,
                y=center_y - radius,
                width=2,
                height=2 * radius + 1,
                color=(0.93, 0.33, 0.08),
                opacity=0.98,
            ),
        )
    )


def toggle_cursor(plotter: Any, session: GraphViewerSession) -> None:
    """Enable or disable the per-file scene cursor."""
    if session.active_file is None:
        return
    session.cursor_enabled = not session.cursor_enabled
    session.cursor_dragging = False
    session.cursor_drag_display_depth = None
    _clear_cursor_edit(session)
    if session.cursor_enabled:
        _ensure_cursor_position(session)
    render_tools_panel(plotter, session)
    if hasattr(plotter, "render"):
        plotter.render()


def _begin_cursor_edit(plotter: Any, session: GraphViewerSession, axis: CursorAxis) -> None:
    if not session.cursor_enabled:
        return
    position = _ensure_cursor_position(session)
    if position is None:
        return
    index = ("x", "y", "z").index(axis)
    session.cursor_edit_axis = axis
    session.cursor_edit_buffer = _format_cursor_coordinate(position[index])
    session.cursor_edit_invalid = False
    session.cursor_edit_replace_pending = True
    render_tools_panel(plotter, session)
    if hasattr(plotter, "render"):
        plotter.render()


def _commit_cursor_edit(plotter: Any, session: GraphViewerSession) -> bool:
    axis = session.cursor_edit_axis
    position = _ensure_cursor_position(session)
    if axis is None or position is None:
        return False
    try:
        value = float(session.cursor_edit_buffer)
    except ValueError:
        value = float("nan")
    if not np.isfinite(value):
        session.cursor_edit_invalid = True
        render_tools_panel(plotter, session)
        if hasattr(plotter, "render"):
            plotter.render()
        return False
    next_position = list(position)
    next_position[("x", "y", "z").index(axis)] = value
    _set_cursor_position(session, next_position)
    _clear_cursor_edit(session)
    render_tools_panel(plotter, session)
    if hasattr(plotter, "render"):
        plotter.render()
    return True


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
        session.dense_node_actor = None
        session.dense_edge_actor = None
        return
    if hasattr(plotter, "remove_actor"):
        for actor in session.graph_actors:
            if actor is not None:
                try:
                    plotter.remove_actor(actor, render=False)
                except TypeError:
                    plotter.remove_actor(actor)
    session.graph_actors.clear()
    session.dense_node_actor = None
    session.dense_edge_actor = None


def _update_dense_graph_appearance(session: GraphViewerSession) -> bool:
    """Apply dense point/line widths without reconstructing rendered data."""
    if session.dense_node_actor is None:
        return False
    session.dense_node_actor.GetProperty().SetPointSize(float(session.options.node_size))
    if session.dense_edge_actor is not None:
        session.dense_edge_actor.GetProperty().SetLineWidth(float(session.options.edge_thickness))
    return True


def render_active_graph(
    plotter: Any,
    session: GraphViewerSession,
    *,
    pv_module: Any | None = None,
    reset_camera: bool = True,
) -> None:
    """Render the active session file using committed appearance options."""
    _remove_graph_actors(plotter, session)
    active_file = session.active_file
    if active_file is None:
        _set_status(plotter, session)
        render_tools_panel(plotter, session)
        if hasattr(plotter, "render"):
            plotter.render()
        return

    if active_file.kind == "graphml":
        graph_data = session.active_graph_data
        if graph_data is not None:
            if _graph_render_mode(graph_data) == "dense":
                actors, session.dense_edge_actor, session.dense_node_actor = _add_dense_graph_scene(
                    plotter, graph_data, session.options, pv_module=pv_module
                )
                session.graph_actors.extend(actors)
            else:
                session.graph_actors.extend(
                    _add_detailed_graph_scene(plotter, graph_data, session.options, pv_module=pv_module)
                )
    else:
        nifti_data = session.active_nifti_data
        if nifti_data is not None:
            actor = _build_instanced_nifti_actor(nifti_data, pv_module=pv_module)
            if actor is not None:
                try:
                    plotter.add_actor(actor, render=False)
                except TypeError:
                    plotter.add_actor(actor)
                session.graph_actors.append(actor)
    if reset_camera:
        plotter.reset_camera()
        _store_initial_camera_state(plotter, session)
    _set_status(plotter, session)
    render_tools_panel(plotter, session)
    if hasattr(plotter, "render"):
        plotter.render()


def refresh_active_graph(plotter: Any, session: GraphViewerSession, *, pv_module: Any | None = None) -> None:
    """Commit preview slider values when relevant and rebuild the active scene."""
    if session.active_kind != "nifti":
        session.apply_preview_options()
        graph_data = session.active_graph_data
        if (
            graph_data is not None
            and _graph_render_mode(graph_data) == "dense"
            and _update_dense_graph_appearance(session)
        ):
            if hasattr(plotter, "render"):
                plotter.render()
            return
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
    render_cursor_crosshair(plotter, session)
    if hasattr(plotter, "render"):
        plotter.render()


def _show_warning_dialog(title: str, message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox
    except Exception:
        return

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning(title, message, parent=root)
    except Exception:
        return
    finally:
        if root is not None:
            root.destroy()


def _confirm_large_nifti(path: Path, voxel_count: int) -> bool:
    try:
        import tkinter as tk
        from tkinter import messagebox
    except Exception:
        return False

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        return bool(
            messagebox.askyesno(
                "Large NIfTI volume",
                "This NIfTI file contains "
                f"{voxel_count} foreground voxels. Rendering one block per voxel may be slow.\n\n"
                f"Load {path.name} anyway?",
                parent=root,
            )
        )
    except Exception:
        return False
    finally:
        if root is not None:
            root.destroy()


def import_graph_from_dialog(plotter: Any, session: GraphViewerSession, *, pv_module: Any | None = None) -> bool:
    """Open a small Tk file dialog and load the selected visualization file."""
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
            title="Import Visualization File",
            filetypes=(
                ("Supported files", "*.graphml *.nii *.nii.gz"),
                ("GraphML files", "*.graphml"),
                ("NIfTI files", "*.nii *.nii.gz"),
                ("All files", "*.*"),
            ),
        )
    except Exception as exc:  # pragma: no cover - depends on desktop availability
        _set_error(plotter, session, f"Import failed: {exc}")
        return False
    finally:
        if "root" in locals():
            root.destroy()

    if not filename:
        return False

    load_visualization_paths(plotter, session, [filename], pv_module=pv_module, interactive=True)
    return True


def _visualization_paths(paths: Sequence[str | Path]) -> list[Path]:
    supported: list[Path] = []
    for path in paths:
        expanded = Path(path).expanduser()
        if expanded.suffix.lower() == ".graphml" or _is_nifti_path(expanded):
            supported.append(expanded)
    return supported


def load_visualization_paths(
    plotter: Any,
    session: GraphViewerSession,
    paths: Sequence[str | Path],
    *,
    pv_module: Any | None = None,
    interactive: bool = False,
    allow_large_nifti: bool = False,
) -> list[LoadedVisualizationFile]:
    """Load supported visualization paths and render the first valid file in the batch."""
    loaded_files: list[LoadedVisualizationFile] = []
    first_loaded_index: int | None = None
    for path in _visualization_paths(paths):
        try:
            kind = _visualization_file_kind(path)
            allow_large = allow_large_nifti
            if kind == "nifti" and not allow_large:
                nifti_data = load_nifti_visualization_data(path)
                if nifti_data.voxel_count > LARGE_NIFTI_VOXEL_WARNING_THRESHOLD:
                    if interactive and _confirm_large_nifti(Path(path), nifti_data.voxel_count):
                        allow_large = True
                    else:
                        _set_error(plotter, session, f"Skipped large NIfTI: {Path(path).name}")
                        continue
            loaded_file = session.load_visualization(path, allow_large_nifti=allow_large)
        except GraphVisualizationError as exc:
            if interactive:
                _show_warning_dialog("Import rejected", str(exc))
            _set_error(plotter, session, str(exc))
            continue
        loaded_files.append(loaded_file)
        if first_loaded_index is None:
            first_loaded_index = session.active_index

    if first_loaded_index is not None:
        session.active_index = first_loaded_index
        _set_error(plotter, session, None)
        render_active_graph(plotter, session, pv_module=pv_module)
    return loaded_files


def load_graph_paths(
    plotter: Any,
    session: GraphViewerSession,
    paths: Sequence[str | Path],
    *,
    pv_module: Any | None = None,
) -> list[LoadedGraphFile]:
    """Load GraphML paths into the session and render the first valid file in the batch."""
    graphml_paths = [path for path in paths if Path(path).suffix.lower() == ".graphml"]
    return load_visualization_paths(plotter, session, graphml_paths, pv_module=pv_module)


def close_active_graph(plotter: Any, session: GraphViewerSession, *, pv_module: Any | None = None) -> None:
    _clear_cursor_edit(session)
    _end_cursor_drag(session)
    session.close_active_file()
    render_active_graph(plotter, session, pv_module=pv_module)


def switch_previous_graph(plotter: Any, session: GraphViewerSession, *, pv_module: Any | None = None) -> None:
    _clear_cursor_edit(session)
    _end_cursor_drag(session)
    session.activate_previous()
    render_active_graph(plotter, session, pv_module=pv_module)


def switch_next_graph(plotter: Any, session: GraphViewerSession, *, pv_module: Any | None = None) -> None:
    _clear_cursor_edit(session)
    _end_cursor_drag(session)
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


def handle_dropped_visualization_paths(
    plotter: Any,
    session: GraphViewerSession,
    paths: Sequence[str | Path],
    *,
    pv_module: Any | None = None,
) -> list[LoadedVisualizationFile]:
    """Load supported visualization files from a drop event, ignoring other paths."""
    return load_visualization_paths(plotter, session, paths, pv_module=pv_module, interactive=True)


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
            handle_dropped_visualization_paths(plotter, session, paths, pv_module=pv_module)

    if hasattr(interactor, "add_observer"):
        interactor.add_observer("DropFilesEvent", _on_drop)
        return True
    if hasattr(interactor, "AddObserver"):
        interactor.AddObserver("DropFilesEvent", _on_drop)
        return True
    return False


def _all_hitboxes(session: GraphViewerSession) -> list[UIHitbox]:
    return session.file_hitboxes + session.tools_hitboxes + session.command_hitboxes


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


def _inside_tools_panel(plotter: Any, session: GraphViewerSession, x_pos: int, y_pos: int) -> bool:
    if not session.tools_panel_visible:
        return False
    panel_x, panel_top, panel_bottom = _tools_panel_geometry(plotter)
    return panel_x <= x_pos <= panel_x + TOOLS_PANEL_WIDTH and panel_bottom <= y_pos <= panel_top


def _begin_cursor_drag(plotter: Any, session: GraphViewerSession, x_pos: int, y_pos: int) -> bool:
    if not session.cursor_enabled or session.active_file is None:
        return False
    if _inside_tools_panel(plotter, session, x_pos, y_pos):
        return False
    position = _ensure_cursor_position(session)
    if position is None:
        return False
    display_point = _cursor_display_point(plotter, position)
    if display_point is None:
        return False
    _clear_cursor_edit(session)
    session.cursor_dragging = True
    session.cursor_drag_display_depth = display_point[2]
    return _update_cursor_drag(plotter, session, x_pos, y_pos)


def _update_cursor_drag(plotter: Any, session: GraphViewerSession, x_pos: int, y_pos: int) -> bool:
    if not session.cursor_dragging or session.cursor_drag_display_depth is None:
        return False
    position = _cursor_world_point(plotter, x_pos, y_pos, session.cursor_drag_display_depth)
    if position is None or not _set_cursor_position(session, position):
        return False
    if session.tools_panel_visible:
        render_tools_panel(plotter, session)
    else:
        render_cursor_crosshair(plotter, session)
    if hasattr(plotter, "render"):
        plotter.render()
    return True


def _end_cursor_drag(session: GraphViewerSession) -> None:
    session.cursor_dragging = False
    session.cursor_drag_display_depth = None


def _event_key(caller: Any) -> tuple[str, str]:
    key_sym = str(caller.GetKeySym()) if hasattr(caller, "GetKeySym") else ""
    key_code = str(caller.GetKeyCode()) if hasattr(caller, "GetKeyCode") else ""
    return key_sym, key_code


def _handle_cursor_key_press(plotter: Any, session: GraphViewerSession, caller: Any) -> bool:
    if session.cursor_edit_axis is None:
        return False
    key_sym, key_code = _event_key(caller)
    if key_sym in ("Return", "KP_Enter") or key_code in ("\r", "\n"):
        _commit_cursor_edit(plotter, session)
        return True
    if key_sym == "Escape":
        _clear_cursor_edit(session)
    elif key_sym in ("BackSpace", "Delete"):
        session.cursor_edit_buffer = "" if session.cursor_edit_replace_pending else session.cursor_edit_buffer[:-1]
        session.cursor_edit_invalid = False
        session.cursor_edit_replace_pending = False
    elif key_code in "0123456789.+-eE":
        session.cursor_edit_buffer = key_code if session.cursor_edit_replace_pending else session.cursor_edit_buffer + key_code
        session.cursor_edit_invalid = False
        session.cursor_edit_replace_pending = False
    else:
        return False
    render_tools_panel(plotter, session)
    if hasattr(plotter, "render"):
        plotter.render()
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
            _clear_cursor_edit(session)
            _end_cursor_drag(session)
            session.active_index = hitbox.index
            render_active_graph(plotter, session, pv_module=pv_module)
            return True
        if hitbox.action == "open-file-list":
            session.file_list_open = True
            render_file_panel(plotter, session)
            return True
        if hitbox.action == "toggle-tools":
            session.tools_panel_visible = not session.tools_panel_visible
            if not session.tools_panel_visible:
                _clear_cursor_edit(session)
            render_tools_panel(plotter, session)
            if hasattr(plotter, "render"):
                plotter.render()
            return True
        if hitbox.action == "toggle-cursor":
            toggle_cursor(plotter, session)
            return True
        if hitbox.action.startswith("edit-cursor-"):
            _begin_cursor_edit(plotter, session, hitbox.action[-1])  # type: ignore[arg-type]
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
        if hitbox.action == "node-decrease":
            adjust_graph_preview(plotter, session, option="node", delta=-SLIDER_STEP)
            return True
        if hitbox.action == "node-increase":
            adjust_graph_preview(plotter, session, option="node", delta=SLIDER_STEP)
            return True
        if hitbox.action == "edge-decrease":
            adjust_graph_preview(plotter, session, option="edge", delta=-SLIDER_STEP)
            return True
        if hitbox.action == "edge-increase":
            adjust_graph_preview(plotter, session, option="edge", delta=SLIDER_STEP)
            return True
    return False


def install_ui_mouse_observers(
    plotter: Any,
    session: GraphViewerSession,
    *,
    pv_module: Any | None = None,
) -> bool:
    """Install mouse and resize observers for custom overlay controls."""
    interactor = getattr(plotter, "iren", None)
    if interactor is None:
        return False
    native_interactor = getattr(interactor, "interactor", interactor)
    cancellable_observers: dict[str, int] = {}

    def _set_event_handled(event_name: str, handled: bool) -> None:
        observer_id = cancellable_observers.get(event_name)
        if observer_id is None or not hasattr(native_interactor, "GetCommand"):
            return
        command = native_interactor.GetCommand(observer_id)
        if command is not None and hasattr(command, "SetAbortFlag"):
            command.SetAbortFlag(1 if handled else 0)

    def _on_resize(_caller: Any, _event: str) -> None:
        render_tools_panel(plotter, session)
        if hasattr(plotter, "render"):
            plotter.render()

    def _on_mouse_move(caller: Any, _event: str) -> None:
        _set_event_handled("MouseMoveEvent", False)
        position = _event_position(caller)
        if position is not None:
            if _update_cursor_drag(plotter, session, *position):
                _set_event_handled("MouseMoveEvent", True)
                return
            update_file_list_hover(plotter, session, *position)

    def _on_left_click(caller: Any, _event: str) -> None:
        _set_event_handled("LeftButtonPressEvent", False)
        position = _event_position(caller)
        if position is not None:
            if dispatch_ui_click(plotter, session, *position, pv_module=pv_module):
                _set_event_handled("LeftButtonPressEvent", True)
                return
            if _begin_cursor_drag(plotter, session, *position):
                _set_event_handled("LeftButtonPressEvent", True)

    def _on_left_release(_caller: Any, _event: str) -> None:
        _end_cursor_drag(session)

    def _on_key_press(caller: Any, _event: str) -> None:
        _handle_cursor_key_press(plotter, session, caller)

    def _on_interaction(_caller: Any, _event: str) -> None:
        if session.cursor_enabled and not session.cursor_dragging:
            render_cursor_crosshair(plotter, session)
            if hasattr(plotter, "render"):
                plotter.render()

    def _add_cancellable_observer(event_name: str, callback: Any) -> None:
        try:
            observer_id = native_interactor.AddObserver(event_name, callback, 1.0)
        except TypeError:
            observer_id = native_interactor.AddObserver(event_name, callback)
        if observer_id is not None:
            cancellable_observers[event_name] = int(observer_id)

    if hasattr(interactor, "add_observer"):
        interactor.add_observer("ConfigureEvent", _on_resize)
        if hasattr(native_interactor, "AddObserver") and hasattr(native_interactor, "GetCommand"):
            _add_cancellable_observer("MouseMoveEvent", _on_mouse_move)
            _add_cancellable_observer("LeftButtonPressEvent", _on_left_click)
        else:
            interactor.add_observer("MouseMoveEvent", _on_mouse_move)
            interactor.add_observer("LeftButtonPressEvent", _on_left_click)
        interactor.add_observer("LeftButtonReleaseEvent", _on_left_release)
        interactor.add_observer("KeyPressEvent", _on_key_press)
        interactor.add_observer("InteractionEvent", _on_interaction)
        return True
    if hasattr(interactor, "AddObserver"):
        interactor.AddObserver("ConfigureEvent", _on_resize)
        _add_cancellable_observer("MouseMoveEvent", _on_mouse_move)
        _add_cancellable_observer("LeftButtonPressEvent", _on_left_click)
        interactor.AddObserver("LeftButtonReleaseEvent", _on_left_release)
        interactor.AddObserver("KeyPressEvent", _on_key_press)
        interactor.AddObserver("InteractionEvent", _on_interaction)
        return True
    return False


def _tools_panel_geometry(plotter: Any) -> tuple[int, int, int]:
    """Return panel x, top edge, and bottom edge in display coordinates."""
    window_width, height = _plotter_window_size(plotter)
    panel_x = max(TOOLS_PANEL_RIGHT_MARGIN, window_width - TOOLS_PANEL_RIGHT_MARGIN - TOOLS_PANEL_WIDTH)
    button_y = height - TOOLS_PANEL_TOP_MARGIN - COMMAND_BUTTON_HEIGHT
    panel_top = button_y - TOOLS_PANEL_GAP
    return panel_x, panel_top, panel_top - TOOLS_PANEL_HEIGHT


def _add_ui_button(
    plotter: Any,
    actors: list[Any],
    hitboxes: list[UIHitbox],
    *,
    label: str,
    action: str,
    x: int,
    y: int,
    width: int,
    height: int = COMMAND_BUTTON_HEIGHT,
    background: tuple[float, float, float] = (0.19, 0.26, 0.34),
    font_size: int = 8,
) -> None:
    actors.append(
        _add_overlay_rect(
            plotter,
            x=x,
            y=y,
            width=width,
            height=height,
            color=background,
            opacity=0.92,
        )
    )
    text_width = max(len(label) * 7, 8)
    text_x = x + max((width - text_width) // 2, 2)
    text_y = y + max((height - 14) // 2, 2)
    actors.append(
        _add_overlay_text(
            plotter,
            label,
            x=text_x,
            y=text_y,
            font_size=font_size,
            color="white",
        )
    )
    hitboxes.append(
        UIHitbox(
            name=f"button-{action}",
            x=x,
            y=y,
            width=width,
            height=height,
            action=action,
        )
    )


def render_tools_button(plotter: Any, session: GraphViewerSession) -> None:
    """Draw the always-visible top-right Tools panel toggle."""
    _remove_actor_list(plotter, session.tools_button_actors)
    session.tools_hitboxes.clear()
    window_width, height = _plotter_window_size(plotter)
    x_pos = max(TOOLS_PANEL_RIGHT_MARGIN, window_width - TOOLS_PANEL_RIGHT_MARGIN - TOOLS_BUTTON_WIDTH)
    y_pos = height - TOOLS_PANEL_TOP_MARGIN - COMMAND_BUTTON_HEIGHT
    _add_ui_button(
        plotter,
        session.tools_button_actors,
        session.tools_hitboxes,
        label="Tools",
        action="toggle-tools",
        x=x_pos,
        y=y_pos,
        width=TOOLS_BUTTON_WIDTH,
        background=(0.12, 0.16, 0.21) if not session.tools_panel_visible else (0.24, 0.34, 0.43),
    )


def render_cursor_controls(plotter: Any, session: GraphViewerSession) -> None:
    """Draw the cursor toggle and numeric coordinate input rows."""
    if not session.tools_panel_visible:
        return
    panel_x, panel_top, _panel_bottom = _tools_panel_geometry(plotter)
    inner_x = panel_x + TOOLS_PANEL_PADDING
    inner_width = TOOLS_PANEL_WIDTH - 2 * TOOLS_PANEL_PADDING
    button_y = panel_top - TOOLS_PANEL_PADDING - COMMAND_BUTTON_HEIGHT
    has_active_file = session.active_file is not None
    active = session.cursor_enabled and has_active_file
    cursor_button_background = (0.10, 0.45, 0.31) if active else (
        (0.19, 0.26, 0.34) if has_active_file else (0.29, 0.31, 0.34)
    )
    _add_ui_button(
        plotter,
        session.command_button_actors,
        session.command_hitboxes,
        label="Enable Cursor",
        action="toggle-cursor",
        x=inner_x,
        y=button_y,
        width=inner_width,
        background=cursor_button_background,
    )

    position = session.active_file.cursor_position if session.active_file is not None else None
    field_x = inner_x + CURSOR_FIELD_LABEL_WIDTH
    field_width = inner_width - CURSOR_FIELD_LABEL_WIDTH
    for row_index, axis in enumerate(("x", "y", "z")):
        y_pos = button_y - (row_index + 1) * (COMMAND_BUTTON_HEIGHT + COMMAND_BUTTON_GAP)
        session.command_button_actors.append(
            _add_overlay_text(plotter, f"{axis.upper()}:", x=inner_x, y=y_pos + 6, font_size=9, color="#d7dde5")
        )
        focused = session.cursor_edit_axis == axis
        background = (0.42, 0.10, 0.12) if focused and session.cursor_edit_invalid else (
            (0.24, 0.34, 0.43) if focused else (0.15, 0.20, 0.26)
        )
        session.command_button_actors.append(
            _add_overlay_rect(
                plotter,
                x=field_x,
                y=y_pos,
                width=field_width,
                height=COMMAND_BUTTON_HEIGHT,
                color=background,
                opacity=0.94,
            )
        )
        if focused:
            value_text = session.cursor_edit_buffer
        elif position is not None:
            value_text = _format_cursor_coordinate(position[row_index])
        else:
            value_text = "--"
        session.command_button_actors.append(
            _add_overlay_text(plotter, value_text, x=field_x + 8, y=y_pos + 6, font_size=9, color="white")
        )
        session.command_hitboxes.append(
            UIHitbox(
                name=f"cursor-{axis}",
                x=field_x,
                y=y_pos,
                width=field_width,
                height=COMMAND_BUTTON_HEIGHT,
                action=f"edit-cursor-{axis}",
            )
        )


def render_command_buttons(plotter: Any, session: GraphViewerSession) -> None:
    """Draw command controls as three rows in the visible Tools panel."""
    _remove_actor_list(plotter, session.command_button_actors)
    session.command_hitboxes.clear()
    if not session.tools_panel_visible:
        return

    panel_x, panel_top, _panel_bottom = _tools_panel_geometry(plotter)
    button_width = (TOOLS_PANEL_WIDTH - 2 * TOOLS_PANEL_PADDING - COMMAND_BUTTON_GAP) // 2
    rows = (
        (("Import", "import", (0.19, 0.26, 0.34)), ("Close", "close", (0.20, 0.24, 0.30))),
        (("< (Prev)", "previous", (0.15, 0.22, 0.31)), ("> (Next)", "next", (0.15, 0.22, 0.31))),
        (("Refresh", "refresh", (0.70, 0.08, 0.09)), ("Reset View", "reset-view", (0.05, 0.28, 0.68))),
    )
    for row_index, row in enumerate(rows):
        y_pos = panel_top - TOOLS_PANEL_PADDING - COMMAND_BUTTON_HEIGHT - CURSOR_ROWS_HEIGHT - row_index * (
            COMMAND_BUTTON_HEIGHT + COMMAND_BUTTON_GAP
        )
        for column, (label, action, background) in enumerate(row):
            x_pos = panel_x + TOOLS_PANEL_PADDING + column * (button_width + COMMAND_BUTTON_GAP)
            _add_ui_button(
                plotter,
                session.command_button_actors,
                session.command_hitboxes,
                label=label,
                action=action,
                x=x_pos,
                y=y_pos,
                width=button_width,
                background=background,
            )


def _render_slider_step_buttons(plotter: Any, session: GraphViewerSession) -> None:
    """Draw minus/plus controls surrounding GraphML appearance sliders."""
    if not session.tools_panel_visible or session.active_kind == "nifti":
        return
    panel_x, panel_top, _panel_bottom = _tools_panel_geometry(plotter)
    slider_rows = (
        ("node-decrease", "node-increase", panel_top - CURSOR_ROWS_HEIGHT - 167),
        ("edge-decrease", "edge-increase", panel_top - CURSOR_ROWS_HEIGHT - 229),
    )
    for decrease_action, increase_action, centre_y in slider_rows:
        button_y = centre_y - SLIDER_STEP_BUTTON_SIZE // 2
        for label, action, x_pos in (
            ("-", decrease_action, panel_x + TOOLS_PANEL_PADDING),
            ("+", increase_action, panel_x + TOOLS_PANEL_WIDTH - TOOLS_PANEL_PADDING - SLIDER_STEP_BUTTON_SIZE),
        ):
            _add_ui_button(
                plotter,
                session.command_button_actors,
                session.command_hitboxes,
                label=label,
                action=action,
                x=x_pos,
                y=button_y,
                width=SLIDER_STEP_BUTTON_SIZE,
                height=SLIDER_STEP_BUTTON_SIZE,
                background=(0.15, 0.22, 0.31),
                font_size=11,
            )


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


def _remove_graph_sliders(plotter: Any, session: GraphViewerSession) -> None:
    if not session.slider_widgets:
        session.sliders_visible = False
        return
    if hasattr(plotter, "clear_slider_widgets"):
        plotter.clear_slider_widgets()
    else:
        for widget in session.slider_widgets:
            for method_name in ("Off", "SetEnabled"):
                if hasattr(widget, method_name):
                    method = getattr(widget, method_name)
                    try:
                        method(0) if method_name == "SetEnabled" else method()
                    except TypeError:
                        method()
                    break
    session.slider_widgets.clear()
    session.sliders_visible = False


def render_graph_sliders(plotter: Any, session: GraphViewerSession) -> None:
    """Show GraphML appearance sliders only while the Tools panel is visible."""
    should_show = session.tools_panel_visible and session.active_kind != "nifti"
    if not should_show:
        _remove_graph_sliders(plotter, session)
        return
    if session.sliders_visible:
        return

    panel_x, panel_top, _panel_bottom = _tools_panel_geometry(plotter)
    width, height = _plotter_window_size(plotter)
    slider_left = (panel_x + TOOLS_PANEL_PADDING + SLIDER_STEP_BUTTON_SIZE + 10) / width
    slider_right = (panel_x + TOOLS_PANEL_WIDTH - TOOLS_PANEL_PADDING - SLIDER_STEP_BUTTON_SIZE - 10) / width
    node_y = (panel_top - CURSOR_ROWS_HEIGHT - 167) / height
    edge_y = (panel_top - CURSOR_ROWS_HEIGHT - 229) / height

    node_slider = plotter.add_slider_widget(
        lambda value: session.set_preview_node_size(value),
        NODE_SIZE_RANGE,
        value=session.preview_node_size,
        title="Node Size",
        pointa=(slider_left, node_y),
        pointb=(slider_right, node_y),
        color=SLIDER_COLOR,
        title_color="#d7dde5",
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
        title="Edge Thickness",
        pointa=(slider_left, edge_y),
        pointb=(slider_right, edge_y),
        color=SLIDER_COLOR,
        title_color="#d7dde5",
        style="modern",
        title_height=0.018,
        fmt="%.2g",
        slider_width=0.018,
        tube_width=0.010,
        interaction_event="always",
    )
    _style_slider_widget(edge_slider)
    session.slider_widgets = [node_slider, edge_slider]
    session.sliders_visible = True


def _clamp_preview_step(value: float, delta: float, bounds: tuple[float, float]) -> float:
    return float(round(min(max(value + delta, bounds[0]), bounds[1]), 10))


def adjust_graph_preview(
    plotter: Any,
    session: GraphViewerSession,
    *,
    option: Literal["node", "edge"],
    delta: float,
) -> None:
    """Adjust one pending appearance value without refreshing graph geometry."""
    if option == "node":
        next_value = _clamp_preview_step(float(session.preview_node_size), delta, NODE_SIZE_RANGE)
        session.set_preview_node_size(next_value)
    else:
        next_value = _clamp_preview_step(float(session.preview_edge_thickness), delta, EDGE_THICKNESS_RANGE)
        session.set_preview_edge_thickness(next_value)
    _remove_graph_sliders(plotter, session)
    render_graph_sliders(plotter, session)
    if hasattr(plotter, "render"):
        plotter.render()


def render_tools_panel(plotter: Any, session: GraphViewerSession) -> None:
    """Render or hide the right-side tool panel and its current controls."""
    if session.cursor_enabled:
        _ensure_cursor_position(session)
    _remove_actor_list(plotter, session.tools_panel_actors)
    render_tools_button(plotter, session)
    if not session.tools_panel_visible:
        _clear_cursor_edit(session)
        render_command_buttons(plotter, session)
        _remove_graph_sliders(plotter, session)
        render_cursor_crosshair(plotter, session)
        return

    panel_x, panel_top, panel_bottom = _tools_panel_geometry(plotter)
    session.tools_panel_actors.append(
        _add_overlay_rect(
            plotter,
            x=panel_x,
            y=panel_bottom,
            width=TOOLS_PANEL_WIDTH,
            height=TOOLS_PANEL_HEIGHT,
            color=(0.12, 0.16, 0.21),
            opacity=0.90,
        )
    )
    render_command_buttons(plotter, session)
    render_cursor_controls(plotter, session)
    _render_slider_step_buttons(plotter, session)
    _remove_graph_sliders(plotter, session)
    render_graph_sliders(plotter, session)
    render_cursor_crosshair(plotter, session)


def add_graph_viewer_controls(plotter: Any, session: GraphViewerSession, *, pv_module: Any | None = None) -> None:
    """Add pure-PyVista controls for file/session management and appearance preview."""
    render_file_panel(plotter, session)
    render_tools_panel(plotter, session)
    install_ui_mouse_observers(plotter, session, pv_module=pv_module)


def _show_interactive_plotter(plotter: Any, session: GraphViewerSession) -> None:
    """Map the desktop window before placing right-aligned overlay controls."""
    plotter.show(interactive_update=True, auto_close=False)
    interactor = getattr(plotter, "iren", None)
    if interactor is not None and hasattr(interactor, "process_events"):
        interactor.process_events()
    render_tools_panel(plotter, session)
    if hasattr(plotter, "render"):
        plotter.render()
    plotter.show()


def launch_graph_viewer(
    input_path: str | Path | None = None,
    *,
    edge_thickness: float = 1.0,
    node_size: float = 2.5,
) -> int:
    """Launch an interactive PyVista window for an optional GraphML or NIfTI file."""
    pv = _import_pyvista()
    session = create_graph_viewer_session(input_path, edge_thickness=edge_thickness, node_size=node_size)
    plotter = build_graph_plotter(None, session.options, pv_module=pv)
    render_active_graph(plotter, session, pv_module=pv)
    add_graph_viewer_controls(plotter, session, pv_module=pv)
    install_drop_observer(plotter, session, pv_module=pv)
    _show_interactive_plotter(plotter, session)
    return 0
