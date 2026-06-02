"""PyVista-based viewer for 3D vessel graphs and binary NIfTI volumes."""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib
from pathlib import Path
from typing import Any, Literal, Sequence
import warnings

import igraph as ig
import nibabel as nib
import numpy as np


VisualizationFileKind = Literal["graphml", "nifti"]
ViewLayoutMode = Literal["single", "double"]
ViewID = Literal["a", "b"]
NODE_SIZE_RANGE = (0.5, 40.0)
EDGE_THICKNESS_RANGE = (0.1, 10.0)
LARGE_NIFTI_VOXEL_WARNING_THRESHOLD = 250_000
FILE_PANEL_X = 10
FILE_PANEL_TOP_MARGIN = 12
FILE_PANEL_WIDTH = 300
FILE_PANEL_ROW_HEIGHT = 22
TOOLS_PANEL_RIGHT_MARGIN = 0
TOOLS_PANEL_TOP_MARGIN = 12
TOOLS_PANEL_WIDTH = 336  # kept for backward reference; runtime width is 25 % of window
TOOLS_PANEL_HEIGHT = 560
TOOLS_PANEL_MIN_HEIGHT = 220
TOOLS_PANEL_BOTTOM_MARGIN = 12
TOOLS_PANEL_CONTENT_HEIGHT = 830
TOOLS_SCROLLBAR_WIDTH = 10
TOOLS_SCROLLBAR_GUTTER = 30
TOOLS_SCROLL_STEP = 42
TOOLS_VIEWPORT_CLIP_PADDING = 2
TOOLS_PANEL_GAP = 0
TOOLS_PANEL_PADDING = 14
TOOLS_SECTION_HEADER_HEIGHT = 14
TOOLS_SECTION_HEADER_GAP = 4
TOOLS_SECTION_GAP = 10
TOOLS_HEADER_FONT_SIZE = 11
TOOLS_TEXT_FONT_SIZE = 11
TOOLS_BUTTON_FONT_SIZE = 10
TOOLS_MENU_FONT_SIZE = 10
VIEW_LAYOUT_MENU_ROW_HEIGHT = 22
VIEW_LAYOUT_MENU_MAX_ROWS = 6
HEADER_HEIGHT_FRACTION = 0.05
HEADER_COLOR = (0.733, 0.765, 0.780)  # #BBC3C7
HEADER_BORDER_COLOR = (0.949, 0.949, 0.306)  # #F2F24E
HEADER_BORDER_WIDTH = 2
HEADER_FONT_SIZE = 11
APPEARANCE_SLIDER_TOP_GAP = 42
APPEARANCE_SLIDER_SPACING = 84
APPEARANCE_SLIDER_RESERVED_HEIGHT = 76
APPEARANCE_SLIDER_BOTTOM_GAP = 60
COMMAND_BUTTON_GAP = 10
COMMAND_BUTTON_HEIGHT = 30
INTERACTIVE_PICK_RADIUS = 12
INTERACTIVE_SELECTED_COLOR = "#03FFD9"
SLIDER_COLOR = "#9ea4aa"
CAMERA_ZOOM_FRACTION = 0.12
CAMERA_MIN_DISTANCE_FRACTION = 0.02
CAMERA_MIN_DISTANCE = 1e-6
CAMERA_ORBIT_RADIANS_PER_PIXEL = 0.005
FIT_PREVIEW_MARGIN = 1.18
DEFAULT_CAMERA_VIEW_ANGLE = 30.0
AXES_MARKER_VIEWPORT = (0.02, 0.02, 0.20, 0.20)
AXES_MARKER_HIDDEN_VIEWPORT = (0.0, 0.0, 0.0001, 0.0001)


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
    node_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class GraphVisualizationOptions:
    """User-configurable graph appearance."""

    edge_thickness: float = 1.0
    node_size: float = 2.5
    window_title: str = "SkelHub Graph Viewer"


@dataclass(slots=True)
class NiftiVisualizationData:
    """Binary NIfTI foreground voxels prepared for physical-space rendering."""

    voxel_positions: np.ndarray
    voxel_count: int
    shape: tuple[int, int, int]
    source_path: str
    display_positions: np.ndarray | None = None
    affine: np.ndarray = field(default_factory=lambda: np.eye(4, dtype=float))
    spatial_unit: str = "unknown"


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
    view_angle: float | None = None
    parallel_projection: bool | None = None


@dataclass(slots=True)
class LoadedVisualizationFile:
    """A visualization file loaded into one viewer session."""

    path: Path
    kind: VisualizationFileKind
    data: GraphVisualizationData | NiftiVisualizationData
    initial_camera_state: CameraState | None = None


LoadedGraphFile = LoadedVisualizationFile


@dataclass(slots=True)
class ViewState:
    """Mutable state for one scene viewport."""

    view_id: ViewID
    file_index: int | None = None
    options: GraphVisualizationOptions = field(default_factory=GraphVisualizationOptions)
    preview_node_size: float | None = None
    preview_edge_thickness: float | None = None
    graph_actors: list[Any] = field(default_factory=list)
    graph_node_actor: Any | None = None
    graph_edge_actor: Any | None = None
    selected_node_actors: list[Any] = field(default_factory=list)
    interactive_enabled: bool = False
    selected_node_index: int | None = None
    camera_orbit_dragging: bool = False
    camera_orbit_last_position: tuple[int, int] | None = None
    file_list_open: bool = False
    camera_state: CameraState | None = None

    def __post_init__(self) -> None:
        _validate_options(self.options)
        if self.preview_node_size is None:
            self.preview_node_size = self.options.node_size
        if self.preview_edge_thickness is None:
            self.preview_edge_thickness = self.options.edge_thickness

    def set_preview_node_size(self, value: float) -> None:
        self.preview_node_size = float(value)

    def set_preview_edge_thickness(self, value: float) -> None:
        self.preview_edge_thickness = float(value)

    def apply_preview_options(self) -> None:
        self.options.node_size = float(self.preview_node_size)
        self.options.edge_thickness = float(self.preview_edge_thickness)
        _validate_options(self.options)


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
    view_id: ViewID | None = None
    value: str | None = None

    def contains(self, x_pos: int, y_pos: int) -> bool:
        return self.x <= x_pos <= self.x + self.width and self.y <= y_pos <= self.y + self.height


@dataclass(slots=True)
class GraphViewerSession:
    """Mutable state for an interactive graph viewer session."""

    options: GraphVisualizationOptions = field(default_factory=GraphVisualizationOptions)
    loaded_files: list[LoadedVisualizationFile] = field(default_factory=list)
    layout_mode: ViewLayoutMode = "single"
    active_view_id: ViewID = "a"
    views: dict[ViewID, ViewState] = field(default_factory=dict)
    file_panel_actors: list[Any] = field(default_factory=list)
    tools_panel_actors: list[Any] = field(default_factory=list)
    command_button_actors: list[Any] = field(default_factory=list)
    header_actors: list[Any] = field(default_factory=list)
    slider_widgets: list[Any] = field(default_factory=list)
    file_hitboxes: list[UIHitbox] = field(default_factory=list)
    tools_hitboxes: list[UIHitbox] = field(default_factory=list)
    command_hitboxes: list[UIHitbox] = field(default_factory=list)
    sliders_visible: bool = False
    tools_panel_visible: bool = True
    tools_scroll_offset: float = 0.0
    tools_scroll_dragging: bool = False
    tools_scroll_drag_last_y: int | None = None
    appearance_slider_dragging: Literal["node", "edge"] | None = None
    node_id_editing: bool = False
    node_id_edit_buffer: str = ""
    node_id_edit_invalid: bool = False
    node_id_edit_replace_pending: bool = False
    camera_sync_enabled: bool = True
    shared_camera_state: CameraState | None = None
    error_actor: Any | None = None
    layout_menu_open: bool = False
    view_menu_open: ViewID | None = None
    overlay_renderer: Any | None = None

    def __post_init__(self) -> None:
        _validate_options(self.options)
        if not self.views:
            self.views = {
                "a": ViewState("a", options=GraphVisualizationOptions(
                    edge_thickness=self.options.edge_thickness,
                    node_size=self.options.node_size,
                    window_title=self.options.window_title,
                )),
                "b": ViewState("b", options=GraphVisualizationOptions(
                    edge_thickness=self.options.edge_thickness,
                    node_size=self.options.node_size,
                    window_title=self.options.window_title,
                )),
            }

    @property
    def active_view(self) -> ViewState:
        return self.views[self.active_view_id]

    def view_state(self, view_id: ViewID | None = None) -> ViewState:
        return self.views[view_id or self.active_view_id]

    @property
    def active_index(self) -> int | None:
        return self.active_view.file_index

    @active_index.setter
    def active_index(self, value: int | None) -> None:
        self.active_view.file_index = value

    @property
    def preview_node_size(self) -> float | None:
        return self.active_view.preview_node_size

    @preview_node_size.setter
    def preview_node_size(self, value: float | None) -> None:
        self.active_view.preview_node_size = value

    @property
    def preview_edge_thickness(self) -> float | None:
        return self.active_view.preview_edge_thickness

    @preview_edge_thickness.setter
    def preview_edge_thickness(self, value: float | None) -> None:
        self.active_view.preview_edge_thickness = value

    @property
    def interactive_enabled(self) -> bool:
        return self.active_view.interactive_enabled

    @interactive_enabled.setter
    def interactive_enabled(self, value: bool) -> None:
        self.active_view.interactive_enabled = bool(value)

    @property
    def selected_node_index(self) -> int | None:
        return self.active_view.selected_node_index

    @selected_node_index.setter
    def selected_node_index(self, value: int | None) -> None:
        self.active_view.selected_node_index = value

    @property
    def file_list_open(self) -> bool:
        return self.active_view.file_list_open

    @file_list_open.setter
    def file_list_open(self, value: bool) -> None:
        self.active_view.file_list_open = bool(value)

    @property
    def camera_orbit_dragging(self) -> bool:
        return self.active_view.camera_orbit_dragging

    @camera_orbit_dragging.setter
    def camera_orbit_dragging(self, value: bool) -> None:
        self.active_view.camera_orbit_dragging = bool(value)

    @property
    def camera_orbit_last_position(self) -> tuple[int, int] | None:
        return self.active_view.camera_orbit_last_position

    @camera_orbit_last_position.setter
    def camera_orbit_last_position(self, value: tuple[int, int] | None) -> None:
        self.active_view.camera_orbit_last_position = value

    @property
    def active_file(self) -> LoadedVisualizationFile | None:
        return self.file_for_view(self.active_view_id)

    def file_for_view(self, view_id: ViewID | None = None) -> LoadedVisualizationFile | None:
        view = self.view_state(view_id)
        if view.file_index is None:
            return None
        if view.file_index < 0 or view.file_index >= len(self.loaded_files):
            return None
        return self.loaded_files[view.file_index]

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
                self.assign_view_file(self.active_view_id, index)
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
        self.assign_view_file(self.active_view_id, len(self.loaded_files) - 1)
        return loaded_file

    def assign_view_file(self, view_id: ViewID, index: int | None) -> None:
        view = self.view_state(view_id)
        view.file_index = index if index is None or 0 <= index < len(self.loaded_files) else None

    def close_active_file(self) -> None:
        active_index = self.active_index
        if active_index is None:
            return

        del self.loaded_files[active_index]
        for view in self.views.values():
            if view.file_index is None:
                continue
            if view.file_index == active_index:
                view.file_index = None
            elif view.file_index > active_index:
                view.file_index -= 1
        if not self.loaded_files:
            return
        if self.active_index is None:
            self.active_index = min(active_index, len(self.loaded_files) - 1)

    def clear_active_view_file(self) -> None:
        self.active_view.file_index = None

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
        self.active_view.set_preview_node_size(value)

    def set_preview_edge_thickness(self, value: float) -> None:
        self.active_view.set_preview_edge_thickness(value)

    def apply_preview_options(self) -> None:
        self.active_view.apply_preview_options()

    def status_text(self, view_id: ViewID | None = None) -> str:
        view = self.view_state(view_id)
        active = self.file_for_view(view.view_id)
        if active is None:
            return "No file loaded"
        kind_label = _kind_label(active.kind)
        active_index = view.file_index
        index_text = "?" if active_index is None else str(active_index + 1)
        return f"{index_text}/{len(self.loaded_files)}  {kind_label}  {active.path.name}"

    def compact_status_text(self, *, max_length: int = 34, view_id: ViewID | None = None) -> str:
        text = self.status_text(view_id)
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


def _extract_node_ids(graph: ig.Graph) -> tuple[str, ...]:
    if "id" in graph.vs.attribute_names():
        return tuple(str(value) for value in graph.vs["id"])
    if "name" in graph.vs.attribute_names():
        return tuple(str(value) for value in graph.vs["name"])
    return tuple(str(index) for index in range(graph.vcount()))


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
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Could not add vertex ids, there is already an 'id' vertex attribute",
                category=RuntimeWarning,
            )
            graph = ig.Graph.Read_GraphML(str(graph_path))
    except Exception as exc:  # pragma: no cover - igraph raises several concrete types
        raise GraphVisualizationError(f"Failed to load GraphML file '{graph_path}': {exc}") from exc

    node_positions = _extract_node_positions(graph)
    node_ids = _extract_node_ids(graph)
    edge_indices = _extract_edge_indices(graph)
    _validate_graph_data(node_positions, edge_indices)
    return GraphVisualizationData(
        node_positions=node_positions,
        edge_indices=edge_indices,
        node_count=graph.vcount(),
        edge_count=graph.ecount(),
        source_path=str(graph_path),
        node_ids=node_ids,
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


def _transform_points(points: np.ndarray, affine: np.ndarray) -> np.ndarray:
    """Transform an array of voxel-space points through a NIfTI affine."""
    points = np.asarray(points, dtype=float)
    if points.size == 0:
        return np.empty((0, 3), dtype=float)
    homogeneous = np.column_stack((points, np.ones(points.shape[0], dtype=float)))
    return (np.asarray(affine, dtype=float) @ homogeneous.T).T[:, :3]


def load_nifti_visualization_data(input_path: str | Path) -> NiftiVisualizationData:
    """Load a binary NIfTI volume with voxel and world-space display positions."""
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
    affine = np.asarray(image.affine, dtype=float)
    spatial_unit, _time_unit = image.header.get_xyzt_units()
    return NiftiVisualizationData(
        voxel_positions=voxel_positions,
        voxel_count=int(voxel_positions.shape[0]),
        shape=tuple(int(size) for size in data.shape),
        source_path=str(nifti_path),
        display_positions=_transform_points(voxel_positions, affine),
        affine=affine,
        spatial_unit=spatial_unit or "unknown",
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


def _add_graph_scene(
    plotter: Any,
    graph_data: GraphVisualizationData,
    options: GraphVisualizationOptions,
    *,
    pv_module: Any | None = None,
) -> tuple[list[Any], Any | None, Any]:
    """Add simplified point/line actors for GraphML files."""
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


def build_nifti_meshes(
    nifti_data: NiftiVisualizationData,
    *,
    pv_module: Any | None = None,
) -> NiftiVisualizationMeshes:
    """Build a physical-space PyVista block mesh from binary NIfTI voxels."""
    pv = _import_pyvista() if pv_module is None else pv_module
    if nifti_data.voxel_count == 0:
        return NiftiVisualizationMeshes(blocks=None)

    voxel_cloud = pv.PolyData(_nifti_display_positions(nifti_data))
    cube = _nifti_voxel_geometry(nifti_data, pv)
    block_mesh = voxel_cloud.glyph(geom=cube, orient=False, scale=False)
    return NiftiVisualizationMeshes(blocks=block_mesh)


def _nifti_display_positions(nifti_data: NiftiVisualizationData) -> np.ndarray:
    if nifti_data.display_positions is not None:
        return nifti_data.display_positions
    return _transform_points(nifti_data.voxel_positions, nifti_data.affine)


def _nifti_voxel_geometry(nifti_data: NiftiVisualizationData, pv: Any) -> Any:
    """Build one voxel block transformed by the affine linear component."""
    cube = pv.Cube(x_length=1.0, y_length=1.0, z_length=1.0)
    linear_transform = np.eye(4, dtype=float)
    linear_transform[:3, :3] = np.asarray(nifti_data.affine, dtype=float)[:3, :3]
    return cube.transform(linear_transform, inplace=False)


def _build_instanced_nifti_actor(
    nifti_data: NiftiVisualizationData,
    *,
    pv_module: Any | None = None,
) -> Any | None:
    """Build one physical-space voxel source instanced at foreground positions."""
    if nifti_data.voxel_count == 0:
        return None
    pv = _import_pyvista() if pv_module is None else pv_module

    try:
        from vtkmodules.vtkRenderingCore import vtkActor, vtkGlyph3DMapper
    except ImportError as exc:  # pragma: no cover - PyVista installations include VTK
        raise GraphVisualizationError("VTK NIfTI block rendering could not be initialized.") from exc

    voxel_cloud = pv.PolyData(_nifti_display_positions(nifti_data))
    cube = _nifti_voxel_geometry(nifti_data, pv)
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
    plotter = pv.Plotter(title=options.window_title, off_screen=off_screen, shape=(1, 2))
    plotter.set_background("white")
    for column in (0, 1):
        plotter.subplot(0, column)
        plotter.add_axes(line_width=3, viewport=AXES_MARKER_VIEWPORT)

    if graph_data is not None:
        plotter.subplot(0, 0)
        _add_graph_scene(plotter, graph_data, options, pv_module=pv)
        plotter.reset_camera()

    return plotter


def _scene_column(view_id: ViewID) -> int:
    return 0 if view_id == "a" else 1


def _select_view_renderer(plotter: Any, view_id: ViewID) -> None:
    if hasattr(plotter, "subplot"):
        plotter.subplot(0, _scene_column(view_id))


def _scene_renderer(plotter: Any, view_id: ViewID) -> Any | None:
    renderers = getattr(plotter, "renderers", None)
    if renderers is not None:
        try:
            return renderers[_scene_column(view_id)]
        except Exception:
            return None
    _select_view_renderer(plotter, view_id)
    return getattr(plotter, "renderer", None)


def _axes_marker_viewport(*, scale_x: float = 1.0) -> tuple[float, float, float, float]:
    """Return the renderer-relative viewport for the orientation axes marker.

    VTK's orientation marker widget interprets the viewport relative to the
    parent renderer, not the full window.  When *scale_x* is > 1.0 (e.g. in
    double-view mode where each renderer occupies half the scene width) the
    widget width is scaled up so it keeps the same physical pixel size as in
    single-view mode.
    """
    x_min, y_min, x_max, y_max = AXES_MARKER_VIEWPORT
    effective_x_max = x_min + (x_max - x_min) * float(scale_x)
    return (x_min, y_min, effective_x_max, y_max)


def _set_axes_marker_visible(
    renderer: Any | None,
    *,
    visible: bool,
    viewport: tuple[float, float, float, float],
) -> None:
    if renderer is None:
        return
    axes_widget = getattr(renderer, "axes_widget", None)
    if axes_widget is None:
        return

    next_viewport = viewport if visible else AXES_MARKER_HIDDEN_VIEWPORT
    if hasattr(axes_widget, "SetViewport"):
        axes_widget.SetViewport(next_viewport)

    if visible:
        if hasattr(axes_widget, "EnabledOn"):
            axes_widget.EnabledOn()
        elif hasattr(axes_widget, "SetEnabled"):
            axes_widget.SetEnabled(1)
    else:
        is_enabled = True
        if hasattr(axes_widget, "GetEnabled"):
            try:
                is_enabled = bool(axes_widget.GetEnabled())
            except Exception:
                is_enabled = True
        if is_enabled and hasattr(axes_widget, "EnabledOff"):
            axes_widget.EnabledOff()
        elif hasattr(axes_widget, "SetEnabled"):
            axes_widget.SetEnabled(0)

    if hasattr(renderer, "Modified"):
        renderer.Modified()


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


def _tools_panel_width(plotter: Any) -> int:
    """Return the tools panel width as 25 % of the window width."""
    window_width, _height = _plotter_window_size(plotter)
    return int(window_width * 0.25)


def _scene_area_fraction(plotter: Any) -> float:
    """Return the right edge of the scene area as a fraction of the window.

    The scene occupies 75 % of the window; the remaining 25 % is the tools panel.
    """
    return 0.75


def apply_view_layout(plotter: Any, session: GraphViewerSession) -> None:
    """Apply scene renderer viewports for the current single/double layout."""
    scene_right = _scene_area_fraction(plotter)
    renderer_a = _scene_renderer(plotter, "a")
    renderer_b = _scene_renderer(plotter, "b")
    if session.layout_mode == "double":
        header_bottom = 1.0 - HEADER_HEIGHT_FRACTION
        if renderer_a is not None and hasattr(renderer_a, "SetViewport"):
            renderer_a.SetViewport(0.0, 0.0, scene_right / 2.0, header_bottom)
        if renderer_b is not None and hasattr(renderer_b, "SetViewport"):
            renderer_b.SetViewport(scene_right / 2.0, 0.0, scene_right, header_bottom)
        axes_viewport = _axes_marker_viewport(scale_x=2.0)
        _set_axes_marker_visible(renderer_a, visible=True, viewport=axes_viewport)
        _set_axes_marker_visible(renderer_b, visible=True, viewport=axes_viewport)
    else:
        if renderer_a is not None and hasattr(renderer_a, "SetViewport"):
            renderer_a.SetViewport(0.0, 0.0, scene_right, 1.0)
        if renderer_b is not None and hasattr(renderer_b, "SetViewport"):
            renderer_b.SetViewport(0.0, 0.0, 0.0, 0.0)
        _set_axes_marker_visible(renderer_a, visible=True, viewport=_axes_marker_viewport())
        _set_axes_marker_visible(renderer_b, visible=False, viewport=AXES_MARKER_HIDDEN_VIEWPORT)


def render_view_headers(plotter: Any, session: GraphViewerSession) -> None:
    """Render compact header bars above each viewport in double-view mode."""
    _remove_actor_list(plotter, session.header_actors)
    if session.layout_mode != "double":
        return

    window_width, window_height = _plotter_window_size(plotter)
    scene_right_px = int(window_width * 0.75)
    header_px = int(window_height * HEADER_HEIGHT_FRACTION)
    half_scene = scene_right_px // 2
    border_w = HEADER_BORDER_WIDTH

    for col, view_id in enumerate(("a", "b")):
        header_x = col * half_scene
        header_y = window_height - header_px
        is_active = session.active_view_id == view_id

        file = session.file_for_view(view_id)
        if file is None:
            text = f"{_view_label(view_id)}  |  No file"
        else:
            kind_label = _kind_label(file.kind)
            name = file.path.name
            prefix = _view_label(view_id) + "  |  " + kind_label + "  "
            available_px = half_scene - 20  # 10 px padding each side
            max_chars = max(10, available_px // 8)  # 8 px conservative char width
            full_text = prefix + name
            if len(full_text) > max_chars:
                name_chars = max(4, max_chars - len(prefix))
                name = name[: name_chars - 3] + "..."
            text = prefix + name

        if is_active:
            # border rect
            session.header_actors.append(
                _add_overlay_rect(
                    plotter,
                    x=header_x,
                    y=header_y,
                    width=half_scene,
                    height=header_px,
                    color=HEADER_BORDER_COLOR,
                    opacity=1.0,
                )
            )
            # inner rect
            session.header_actors.append(
                _add_overlay_rect(
                    plotter,
                    x=header_x + border_w,
                    y=header_y + border_w,
                    width=half_scene - 2 * border_w,
                    height=header_px - 2 * border_w,
                    color=HEADER_COLOR,
                    opacity=1.0,
                )
            )
            text_color = "#1a1a1a"
        else:
            session.header_actors.append(
                _add_overlay_rect(
                    plotter,
                    x=header_x,
                    y=header_y,
                    width=half_scene,
                    height=header_px,
                    color=HEADER_COLOR,
                    opacity=1.0,
                )
            )
            text_color = "#4a4a4a"

        session.header_actors.append(
            _add_overlay_text(
                plotter,
                text,
                x=header_x + 10,
                y=header_y + header_px // 2,
                font_size=HEADER_FONT_SIZE,
                color=text_color,
            )
        )


def _ensure_overlay_renderer(plotter: Any, session: GraphViewerSession) -> Any | None:
    if session.overlay_renderer is not None:
        return session.overlay_renderer
    render_window = getattr(plotter, "render_window", None)
    if render_window is None and hasattr(plotter, "ren_win"):
        render_window = getattr(plotter, "ren_win", None)
    if render_window is None:
        return None
    try:
        from vtkmodules.vtkRenderingCore import vtkRenderer
    except Exception:
        return None
    overlay = vtkRenderer()
    overlay.SetLayer(1)
    overlay.SetViewport(0.0, 0.0, 1.0, 1.0)
    overlay.InteractiveOff()
    try:
        render_window.SetNumberOfLayers(max(2, int(render_window.GetNumberOfLayers())))
    except Exception:
        render_window.SetNumberOfLayers(2)
    render_window.AddRenderer(overlay)
    session.overlay_renderer = overlay
    try:
        setattr(plotter, "_skelhub_overlay_renderer", overlay)
    except Exception:
        pass
    return overlay


def _remove_actor_list(plotter: Any, actors: list[Any]) -> None:
    if not actors or not hasattr(plotter, "remove_actor"):
        actors.clear()
        return
    for actor in actors:
        if actor is None:
            continue
        overlay_renderer = getattr(actor, "_skelhub_overlay_renderer", None)
        if overlay_renderer is not None and hasattr(overlay_renderer, "RemoveActor2D"):
            try:
                overlay_renderer.RemoveActor2D(actor)
                continue
            except Exception:
                pass
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
    overlay_renderer = getattr(plotter, "_skelhub_overlay_renderer", None)
    if overlay_renderer is not None and hasattr(overlay_renderer, "AddActor2D"):
        overlay_renderer.AddActor2D(actor)
        try:
            setattr(actor, "_skelhub_overlay_renderer", overlay_renderer)
        except Exception:
            pass
        return
    renderer = getattr(plotter, "renderer", None)
    if renderer is not None and hasattr(renderer, "AddActor2D"):
        renderer.AddActor2D(actor)
        return
    if hasattr(plotter, "add_actor"):
        try:
            plotter.add_actor(actor, render=False)
        except TypeError:
            plotter.add_actor(actor)


def _overlay_color(color: str) -> tuple[float, float, float]:
    named = {
        "white": (1.0, 1.0, 1.0),
        "black": (0.0, 0.0, 0.0),
    }
    if color in named:
        return named[color]
    if color.startswith("#") and len(color) == 7:
        return tuple(int(color[index : index + 2], 16) / 255.0 for index in (1, 3, 5))  # type: ignore[return-value]
    return (1.0, 1.0, 1.0)


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
        from vtkmodules.vtkRenderingCore import vtkTextActor
    except ImportError:
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

    actor = vtkTextActor()
    actor.SetInput(str(text))
    actor.SetPosition(int(x), int(y))
    text_property = _text_actor_property(actor)
    if text_property is not None:
        text_property.SetFontFamilyToArial()
        text_property.SetFontSize(int(font_size))
        text_property.SetColor(*_overlay_color(color))
        if background_color is not None:
            text_property.SetBackgroundColor(*background_color)
            text_property.SetBackgroundOpacity(background_opacity)
            text_property.SetFrame(True)
            text_property.SetFrameWidth(1)
            text_property.SetFrameColor(*background_color)
    _add_actor2d(plotter, actor)
    return actor


def _add_file_panel_row(
    plotter: Any,
    session: GraphViewerSession,
    *,
    text: str,
    x: int,
    y: int,
    background: tuple[float, float, float],
    color: str = "white",
) -> None:
    session.file_panel_actors.append(
        _add_overlay_rect(
            plotter,
            x=x,
            y=y - 2,
            width=FILE_PANEL_WIDTH,
            height=FILE_PANEL_ROW_HEIGHT + 4,
            color=background,
            opacity=0.96,
        )
    )
    session.file_panel_actors.append(
        _add_overlay_text(
            plotter,
            text,
            x=x + 8,
            y=y,
            font_size=TOOLS_MENU_FONT_SIZE,
            color=color,
        )
    )


def render_file_panel(plotter: Any, session: GraphViewerSession) -> None:
    """Draw compact per-viewport file status controls and optional file lists."""
    _remove_actor_list(plotter, session.file_panel_actors)
    session.file_hitboxes.clear()
    if session.layout_mode == "double":
        for view in session.views.values():
            view.file_list_open = False
        if hasattr(plotter, "render"):
            plotter.render()
        return

    width, height = _plotter_window_size(plotter)
    scene_right = int(round(width * _scene_area_fraction(plotter)))
    label_y = height - FILE_PANEL_TOP_MARGIN - FILE_PANEL_ROW_HEIGHT

    view_ids: tuple[ViewID, ...] = ("a", "b") if session.layout_mode == "double" else ("a",)
    for view_id in view_ids:
        view = session.view_state(view_id)
        panel_x = FILE_PANEL_X if view_id == "a" else scene_right // 2 + FILE_PANEL_X
        view_label = "View A" if view_id == "a" else "View B"
        status = session.compact_status_text(max_length=30, view_id=view_id)
        label_text = f" {view_label}: {status} "
        is_active_view = view_id == session.active_view_id
        _add_file_panel_row(
            plotter,
            session,
            text=label_text,
            x=panel_x,
            y=label_y,
            background=(0.24, 0.34, 0.43) if is_active_view else (0.12, 0.16, 0.21),
        )
        session.file_hitboxes.append(
            UIHitbox(
                name=f"file-panel-{view_id}",
                x=panel_x,
                y=label_y - 2,
                width=FILE_PANEL_WIDTH,
                height=FILE_PANEL_ROW_HEIGHT + 4,
                action="open-file-list",
                view_id=view_id,
            )
        )

        if view.file_list_open:
            rows = session.loaded_files or []
            if not rows:
                _add_file_panel_row(
                    plotter,
                    session,
                    text="No loaded files",
                    x=panel_x,
                    y=label_y - FILE_PANEL_ROW_HEIGHT,
                    background=(0.17, 0.21, 0.27),
                    color="#d7dde5",
                )
            for index, loaded_file in enumerate(rows):
                row_y = label_y - FILE_PANEL_ROW_HEIGHT * (index + 1)
                is_active = index == view.file_index
                prefix = "> " if is_active else "  "
                name = f"{_kind_label(loaded_file.kind)} {loaded_file.path.name}"
                if len(name) > 42:
                    name = name[:39] + "..."
                _add_file_panel_row(
                    plotter,
                    session,
                    text=f"{prefix}{index + 1}. {name}",
                    x=panel_x,
                    y=row_y,
                    background=(0.24, 0.34, 0.43) if is_active else (0.17, 0.21, 0.27),
                    color="white" if is_active else "#d7dde5",
                )
                session.file_hitboxes.append(
                    UIHitbox(
                        name=f"file-{view_id}-{index}",
                        x=panel_x,
                        y=row_y - 2,
                        width=FILE_PANEL_WIDTH,
                        height=FILE_PANEL_ROW_HEIGHT + 4,
                        action="switch-file",
                        index=index,
                        view_id=view_id,
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
        font_size=TOOLS_MENU_FONT_SIZE,
        color="white",
        background_color=(0.55, 0.07, 0.08),
    )


def _box_corners(lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    return np.asarray(
        [
            [x, y, z]
            for x in (lower[0], upper[0])
            for y in (lower[1], upper[1])
            for z in (lower[2], upper[2])
        ],
        dtype=float,
    )


def _scene_bounds(active_file: LoadedVisualizationFile) -> tuple[np.ndarray, np.ndarray]:
    """Return displayed bounds for camera navigation and framing."""
    if active_file.kind == "graphml":
        positions = active_file.data.node_positions  # type: ignore[union-attr]
        return positions.min(axis=0), positions.max(axis=0)

    nifti_data = active_file.data
    if nifti_data.voxel_count:  # type: ignore[union-attr]
        voxel_positions = nifti_data.voxel_positions  # type: ignore[union-attr]
        lower = voxel_positions.min(axis=0) - 0.5
        upper = voxel_positions.max(axis=0) + 0.5
    else:
        lower = np.full(3, -0.5, dtype=float)
        upper = np.asarray(nifti_data.shape, dtype=float) - 0.5  # type: ignore[union-attr]
    world_corners = _transform_points(_box_corners(lower, upper), nifti_data.affine)  # type: ignore[union-attr]
    return world_corners.min(axis=0), world_corners.max(axis=0)


def _clear_node_id_edit(session: GraphViewerSession) -> None:
    session.node_id_editing = False
    session.node_id_edit_buffer = ""
    session.node_id_edit_invalid = False
    session.node_id_edit_replace_pending = False


def _format_coordinate(value: float) -> str:
    return f"{float(value):.6g}"


def _display_point(plotter: Any, position: Sequence[float]) -> tuple[float, float, float] | None:
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


def _selected_graph_data(session: GraphViewerSession, view_id: ViewID | None = None) -> tuple[GraphVisualizationData, int] | None:
    view = session.view_state(view_id)
    active = session.file_for_view(view.view_id)
    graph_data = active.data if active is not None and active.kind == "graphml" else None
    index = view.selected_node_index
    if graph_data is None or index is None or index < 0 or index >= graph_data.node_count:
        return None
    return graph_data, index


def selected_node_position(session: GraphViewerSession) -> tuple[float, float, float] | None:
    selected = _selected_graph_data(session)
    if selected is None:
        return None
    graph_data, index = selected
    return tuple(float(value) for value in graph_data.node_positions[index])


def selected_node_id(session: GraphViewerSession) -> str | None:
    selected = _selected_graph_data(session)
    if selected is None:
        return None
    graph_data, index = selected
    if index < len(graph_data.node_ids):
        return graph_data.node_ids[index]
    return str(index)


def selected_node_degree(session: GraphViewerSession) -> int | None:
    selected = _selected_graph_data(session)
    if selected is None:
        return None
    graph_data, index = selected
    if graph_data.edge_indices.size == 0:
        return 0
    return int(np.count_nonzero(graph_data.edge_indices == index))


def _remove_selected_node_highlight(plotter: Any, session: GraphViewerSession, view_id: ViewID | None = None) -> None:
    _remove_actor_list(plotter, session.view_state(view_id).selected_node_actors)


def render_selected_node_highlight(
    plotter: Any,
    session: GraphViewerSession,
    *,
    pv_module: Any | None = None,
    view_id: ViewID | None = None,
) -> None:
    """Draw the selected GraphML node as a highlight actor."""
    view = session.view_state(view_id)
    _remove_selected_node_highlight(plotter, session, view.view_id)
    if not view.interactive_enabled:
        return
    selected = _selected_graph_data(session)
    if selected is None:
        return
    _select_view_renderer(plotter, view.view_id)
    graph_data, index = selected
    pv = _import_pyvista() if pv_module is None else pv_module
    point = graph_data.node_positions[index]
    mesh = pv.PolyData(np.asarray([point], dtype=float))
    actor = plotter.add_mesh(
        mesh,
        color=INTERACTIVE_SELECTED_COLOR,
        style="points",
        point_size=float(view.options.node_size),
        render_points_as_spheres=True,
        render=False,
    )
    view.selected_node_actors.append(actor)


def clear_interactive_selection(plotter: Any, session: GraphViewerSession, view_id: ViewID | None = None) -> None:
    view = session.view_state(view_id)
    view.selected_node_index = None
    _clear_node_id_edit(session)
    _remove_selected_node_highlight(plotter, session, view.view_id)


def toggle_interactive(plotter: Any, session: GraphViewerSession, *, pv_module: Any | None = None) -> None:
    """Enable or disable GraphML node selection."""
    if session.active_kind != "graphml":
        return
    session.interactive_enabled = not session.interactive_enabled
    session.camera_orbit_dragging = False
    session.camera_orbit_last_position = None
    _clear_node_id_edit(session)
    if not session.interactive_enabled:
        _remove_selected_node_highlight(plotter, session, session.active_view_id)
    else:
        render_selected_node_highlight(plotter, session, pv_module=pv_module, view_id=session.active_view_id)
    render_tools_panel(plotter, session)
    if hasattr(plotter, "render"):
        plotter.render()


def toggle_camera_sync(plotter: Any, session: GraphViewerSession) -> None:
    """Enable or disable shared world-coordinate camera state."""
    session.camera_sync_enabled = not session.camera_sync_enabled
    if session.camera_sync_enabled:
        _store_shared_camera_state(plotter, session)
    else:
        session.shared_camera_state = None
    render_tools_panel(plotter, session)
    if hasattr(plotter, "render"):
        plotter.render()


def _begin_node_id_edit(plotter: Any, session: GraphViewerSession) -> None:
    if session.active_kind != "graphml":
        return
    current_id = selected_node_id(session)
    session.node_id_editing = True
    session.node_id_edit_buffer = "" if current_id is None else current_id
    session.node_id_edit_invalid = False
    session.node_id_edit_replace_pending = True
    render_tools_panel(plotter, session)
    if hasattr(plotter, "render"):
        plotter.render()


def select_graph_node(
    plotter: Any,
    session: GraphViewerSession,
    node_index: int,
    *,
    pv_module: Any | None = None,
) -> bool:
    graph_data = session.active_graph_data
    if graph_data is None or node_index < 0 or node_index >= graph_data.node_count:
        return False
    session.selected_node_index = int(node_index)
    _clear_node_id_edit(session)
    render_selected_node_highlight(plotter, session, pv_module=pv_module, view_id=session.active_view_id)
    render_tools_panel(plotter, session)
    if hasattr(plotter, "render"):
        plotter.render()
    return True


def select_graph_node_by_id(
    plotter: Any,
    session: GraphViewerSession,
    node_id: str,
    *,
    pv_module: Any | None = None,
) -> bool:
    graph_data = session.active_graph_data
    if graph_data is None:
        return False
    node_ids = graph_data.node_ids or tuple(str(index) for index in range(graph_data.node_count))
    try:
        node_index = node_ids.index(str(node_id))
    except ValueError:
        return False
    return select_graph_node(plotter, session, node_index, pv_module=pv_module)


def _commit_node_id_edit(plotter: Any, session: GraphViewerSession, *, pv_module: Any | None = None) -> bool:
    if not session.node_id_editing:
        return False
    node_id = session.node_id_edit_buffer
    if not select_graph_node_by_id(plotter, session, node_id, pv_module=pv_module):
        session.node_id_edit_invalid = True
        render_tools_panel(plotter, session)
        if hasattr(plotter, "render"):
            plotter.render()
        return False
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


def _camera_bool(camera: Any, property_name: str, getter_name: str) -> bool | None:
    if hasattr(camera, getter_name):
        return bool(getattr(camera, getter_name)())
    if hasattr(camera, property_name):
        return bool(getattr(camera, property_name))
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
    view_angle = _camera_scalar(camera, "view_angle", "GetViewAngle")
    parallel_projection = _camera_bool(camera, "parallel_projection", "GetParallelProjection")
    return CameraState(
        position=position,  # type: ignore[arg-type]
        focal_point=focal_point,  # type: ignore[arg-type]
        view_up=view_up,  # type: ignore[arg-type]
        clipping_range=clipping_range,  # type: ignore[arg-type]
        parallel_scale=parallel_scale,
        view_angle=view_angle,
        parallel_projection=parallel_projection,
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


def _set_camera_bool(camera: Any, property_name: str, setter_name: str, value: bool | None) -> None:
    if value is None:
        return
    if hasattr(camera, setter_name):
        getattr(camera, setter_name)(bool(value))
    elif hasattr(camera, property_name):
        setattr(camera, property_name, bool(value))


def _restore_camera_state(plotter: Any, state: CameraState) -> bool:
    camera = getattr(plotter, "camera", None)
    if camera is None:
        return False

    _set_camera_tuple(camera, "position", "SetPosition", state.position)
    _set_camera_tuple(camera, "focal_point", "SetFocalPoint", state.focal_point)
    _set_camera_tuple(camera, "up", "SetViewUp", state.view_up)
    _set_camera_tuple(camera, "clipping_range", "SetClippingRange", state.clipping_range)
    _set_camera_scalar(camera, "parallel_scale", "SetParallelScale", state.parallel_scale)
    _set_camera_scalar(camera, "view_angle", "SetViewAngle", state.view_angle)
    _set_camera_bool(camera, "parallel_projection", "SetParallelProjection", state.parallel_projection)
    return True


def _store_initial_camera_state(plotter: Any, session: GraphViewerSession, view_id: ViewID | None = None) -> None:
    view = session.view_state(view_id)
    _select_view_renderer(plotter, view.view_id)
    active_file = session.file_for_view(view.view_id)
    if active_file is None or active_file.initial_camera_state is not None:
        return
    active_file.initial_camera_state = _capture_camera_state(plotter)


def _reset_camera_clipping_range(plotter: Any) -> None:
    if hasattr(plotter, "reset_camera_clipping_range"):
        plotter.reset_camera_clipping_range()
        return
    renderer = getattr(plotter, "renderer", None)
    if renderer is not None and hasattr(renderer, "ResetCameraClippingRange"):
        renderer.ResetCameraClippingRange()


def _store_shared_camera_state(plotter: Any, session: GraphViewerSession, view_id: ViewID | None = None) -> None:
    view = session.view_state(view_id)
    _select_view_renderer(plotter, view.view_id)
    if not session.camera_sync_enabled or session.file_for_view(view.view_id) is None:
        return
    state = _capture_camera_state(plotter)
    if state is not None:
        session.shared_camera_state = state


def _sync_camera_to_other_views(plotter: Any, session: GraphViewerSession, source_view_id: ViewID | None = None) -> None:
    if not session.camera_sync_enabled or session.layout_mode != "double":
        return
    source = session.view_state(source_view_id)
    _store_shared_camera_state(plotter, session, source.view_id)
    if session.shared_camera_state is None:
        return
    for view_id in ("a", "b"):
        if view_id == source.view_id or session.file_for_view(view_id) is None:
            continue
        _select_view_renderer(plotter, view_id)
        if _restore_camera_state(plotter, session.shared_camera_state):
            _reset_camera_clipping_range(plotter)
    _select_view_renderer(plotter, source.view_id)


def _normalized(vector: np.ndarray) -> np.ndarray | None:
    norm = float(np.linalg.norm(vector))
    if not np.isfinite(norm) or norm <= 0:
        return None
    return vector / norm


def _rotate_vector(vector: np.ndarray, axis: np.ndarray, angle: float) -> np.ndarray:
    axis_unit = _normalized(axis)
    if axis_unit is None or not np.isfinite(angle):
        return vector
    cos_angle = float(np.cos(angle))
    sin_angle = float(np.sin(angle))
    return (
        vector * cos_angle
        + np.cross(axis_unit, vector) * sin_angle
        + axis_unit * float(np.dot(axis_unit, vector)) * (1.0 - cos_angle)
    )


def _active_scene_center_and_radius(session: GraphViewerSession) -> tuple[np.ndarray, float] | None:
    active_file = session.active_file
    if active_file is None:
        return None
    lower, upper = _scene_bounds(active_file)
    center = (lower + upper) / 2.0
    radius = float(np.linalg.norm(upper - lower) / 2.0)
    if not np.isfinite(radius) or radius <= 0:
        radius = CAMERA_MIN_DISTANCE
    return center, radius


def _refresh_after_camera_navigation(plotter: Any, session: GraphViewerSession) -> None:
    _reset_camera_clipping_range(plotter)
    _sync_camera_to_other_views(plotter, session)
    if hasattr(plotter, "render"):
        plotter.render()


def _zoom_active_camera(plotter: Any, session: GraphViewerSession, *, direction: float) -> bool:
    """Move the camera toward or away from the active object's displayed bounds center."""
    _select_view_renderer(plotter, session.active_view_id)
    scene = _active_scene_center_and_radius(session)
    if scene is None:
        return False
    center, radius = scene

    camera = getattr(plotter, "camera", None)
    if camera is None:
        return False
    position = _camera_tuple(camera, "position", "GetPosition")
    if position is None:
        return False

    offset = np.asarray(position, dtype=float) - center
    distance = float(np.linalg.norm(offset))
    if not np.isfinite(distance) or distance <= 0:
        return False
    min_distance = max(radius * CAMERA_MIN_DISTANCE_FRACTION, CAMERA_MIN_DISTANCE)
    zoom_delta = CAMERA_ZOOM_FRACTION * distance
    next_distance = distance - float(direction) * zoom_delta
    if next_distance < min_distance:
        next_distance = min_distance
    next_position = center + (offset / distance) * next_distance

    _set_camera_tuple(camera, "position", "SetPosition", tuple(float(value) for value in next_position))
    _refresh_after_camera_navigation(plotter, session)
    return True


def fit_active_preview(plotter: Any, session: GraphViewerSession) -> bool:
    """Fit the active object by changing camera distance while preserving orientation."""
    _select_view_renderer(plotter, session.active_view_id)
    scene = _active_scene_center_and_radius(session)
    camera = getattr(plotter, "camera", None)
    if scene is None or camera is None:
        return False
    center, radius = scene

    position = _camera_tuple(camera, "position", "GetPosition")
    focal_point = _camera_tuple(camera, "focal_point", "GetFocalPoint")
    view_up = _camera_tuple(camera, "up", "GetViewUp")
    if position is None or focal_point is None:
        return False

    view_direction = _normalized(np.asarray(focal_point, dtype=float) - np.asarray(position, dtype=float))
    if view_direction is None:
        return False

    parallel_projection = _camera_bool(camera, "parallel_projection", "GetParallelProjection")
    current_distance = float(np.linalg.norm(np.asarray(position, dtype=float) - np.asarray(focal_point, dtype=float)))
    if not np.isfinite(current_distance) or current_distance <= 0:
        current_distance = max(radius * 2.0, CAMERA_MIN_DISTANCE)

    if parallel_projection:
        next_distance = current_distance
        _set_camera_scalar(camera, "parallel_scale", "SetParallelScale", max(radius * FIT_PREVIEW_MARGIN, CAMERA_MIN_DISTANCE))
    else:
        view_angle = _camera_scalar(camera, "view_angle", "GetViewAngle") or DEFAULT_CAMERA_VIEW_ANGLE
        half_angle = np.deg2rad(max(min(float(view_angle), 170.0), 1.0) / 2.0)
        next_distance = max(radius * FIT_PREVIEW_MARGIN / max(float(np.sin(half_angle)), 1e-6), CAMERA_MIN_DISTANCE)

    next_position = center - view_direction * next_distance
    _set_camera_tuple(camera, "position", "SetPosition", tuple(float(value) for value in next_position))
    _set_camera_tuple(camera, "focal_point", "SetFocalPoint", tuple(float(value) for value in center))
    if view_up is not None:
        _set_camera_tuple(camera, "up", "SetViewUp", view_up)
    _reset_camera_clipping_range(plotter)
    if session.camera_sync_enabled:
        _sync_camera_to_other_views(plotter, session)
    if hasattr(plotter, "render"):
        plotter.render()
    return True


def _remove_graph_actors(plotter: Any, session: GraphViewerSession, view_id: ViewID | None = None) -> None:
    view = session.view_state(view_id)
    if not view.graph_actors:
        view.graph_node_actor = None
        view.graph_edge_actor = None
        return
    if hasattr(plotter, "remove_actor"):
        for actor in view.graph_actors:
            if actor is not None:
                try:
                    plotter.remove_actor(actor, render=False)
                except TypeError:
                    plotter.remove_actor(actor)
    view.graph_actors.clear()
    view.graph_node_actor = None
    view.graph_edge_actor = None


def _update_graph_appearance(session: GraphViewerSession, view_id: ViewID | None = None) -> bool:
    """Apply point/line widths without reconstructing rendered data."""
    view = session.view_state(view_id)
    if view.graph_node_actor is None:
        return False
    view.graph_node_actor.GetProperty().SetPointSize(float(view.options.node_size))
    if view.graph_edge_actor is not None:
        view.graph_edge_actor.GetProperty().SetLineWidth(float(view.options.edge_thickness))
    return True


def render_active_graph(
    plotter: Any,
    session: GraphViewerSession,
    *,
    pv_module: Any | None = None,
    reset_camera: bool = True,
    view_id: ViewID | None = None,
) -> None:
    """Render the active session file using committed appearance options."""
    apply_view_layout(plotter, session)
    render_view_headers(plotter, session)
    view = session.view_state(view_id)
    _select_view_renderer(plotter, view.view_id)
    _remove_graph_actors(plotter, session, view.view_id)
    active_file = session.file_for_view(view.view_id)
    if active_file is None:
        view.interactive_enabled = False
        clear_interactive_selection(plotter, session, view.view_id)
        _set_status(plotter, session)
        render_tools_panel(plotter, session)
        if hasattr(plotter, "render"):
            plotter.render()
        return

    if active_file.kind != "graphml":
        view.interactive_enabled = False
        clear_interactive_selection(plotter, session, view.view_id)
    elif view.selected_node_index is not None and view.selected_node_index >= active_file.data.node_count:  # type: ignore[union-attr]
        clear_interactive_selection(plotter, session, view.view_id)

    if active_file.kind == "graphml":
        graph_data = active_file.data if isinstance(active_file.data, GraphVisualizationData) else None
        if graph_data is not None:
            actors, view.graph_edge_actor, view.graph_node_actor = _add_graph_scene(
                plotter, graph_data, view.options, pv_module=pv_module
            )
            view.graph_actors.extend(actors)
    else:
        nifti_data = active_file.data if isinstance(active_file.data, NiftiVisualizationData) else None
        if nifti_data is not None:
            actor = _build_instanced_nifti_actor(nifti_data, pv_module=pv_module)
            if actor is not None:
                try:
                    plotter.add_actor(actor, render=False)
                except TypeError:
                    plotter.add_actor(actor)
                view.graph_actors.append(actor)
    if reset_camera:
        plotter.reset_camera()
        _store_initial_camera_state(plotter, session, view.view_id)
        if session.camera_sync_enabled:
            if session.shared_camera_state is None:
                _store_shared_camera_state(plotter, session, view.view_id)
            else:
                if _restore_camera_state(plotter, session.shared_camera_state):
                    _reset_camera_clipping_range(plotter)
    _set_status(plotter, session)
    render_tools_panel(plotter, session)
    render_selected_node_highlight(plotter, session, pv_module=pv_module, view_id=view.view_id)
    if hasattr(plotter, "render"):
        plotter.render()


def refresh_active_graph(plotter: Any, session: GraphViewerSession, *, pv_module: Any | None = None) -> None:
    """Commit preview slider values when relevant and rebuild the active scene."""
    if session.active_kind != "nifti":
        session.apply_preview_options()
        graph_data = session.active_graph_data
        if graph_data is not None and _update_graph_appearance(session, session.active_view_id):
            render_selected_node_highlight(plotter, session, pv_module=pv_module, view_id=session.active_view_id)
            if hasattr(plotter, "render"):
                plotter.render()
            return
    render_active_graph(plotter, session, pv_module=pv_module, reset_camera=False, view_id=session.active_view_id)


def reset_active_view(plotter: Any, session: GraphViewerSession) -> None:
    """Restore the initial camera state for the active graph when available."""
    _select_view_renderer(plotter, session.active_view_id)
    active_file = session.active_file
    restored = False
    if active_file is not None and active_file.initial_camera_state is not None:
        restored = _restore_camera_state(plotter, active_file.initial_camera_state)

    if not restored and hasattr(plotter, "reset_camera"):
        plotter.reset_camera()
        _store_initial_camera_state(plotter, session)
    if session.camera_sync_enabled:
        _sync_camera_to_other_views(plotter, session)
    _set_status(plotter, session)
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
    _store_shared_camera_state(plotter, session)
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
    clear_interactive_selection(plotter, session, session.active_view_id)
    session.interactive_enabled = False
    _end_camera_orbit_drag(session)
    _store_shared_camera_state(plotter, session)
    if session.layout_mode == "double":
        session.clear_active_view_file()
        render_active_graph(plotter, session, pv_module=pv_module, view_id=session.active_view_id)
    else:
        session.close_active_file()
        if session.active_file is None:
            session.shared_camera_state = None
        render_active_graph(plotter, session, pv_module=pv_module)


def switch_previous_graph(plotter: Any, session: GraphViewerSession, *, pv_module: Any | None = None) -> None:
    clear_interactive_selection(plotter, session, session.active_view_id)
    session.interactive_enabled = False
    _end_camera_orbit_drag(session)
    _store_shared_camera_state(plotter, session)
    session.activate_previous()
    render_active_graph(plotter, session, pv_module=pv_module)


def switch_next_graph(plotter: Any, session: GraphViewerSession, *, pv_module: Any | None = None) -> None:
    clear_interactive_selection(plotter, session, session.active_view_id)
    session.interactive_enabled = False
    _end_camera_orbit_drag(session)
    _store_shared_camera_state(plotter, session)
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


def _visible_view_ids(session: GraphViewerSession) -> tuple[ViewID, ...]:
    return ("a", "b") if session.layout_mode == "double" else ("a",)


def render_visible_views(plotter: Any, session: GraphViewerSession, *, pv_module: Any | None = None, reset_camera: bool = False) -> None:
    apply_view_layout(plotter, session)
    for view_id in _visible_view_ids(session):
        render_active_graph(plotter, session, pv_module=pv_module, reset_camera=reset_camera, view_id=view_id)
    render_tools_panel(plotter, session)
    render_file_panel(plotter, session)


def set_layout_mode(
    plotter: Any,
    session: GraphViewerSession,
    mode: ViewLayoutMode,
    *,
    pv_module: Any | None = None,
) -> None:
    if mode == session.layout_mode:
        session.layout_menu_open = False
        render_tools_panel(plotter, session)
        return
    if mode == "double":
        session.views["a"].file_index = session.active_index
        session.views["b"].file_index = None
        session.layout_mode = "double"
        session.active_view_id = "a"
        session.camera_sync_enabled = True
    else:
        session.active_view_id = "a"
        session.layout_mode = "single"
        session.views["b"].file_list_open = False
        session.views["b"].interactive_enabled = False
        _remove_graph_actors(plotter, session, "b")
        _remove_selected_node_highlight(plotter, session, "b")
    session.layout_menu_open = False
    session.view_menu_open = None
    render_visible_views(plotter, session, pv_module=pv_module, reset_camera=False)


def set_active_view(plotter: Any, session: GraphViewerSession, view_id: ViewID) -> bool:
    if view_id not in _visible_view_ids(session):
        return False
    if session.active_view_id == view_id:
        return False
    session.active_view_id = view_id
    _clear_node_id_edit(session)
    _select_view_renderer(plotter, view_id)
    render_tools_panel(plotter, session)
    render_file_panel(plotter, session)
    render_view_headers(plotter, session)
    if hasattr(plotter, "render"):
        plotter.render()
    return True


def _view_at_display_position(plotter: Any, session: GraphViewerSession, x_pos: int, y_pos: int) -> ViewID | None:
    del y_pos
    if session.layout_mode != "double":
        return "a"
    width, _height = _plotter_window_size(plotter)
    scene_right = int(round(width * _scene_area_fraction(plotter)))
    if x_pos < 0 or x_pos > scene_right:
        return None
    return "a" if x_pos < scene_right / 2 else "b"


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
    hovered_view_id: ViewID | None = None
    for hitbox in session.file_hitboxes:
        if hitbox.action == "open-file-list" and hitbox.contains(x_pos, y_pos):
            hovered_view_id = hitbox.view_id or session.active_view_id
            break
    changed = False
    for view_id, view in session.views.items():
        should_open = hovered_view_id == view_id
        if view.file_list_open != should_open:
            view.file_list_open = should_open
            changed = True
    if not changed:
        return False
    render_file_panel(plotter, session)
    return True


def _inside_tools_panel(plotter: Any, session: GraphViewerSession, x_pos: int, y_pos: int) -> bool:
    if not session.tools_panel_visible:
        return False
    panel_x, panel_top, panel_bottom = _tools_panel_geometry(plotter)
    return panel_x <= x_pos <= panel_x + _tools_panel_width(plotter) and panel_bottom <= y_pos <= panel_top


def _tools_panel_visible_height(plotter: Any) -> int:
    _window_width, height = _plotter_window_size(plotter)
    return max(TOOLS_PANEL_MIN_HEIGHT, height - TOOLS_PANEL_TOP_MARGIN - TOOLS_PANEL_BOTTOM_MARGIN)


def _tools_scroll_max(plotter: Any) -> float:
    visible_height = _tools_panel_visible_height(plotter)
    return float(max(0, TOOLS_PANEL_CONTENT_HEIGHT - visible_height))


def _clamp_tools_scroll(plotter: Any, session: GraphViewerSession) -> None:
    session.tools_scroll_offset = min(max(float(session.tools_scroll_offset), 0.0), _tools_scroll_max(plotter))


def _tools_content_top(plotter: Any, session: GraphViewerSession) -> int:
    panel_x, panel_top, _panel_bottom = _tools_panel_geometry(plotter)
    del panel_x
    _clamp_tools_scroll(plotter, session)
    return panel_top + int(round(session.tools_scroll_offset))


def _tools_row_visible(plotter: Any, y_pos: int, height: int = COMMAND_BUTTON_HEIGHT) -> bool:
    _panel_x, panel_top, panel_bottom = _tools_panel_geometry(plotter)
    visible_bottom = panel_bottom + TOOLS_VIEWPORT_CLIP_PADDING
    visible_top = panel_top - TOOLS_VIEWPORT_CLIP_PADDING
    return y_pos >= visible_bottom and y_pos + height <= visible_top


def _scroll_tools_panel(
    plotter: Any,
    session: GraphViewerSession,
    delta: float,
    *,
    include_sliders: bool = True,
) -> bool:
    if not session.tools_panel_visible or _tools_scroll_max(plotter) <= 0:
        return False
    previous_offset = session.tools_scroll_offset
    session.tools_scroll_offset = previous_offset + float(delta)
    _clamp_tools_scroll(plotter, session)
    if session.tools_scroll_offset == previous_offset:
        return False
    render_tools_panel(plotter, session, include_sliders=include_sliders)
    if hasattr(plotter, "render"):
        plotter.render()
    return True


def _tools_scrollbar_geometry(plotter: Any, session: GraphViewerSession) -> tuple[int, int, int, int] | None:
    max_scroll = _tools_scroll_max(plotter)
    if not session.tools_panel_visible or max_scroll <= 0:
        return None
    panel_x, panel_top, panel_bottom = _tools_panel_geometry(plotter)
    track_height = panel_top - panel_bottom - 2 * TOOLS_PANEL_PADDING
    if track_height <= 0:
        return None
    visible_height = _tools_panel_visible_height(plotter)
    thumb_height = max(34, int(round(track_height * visible_height / TOOLS_PANEL_CONTENT_HEIGHT)))
    thumb_travel = max(1, track_height - thumb_height)
    thumb_y = panel_top - TOOLS_PANEL_PADDING - thumb_height - int(
        round((session.tools_scroll_offset / max_scroll) * thumb_travel)
    )
    thumb_x = panel_x + _tools_panel_width(plotter) - TOOLS_PANEL_PADDING - TOOLS_SCROLLBAR_WIDTH
    return thumb_x, thumb_y, TOOLS_SCROLLBAR_WIDTH, thumb_height


def _begin_tools_scroll_drag(plotter: Any, session: GraphViewerSession, x_pos: int, y_pos: int) -> bool:
    geometry = _tools_scrollbar_geometry(plotter, session)
    if geometry is None:
        return False
    thumb_x, thumb_y, thumb_width, thumb_height = geometry
    if not (thumb_x <= x_pos <= thumb_x + thumb_width and thumb_y <= y_pos <= thumb_y + thumb_height):
        return False
    session.tools_scroll_dragging = True
    session.tools_scroll_drag_last_y = y_pos
    return True


def _update_tools_scroll_drag(plotter: Any, session: GraphViewerSession, x_pos: int, y_pos: int) -> bool:
    del x_pos
    if not session.tools_scroll_dragging or session.tools_scroll_drag_last_y is None:
        return False
    geometry = _tools_scrollbar_geometry(plotter, session)
    if geometry is None:
        return False
    _thumb_x, _thumb_y, _thumb_width, thumb_height = geometry
    panel_x, panel_top, panel_bottom = _tools_panel_geometry(plotter)
    del panel_x
    track_height = panel_top - panel_bottom - 2 * TOOLS_PANEL_PADDING
    thumb_travel = max(1, track_height - thumb_height)
    max_scroll = _tools_scroll_max(plotter)
    delta_y = y_pos - session.tools_scroll_drag_last_y
    session.tools_scroll_drag_last_y = y_pos
    return _scroll_tools_panel(plotter, session, -float(delta_y) * max_scroll / thumb_travel)


def _end_tools_scroll_drag(session: GraphViewerSession) -> bool:
    was_dragging = session.tools_scroll_dragging
    session.tools_scroll_dragging = False
    session.tools_scroll_drag_last_y = None
    return was_dragging


def _set_appearance_slider_from_display_x(
    plotter: Any,
    session: GraphViewerSession,
    hitbox: UIHitbox,
    x_pos: int,
    *,
    pv_module: Any | None = None,
) -> bool:
    if hitbox.value not in ("node", "edge") or session.active_kind != "graphml":
        return False
    bounds = _appearance_slider_bounds(hitbox.value)
    fraction = min(max((float(x_pos) - hitbox.x) / max(float(hitbox.width), 1.0), 0.0), 1.0)
    value = bounds[0] + fraction * (bounds[1] - bounds[0])
    changed = _commit_graph_preview_value(plotter, session, option=hitbox.value, value=value, pv_module=pv_module)
    if changed:
        render_tools_panel(plotter, session)
        if hasattr(plotter, "render"):
            plotter.render()
    return True


def _update_appearance_slider_drag(
    plotter: Any,
    session: GraphViewerSession,
    x_pos: int,
    y_pos: int,
    *,
    pv_module: Any | None = None,
) -> bool:
    del y_pos
    option = session.appearance_slider_dragging
    if option is None:
        return False
    for hitbox in session.command_hitboxes:
        if hitbox.action == "appearance-slider" and hitbox.value == option:
            _set_appearance_slider_from_display_x(plotter, session, hitbox, x_pos, pv_module=pv_module)
            return True
    session.appearance_slider_dragging = None
    return False


def _end_appearance_slider_drag(session: GraphViewerSession) -> bool:
    was_dragging = session.appearance_slider_dragging is not None
    session.appearance_slider_dragging = None
    return was_dragging


def _nearest_graph_node_to_world_point(graph_data: GraphVisualizationData, point: Sequence[float]) -> int | None:
    world_point = np.asarray(point, dtype=float)
    if world_point.shape != (3,) or not np.isfinite(world_point).all():
        return None
    distances = np.linalg.norm(graph_data.node_positions - world_point, axis=1)
    if distances.size == 0 or not np.isfinite(distances).any():
        return None
    return int(np.nanargmin(distances))


def _picked_graph_node_index(plotter: Any, session: GraphViewerSession, x_pos: int, y_pos: int) -> int | None:
    graph_data = session.active_graph_data
    renderer = getattr(plotter, "renderer", None)
    if graph_data is None or renderer is None:
        return None
    try:
        from vtkmodules.vtkRenderingCore import vtkCellPicker

        picker = vtkCellPicker()
        picker.SetTolerance(0.01)
        if not picker.Pick(float(x_pos), float(y_pos), 0.0, renderer):
            return None
        pick_position = picker.GetPickPosition()
    except Exception:
        return None
    return _nearest_graph_node_to_world_point(graph_data, pick_position)


def _nearest_graph_node_index(plotter: Any, session: GraphViewerSession, x_pos: int, y_pos: int) -> int | None:
    graph_data = session.active_graph_data
    if graph_data is None:
        return None
    picked_index = _picked_graph_node_index(plotter, session, x_pos, y_pos)
    if picked_index is not None:
        return picked_index
    best_index: int | None = None
    best_distance = float("inf")
    for index, position in enumerate(graph_data.node_positions):
        display_point = _display_point(plotter, position)
        if display_point is None:
            continue
        distance = float(np.hypot(display_point[0] - x_pos, display_point[1] - y_pos))
        if distance < best_distance:
            best_distance = distance
            best_index = index
    pick_radius = max(INTERACTIVE_PICK_RADIUS, float(session.active_view.options.node_size))
    return best_index if best_distance <= pick_radius else None


def select_graph_node_at_display_position(
    plotter: Any,
    session: GraphViewerSession,
    x_pos: int,
    y_pos: int,
    *,
    pv_module: Any | None = None,
) -> bool:
    if not session.interactive_enabled or session.active_kind != "graphml":
        return False
    if _inside_tools_panel(plotter, session, x_pos, y_pos):
        return False
    node_index = _nearest_graph_node_index(plotter, session, x_pos, y_pos)
    if node_index is None:
        return False
    return select_graph_node(plotter, session, node_index, pv_module=pv_module)


def _begin_camera_orbit_drag(plotter: Any, session: GraphViewerSession, x_pos: int, y_pos: int) -> bool:
    _select_view_renderer(plotter, session.active_view_id)
    if session.active_file is None:
        return False
    if _inside_tools_panel(plotter, session, x_pos, y_pos):
        return False
    if _active_scene_center_and_radius(session) is None:
        return False
    if getattr(plotter, "camera", None) is None:
        return False
    session.camera_orbit_dragging = True
    session.camera_orbit_last_position = (x_pos, y_pos)
    return True


def _update_camera_orbit_drag(plotter: Any, session: GraphViewerSession, x_pos: int, y_pos: int) -> bool:
    _select_view_renderer(plotter, session.active_view_id)
    if not session.camera_orbit_dragging or session.camera_orbit_last_position is None:
        return False
    last_x, last_y = session.camera_orbit_last_position
    session.camera_orbit_last_position = (x_pos, y_pos)
    dx = x_pos - last_x
    dy = y_pos - last_y
    if dx == 0 and dy == 0:
        return True

    scene = _active_scene_center_and_radius(session)
    camera = getattr(plotter, "camera", None)
    if scene is None or camera is None:
        return False
    center, _radius = scene
    position = _camera_tuple(camera, "position", "GetPosition")
    view_up = _camera_tuple(camera, "up", "GetViewUp")
    if position is None or view_up is None:
        return False

    offset = np.asarray(position, dtype=float) - center
    distance = float(np.linalg.norm(offset))
    if not np.isfinite(distance) or distance <= 0:
        return False
    up = _normalized(np.asarray(view_up, dtype=float))
    if up is None:
        return False
    view_direction = _normalized(-offset)
    if view_direction is None:
        return False
    right = _normalized(np.cross(view_direction, up))
    if right is None:
        return False

    yaw = -float(dx) * CAMERA_ORBIT_RADIANS_PER_PIXEL
    pitch = -float(dy) * CAMERA_ORBIT_RADIANS_PER_PIXEL
    next_offset = _rotate_vector(offset, up, yaw)
    next_up = _rotate_vector(up, right, pitch)
    next_offset = _rotate_vector(next_offset, right, pitch)
    next_up = _normalized(next_up)
    if next_up is None:
        return False
    next_offset_unit = _normalized(next_offset)
    if next_offset_unit is None:
        return False
    next_position = center + next_offset_unit * distance

    _set_camera_tuple(camera, "position", "SetPosition", tuple(float(value) for value in next_position))
    _set_camera_tuple(camera, "up", "SetViewUp", tuple(float(value) for value in next_up))
    _refresh_after_camera_navigation(plotter, session)
    return True


def _end_camera_orbit_drag(session: GraphViewerSession) -> None:
    session.camera_orbit_dragging = False
    session.camera_orbit_last_position = None


def _event_key(caller: Any) -> tuple[str, str]:
    key_sym = str(caller.GetKeySym()) if hasattr(caller, "GetKeySym") else ""
    key_code = str(caller.GetKeyCode()) if hasattr(caller, "GetKeyCode") else ""
    return key_sym, key_code


def select_relative_graph_node(
    plotter: Any,
    session: GraphViewerSession,
    delta: int,
    *,
    pv_module: Any | None = None,
) -> bool:
    graph_data = session.active_graph_data
    if not session.interactive_enabled or graph_data is None or session.selected_node_index is None:
        return False
    node_index = (session.selected_node_index + int(delta)) % graph_data.node_count
    return select_graph_node(plotter, session, node_index, pv_module=pv_module)


def _handle_interactive_key_press(
    plotter: Any,
    session: GraphViewerSession,
    caller: Any,
    *,
    pv_module: Any | None = None,
) -> bool:
    key_sym, key_code = _event_key(caller)
    if key_sym in ("Left", "LeftArrow"):
        return select_relative_graph_node(plotter, session, -1, pv_module=pv_module)
    if key_sym in ("Right", "RightArrow"):
        return select_relative_graph_node(plotter, session, 1, pv_module=pv_module)
    if not session.node_id_editing:
        return False
    if key_sym in ("Return", "KP_Enter") or key_code in ("\r", "\n"):
        _commit_node_id_edit(plotter, session, pv_module=pv_module)
        return True
    if key_sym == "Escape":
        _clear_node_id_edit(session)
    elif key_sym in ("BackSpace", "Delete"):
        session.node_id_edit_buffer = "" if session.node_id_edit_replace_pending else session.node_id_edit_buffer[:-1]
        session.node_id_edit_invalid = False
        session.node_id_edit_replace_pending = False
    elif key_code and len(key_code) == 1 and key_code.isprintable():
        next_text = key_code if session.node_id_edit_replace_pending else session.node_id_edit_buffer + key_code
        session.node_id_edit_buffer = next_text
        session.node_id_edit_invalid = False
        session.node_id_edit_replace_pending = False
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
            view_id = hitbox.view_id or session.active_view_id
            set_active_view(plotter, session, view_id)
            clear_interactive_selection(plotter, session, view_id)
            session.view_state(view_id).interactive_enabled = False
            _end_camera_orbit_drag(session)
            _store_shared_camera_state(plotter, session, view_id)
            session.assign_view_file(view_id, hitbox.index)
            render_active_graph(plotter, session, pv_module=pv_module, view_id=view_id)
            return True
        if hitbox.action == "open-file-list":
            view_id = hitbox.view_id or session.active_view_id
            set_active_view(plotter, session, view_id)
            session.view_state(view_id).file_list_open = True
            render_file_panel(plotter, session)
            return True
        if hitbox.action == "toggle-layout-menu":
            session.layout_menu_open = not session.layout_menu_open
            session.view_menu_open = None
            render_tools_panel(plotter, session)
            if hasattr(plotter, "render"):
                plotter.render()
            return True
        if hitbox.action == "set-layout":
            set_layout_mode(plotter, session, "double" if hitbox.index == 1 else "single", pv_module=pv_module)
            return True
        if hitbox.action == "toggle-view-menu" and hitbox.view_id is not None:
            session.view_menu_open = None if session.view_menu_open == hitbox.view_id else hitbox.view_id
            session.layout_menu_open = False
            render_tools_panel(plotter, session)
            if hasattr(plotter, "render"):
                plotter.render()
            return True
        if hitbox.action == "assign-view-file" and hitbox.view_id is not None:
            set_active_view(plotter, session, hitbox.view_id)
            session.assign_view_file(hitbox.view_id, hitbox.index)
            session.view_menu_open = None
            render_active_graph(plotter, session, pv_module=pv_module, view_id=hitbox.view_id)
            return True
        if hitbox.action == "appearance-slider" and hitbox.value in ("node", "edge"):
            session.appearance_slider_dragging = hitbox.value
            _set_appearance_slider_from_display_x(plotter, session, hitbox, x_pos, pv_module=pv_module)
            return True
        if hitbox.action == "toggle-interactive":
            toggle_interactive(plotter, session, pv_module=pv_module)
            return True
        if hitbox.action == "toggle-camera-sync":
            toggle_camera_sync(plotter, session)
            return True
        if hitbox.action == "edit-node-id":
            _begin_node_id_edit(plotter, session)
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
        if hitbox.action == "fit-preview":
            fit_active_preview(plotter, session)
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
        apply_view_layout(plotter, session)
        render_view_headers(plotter, session)
        render_tools_panel(plotter, session)
        render_file_panel(plotter, session)
        if hasattr(plotter, "render"):
            plotter.render()

    def _on_mouse_move(caller: Any, _event: str) -> None:
        _set_event_handled("MouseMoveEvent", False)
        position = _event_position(caller)
        if position is not None:
            if _update_appearance_slider_drag(plotter, session, *position, pv_module=pv_module):
                _set_event_handled("MouseMoveEvent", True)
                return
            if _update_tools_scroll_drag(plotter, session, *position):
                _set_event_handled("MouseMoveEvent", True)
                return
            if _update_camera_orbit_drag(plotter, session, *position):
                _set_event_handled("MouseMoveEvent", True)
                return
            update_file_list_hover(plotter, session, *position)

    def _on_left_click(caller: Any, _event: str) -> None:
        _set_event_handled("LeftButtonPressEvent", False)
        position = _event_position(caller)
        if position is not None:
            if _begin_tools_scroll_drag(plotter, session, *position):
                _set_event_handled("LeftButtonPressEvent", True)
                return
            if dispatch_ui_click(plotter, session, *position, pv_module=pv_module):
                _set_event_handled("LeftButtonPressEvent", True)
                return
            view_id = _view_at_display_position(plotter, session, *position)
            if view_id is not None:
                set_active_view(plotter, session, view_id)
            if select_graph_node_at_display_position(plotter, session, *position, pv_module=pv_module):
                _set_event_handled("LeftButtonPressEvent", True)
                return
            if _begin_camera_orbit_drag(plotter, session, *position):
                _set_event_handled("LeftButtonPressEvent", True)

    def _on_left_release(_caller: Any, _event: str) -> None:
        _end_appearance_slider_drag(session)
        if _end_tools_scroll_drag(session):
            render_tools_panel(plotter, session)
            if hasattr(plotter, "render"):
                plotter.render()
        _end_camera_orbit_drag(session)

    def _on_key_press(caller: Any, _event: str) -> None:
        _handle_interactive_key_press(plotter, session, caller, pv_module=pv_module)

    def _on_wheel_forward(caller: Any, _event: str) -> None:
        _set_event_handled("MouseWheelForwardEvent", False)
        position = _event_position(caller)
        if position is not None and _inside_tools_panel(plotter, session, *position):
            if _scroll_tools_panel(plotter, session, -TOOLS_SCROLL_STEP):
                _set_event_handled("MouseWheelForwardEvent", True)
            else:
                _set_event_handled("MouseWheelForwardEvent", True)
            return
        if _zoom_active_camera(plotter, session, direction=1.0):
            _set_event_handled("MouseWheelForwardEvent", True)

    def _on_wheel_backward(caller: Any, _event: str) -> None:
        _set_event_handled("MouseWheelBackwardEvent", False)
        position = _event_position(caller)
        if position is not None and _inside_tools_panel(plotter, session, *position):
            if _scroll_tools_panel(plotter, session, TOOLS_SCROLL_STEP):
                _set_event_handled("MouseWheelBackwardEvent", True)
            else:
                _set_event_handled("MouseWheelBackwardEvent", True)
            return
        if _zoom_active_camera(plotter, session, direction=-1.0):
            _set_event_handled("MouseWheelBackwardEvent", True)

    def _on_interaction(_caller: Any, _event: str) -> None:
        _sync_camera_to_other_views(plotter, session)

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
            _add_cancellable_observer("MouseWheelForwardEvent", _on_wheel_forward)
            _add_cancellable_observer("MouseWheelBackwardEvent", _on_wheel_backward)
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
        _add_cancellable_observer("MouseWheelForwardEvent", _on_wheel_forward)
        _add_cancellable_observer("MouseWheelBackwardEvent", _on_wheel_backward)
        interactor.AddObserver("LeftButtonReleaseEvent", _on_left_release)
        interactor.AddObserver("KeyPressEvent", _on_key_press)
        interactor.AddObserver("InteractionEvent", _on_interaction)
        return True
    return False


def _tools_panel_geometry(plotter: Any) -> tuple[int, int, int]:
    """Return panel x, top edge, and bottom edge in display coordinates."""
    window_width, height = _plotter_window_size(plotter)
    panel_x = int(window_width * 0.75)
    panel_top = height - TOOLS_PANEL_TOP_MARGIN
    return panel_x, panel_top, panel_top - _tools_panel_visible_height(plotter)


def _tools_panel_layout(plotter: Any, session: GraphViewerSession) -> dict[str, int]:
    """Return bottom/center y coordinates for grouped Tools-panel controls."""
    cursor_top = _tools_content_top(plotter, session) - TOOLS_PANEL_PADDING
    layout: dict[str, int] = {}
    row_stride = COMMAND_BUTTON_HEIGHT + COMMAND_BUTTON_GAP

    layout["session_header"] = cursor_top - TOOLS_SECTION_HEADER_HEIGHT
    layout["session_file"] = layout["session_header"] - TOOLS_SECTION_HEADER_GAP - COMMAND_BUTTON_HEIGHT
    layout["session_navigation"] = layout["session_file"] - row_stride

    cursor_top = layout["session_navigation"] - TOOLS_SECTION_GAP
    layout["view_layout_header"] = cursor_top - TOOLS_SECTION_HEADER_HEIGHT
    layout["layout_dropdown"] = layout["view_layout_header"] - TOOLS_SECTION_HEADER_GAP - COMMAND_BUTTON_HEIGHT
    layout["view_a_dropdown"] = layout["layout_dropdown"] - row_stride
    layout["view_b_dropdown"] = layout["view_a_dropdown"] - row_stride

    cursor_top = layout["view_b_dropdown"] - TOOLS_SECTION_GAP
    layout["camera_header"] = cursor_top - TOOLS_SECTION_HEADER_HEIGHT
    layout["camera_sync"] = layout["camera_header"] - TOOLS_SECTION_HEADER_GAP - COMMAND_BUTTON_HEIGHT
    layout["camera_view"] = layout["camera_sync"] - row_stride

    cursor_top = layout["camera_view"] - TOOLS_SECTION_GAP
    layout["appearance_header"] = cursor_top - TOOLS_SECTION_HEADER_HEIGHT
    layout["node_slider"] = layout["appearance_header"] - TOOLS_SECTION_HEADER_GAP - APPEARANCE_SLIDER_TOP_GAP
    layout["edge_slider"] = layout["node_slider"] - APPEARANCE_SLIDER_SPACING

    cursor_top = layout["edge_slider"] - APPEARANCE_SLIDER_BOTTOM_GAP
    layout["interactive_header"] = cursor_top - TOOLS_SECTION_HEADER_HEIGHT
    layout["interactive_toggle"] = layout["interactive_header"] - TOOLS_SECTION_HEADER_GAP - COMMAND_BUTTON_HEIGHT
    layout["node_id"] = layout["interactive_toggle"] - row_stride
    layout["x"] = layout["node_id"] - row_stride
    layout["y"] = layout["x"] - row_stride
    layout["z"] = layout["y"] - row_stride
    layout["degree"] = layout["z"] - row_stride
    return layout


def _add_tools_section_header(
    plotter: Any,
    actors: list[Any],
    *,
    title: str,
    x: int,
    y: int,
    width: int,
) -> None:
    """Add a centered bold section title with side separator lines."""
    center_x = x + width // 2
    center_y = y + TOOLS_SECTION_HEADER_HEIGHT // 2
    text_gap = 10
    text_slot_width = max(88, len(title) * 9 + 24)
    left_line_width = max(0, center_x - x - text_slot_width // 2 - text_gap)
    right_line_x = center_x + text_slot_width // 2 + text_gap
    right_line_width = max(0, x + width - right_line_x)
    line_y = center_y
    line_color = (0.38, 0.45, 0.52)
    for line_x, line_width in ((x, left_line_width), (right_line_x, right_line_width)):
        if line_width <= 0:
            continue
        actors.append(
            _add_overlay_rect(
                plotter,
                x=line_x,
                y=line_y,
                width=line_width,
                height=1,
                color=line_color,
                opacity=0.78,
            )
        )
    text_actor = _add_overlay_text(plotter, title, x=center_x, y=center_y, font_size=TOOLS_HEADER_FONT_SIZE, color="#f1f5f9")
    text_property = _text_actor_property(text_actor)
    if text_property is not None:
        if hasattr(text_property, "SetJustificationToCentered"):
            text_property.SetJustificationToCentered()
        if hasattr(text_property, "SetVerticalJustificationToCentered"):
            text_property.SetVerticalJustificationToCentered()
        if hasattr(text_property, "SetBold"):
            text_property.SetBold(True)
    actors.append(text_actor)


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
    font_size: int = TOOLS_BUTTON_FONT_SIZE,
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
    text_actor = _add_overlay_text(
        plotter,
        label,
        x=x + width // 2,
        y=y + height // 2,
        font_size=font_size,
        color="white",
    )
    text_property = _text_actor_property(text_actor)
    if text_property is not None:
        if hasattr(text_property, "SetJustificationToCentered"):
            text_property.SetJustificationToCentered()
        if hasattr(text_property, "SetVerticalJustificationToCentered"):
            text_property.SetVerticalJustificationToCentered()
    actors.append(text_actor)
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


def _view_label(view_id: ViewID) -> str:
    return "View A" if view_id == "a" else "View B"


def _loaded_file_label(loaded_file: LoadedVisualizationFile, *, max_length: int = 24) -> str:
    label = f"{_kind_label(loaded_file.kind)} {loaded_file.path.name}"
    return label if len(label) <= max_length else label[: max_length - 3] + "..."


def _view_dropdown_label(session: GraphViewerSession, view_id: ViewID) -> str:
    active = session.file_for_view(view_id)
    if active is None:
        return "Empty"
    return _loaded_file_label(active)


def _add_dropdown_button(
    plotter: Any,
    session: GraphViewerSession,
    *,
    label: str,
    value: str,
    action: str,
    x: int,
    y: int,
    width: int,
    enabled: bool = True,
    view_id: ViewID | None = None,
) -> None:
    background = (0.19, 0.26, 0.34) if enabled else (0.24, 0.25, 0.27)
    text_color = "white" if enabled else "#8f98a3"
    session.command_button_actors.append(
        _add_overlay_text(
            plotter,
            f"{label}:",
            x=x,
            y=y + 7,
            font_size=TOOLS_TEXT_FONT_SIZE,
            color="#d7dde5" if enabled else "#7d8590",
        )
    )
    field_x = x + 92
    field_width = width - 92
    session.command_button_actors.append(
        _add_overlay_rect(
            plotter,
            x=field_x,
            y=y,
            width=field_width,
            height=COMMAND_BUTTON_HEIGHT,
            color=background,
            opacity=0.94,
        )
    )
    session.command_button_actors.append(
        _add_overlay_text(plotter, f"{value} v", x=field_x + 8, y=y + 7, font_size=TOOLS_TEXT_FONT_SIZE, color=text_color)
    )
    if enabled:
        session.command_hitboxes.append(
            UIHitbox(
                name=f"dropdown-{action}",
                x=field_x,
                y=y,
                width=field_width,
                height=COMMAND_BUTTON_HEIGHT,
                action=action,
                view_id=view_id,
            )
        )


def _add_dropdown_menu(
    plotter: Any,
    session: GraphViewerSession,
    *,
    x: int,
    y: int,
    width: int,
    rows: Sequence[tuple[str, str, int | None, ViewID | None]],
) -> None:
    field_x = x + 92
    field_width = width - 92
    for row_index, (label, action, index, view_id) in enumerate(rows[:VIEW_LAYOUT_MENU_MAX_ROWS]):
        row_y = y - VIEW_LAYOUT_MENU_ROW_HEIGHT * (row_index + 1)
        menu_x = field_x
        menu_y = row_y - 2
        menu_height = VIEW_LAYOUT_MENU_ROW_HEIGHT + 4
        if not _tools_row_visible(plotter, menu_y, menu_height):
            continue
        session.command_button_actors.append(
            _add_overlay_rect(
                plotter,
                x=menu_x,
                y=menu_y,
                width=field_width,
                height=menu_height,
                color=(0.17, 0.21, 0.27),
                opacity=0.98,
            )
        )
        session.command_button_actors.append(
            _add_overlay_text(
                plotter,
                label,
                x=menu_x + 8,
                y=menu_y + 6,
                font_size=TOOLS_MENU_FONT_SIZE,
                color="white",
            )
        )
        session.command_hitboxes.append(
            UIHitbox(
                name=f"dropdown-row-{action}-{row_index}",
                x=menu_x,
                y=menu_y,
                width=field_width,
                height=menu_height,
                action=action,
                index=index,
                view_id=view_id,
            )
        )


def render_interactive_controls(plotter: Any, session: GraphViewerSession) -> None:
    """Draw GraphML interactive-selection controls in the Tools panel."""
    if not session.tools_panel_visible:
        return
    panel_x, _panel_top, _panel_bottom = _tools_panel_geometry(plotter)
    layout = _tools_panel_layout(plotter, session)
    inner_x = panel_x + TOOLS_PANEL_PADDING
    scroll_gutter = TOOLS_SCROLLBAR_GUTTER if _tools_scroll_max(plotter) > 0 else 0
    inner_width = _tools_panel_width(plotter) - 2 * TOOLS_PANEL_PADDING - scroll_gutter

    header_y = layout["interactive_header"]
    if _tools_row_visible(plotter, header_y, TOOLS_SECTION_HEADER_HEIGHT):
        _add_tools_section_header(
            plotter,
            session.command_button_actors,
            title="Interactive",
            x=inner_x,
            y=header_y,
            width=inner_width,
        )

    button_y = layout["interactive_toggle"]
    has_graphml_file = session.active_kind == "graphml"
    active = session.interactive_enabled and has_graphml_file
    interactive_button_background = (0.10, 0.45, 0.31) if active else (
        (0.19, 0.26, 0.34) if has_graphml_file else (0.29, 0.31, 0.34)
    )
    if _tools_row_visible(plotter, button_y):
        _add_ui_button(
            plotter,
            session.command_button_actors,
            session.command_hitboxes,
            label="Interactive",
            action="toggle-interactive",
            x=inner_x,
            y=button_y,
            width=inner_width,
            background=interactive_button_background,
        )

    position = selected_node_position(session)
    node_id = selected_node_id(session)
    node_degree = selected_node_degree(session)
    label_width = 104
    field_x = inner_x + label_width
    field_width = inner_width - label_width
    node_id_y = layout["node_id"]
    if _tools_row_visible(plotter, node_id_y):
        session.command_button_actors.append(
            _add_overlay_text(plotter, "Node id:", x=inner_x, y=node_id_y + 7, font_size=TOOLS_TEXT_FONT_SIZE, color="#d7dde5")
        )
        node_id_background = (0.42, 0.10, 0.12) if session.node_id_editing and session.node_id_edit_invalid else (
            (0.24, 0.34, 0.43) if session.node_id_editing else (0.15, 0.20, 0.26)
        )
        session.command_button_actors.append(
            _add_overlay_rect(
                plotter,
                x=field_x,
                y=node_id_y,
                width=field_width,
                height=COMMAND_BUTTON_HEIGHT,
                color=node_id_background,
                opacity=0.94,
            )
        )
        if session.node_id_editing:
            node_id_text = session.node_id_edit_buffer
        elif node_id is not None:
            node_id_text = node_id
        else:
            node_id_text = "--"
        session.command_button_actors.append(
            _add_overlay_text(plotter, node_id_text, x=field_x + 8, y=node_id_y + 7, font_size=TOOLS_TEXT_FONT_SIZE, color="white")
        )
        session.command_hitboxes.append(
            UIHitbox(
                name="node-id",
                x=field_x,
                y=node_id_y,
                width=field_width,
                height=COMMAND_BUTTON_HEIGHT,
                action="edit-node-id",
            )
        )

    for row_index, axis in enumerate(("x", "y", "z")):
        y_pos = layout[axis]
        if not _tools_row_visible(plotter, y_pos):
            continue
        session.command_button_actors.append(
            _add_overlay_text(plotter, f"{axis.upper()}:", x=inner_x, y=y_pos + 7, font_size=TOOLS_TEXT_FONT_SIZE, color="#d7dde5")
        )
        session.command_button_actors.append(
            _add_overlay_rect(
                plotter,
                x=field_x,
                y=y_pos,
                width=field_width,
                height=COMMAND_BUTTON_HEIGHT,
                color=(0.15, 0.20, 0.26),
                opacity=0.94,
            )
        )
        value_text = _format_coordinate(position[row_index]) if position is not None else "--"
        session.command_button_actors.append(
            _add_overlay_text(plotter, value_text, x=field_x + 8, y=y_pos + 7, font_size=TOOLS_TEXT_FONT_SIZE, color="white")
        )

    degree_y = layout["degree"]
    if not _tools_row_visible(plotter, degree_y):
        return
    session.command_button_actors.append(
        _add_overlay_text(plotter, "Node dgr:", x=inner_x, y=degree_y + 7, font_size=TOOLS_TEXT_FONT_SIZE, color="#d7dde5")
    )
    session.command_button_actors.append(
        _add_overlay_rect(
            plotter,
            x=field_x,
            y=degree_y,
            width=field_width,
            height=COMMAND_BUTTON_HEIGHT,
            color=(0.15, 0.20, 0.26),
            opacity=0.94,
        )
    )
    degree_text = str(node_degree) if node_degree is not None else "--"
    session.command_button_actors.append(
        _add_overlay_text(plotter, degree_text, x=field_x + 8, y=degree_y + 7, font_size=TOOLS_TEXT_FONT_SIZE, color="white")
    )


def render_view_layout_controls(plotter: Any, session: GraphViewerSession) -> None:
    """Draw layout mode and per-view assignment controls."""
    if not session.tools_panel_visible:
        return
    panel_x, _panel_top, _panel_bottom = _tools_panel_geometry(plotter)
    layout = _tools_panel_layout(plotter, session)
    inner_x = panel_x + TOOLS_PANEL_PADDING
    scroll_gutter = TOOLS_SCROLLBAR_GUTTER if _tools_scroll_max(plotter) > 0 else 0
    inner_width = _tools_panel_width(plotter) - 2 * TOOLS_PANEL_PADDING - scroll_gutter

    header_y = layout["view_layout_header"]
    if _tools_row_visible(plotter, header_y, TOOLS_SECTION_HEADER_HEIGHT):
        _add_tools_section_header(
            plotter,
            session.command_button_actors,
            title="View Layout",
            x=inner_x,
            y=header_y,
            width=inner_width,
        )

    layout_y = layout["layout_dropdown"]
    if _tools_row_visible(plotter, layout_y):
        _add_dropdown_button(
            plotter,
            session,
            label="Layout",
            value="Single View" if session.layout_mode == "single" else "Double View",
            action="toggle-layout-menu",
            x=inner_x,
            y=layout_y,
            width=inner_width,
        )

    enabled = session.layout_mode == "double"
    for view_id, row_key in (("a", "view_a_dropdown"), ("b", "view_b_dropdown")):
        row_y = layout[row_key]
        if not _tools_row_visible(plotter, row_y):
            continue
        _add_dropdown_button(
            plotter,
            session,
            label=_view_label(view_id),
            value=_view_dropdown_label(session, view_id),
            action="toggle-view-menu",
            x=inner_x,
            y=row_y,
            width=inner_width,
            enabled=enabled,
            view_id=view_id,
        )


def render_open_dropdown_menus(plotter: Any, session: GraphViewerSession) -> None:
    """Draw open dropdown menus as the final Tools overlay layer."""
    if not session.tools_panel_visible:
        return
    panel_x, _panel_top, _panel_bottom = _tools_panel_geometry(plotter)
    layout = _tools_panel_layout(plotter, session)
    scroll_gutter = TOOLS_SCROLLBAR_GUTTER if _tools_scroll_max(plotter) > 0 else 0
    inner_x = panel_x + TOOLS_PANEL_PADDING
    inner_width = _tools_panel_width(plotter) - 2 * TOOLS_PANEL_PADDING - scroll_gutter

    if session.layout_menu_open:
        _add_dropdown_menu(
            plotter,
            session,
            x=inner_x,
            y=layout["layout_dropdown"],
            width=inner_width,
            rows=(("Single View", "set-layout", None, None), ("Double View", "set-layout", 1, None)),
        )

    if session.layout_mode != "double" or session.view_menu_open is None:
        return
    row_key = "view_a_dropdown" if session.view_menu_open == "a" else "view_b_dropdown"
    rows: list[tuple[str, str, int | None, ViewID | None]] = [("Empty", "assign-view-file", None, session.view_menu_open)]
    rows.extend(
        (_loaded_file_label(loaded_file), "assign-view-file", index, session.view_menu_open)
        for index, loaded_file in enumerate(session.loaded_files)
    )
    _add_dropdown_menu(plotter, session, x=inner_x, y=layout[row_key], width=inner_width, rows=rows)


def render_command_buttons(plotter: Any, session: GraphViewerSession) -> None:
    """Draw session and camera controls in the visible Tools panel."""
    _remove_actor_list(plotter, session.command_button_actors)
    session.command_hitboxes.clear()
    if not session.tools_panel_visible:
        return

    panel_x, _panel_top, _panel_bottom = _tools_panel_geometry(plotter)
    layout = _tools_panel_layout(plotter, session)
    scroll_gutter = TOOLS_SCROLLBAR_GUTTER if _tools_scroll_max(plotter) > 0 else 0
    inner_x = panel_x + TOOLS_PANEL_PADDING
    inner_width = _tools_panel_width(plotter) - 2 * TOOLS_PANEL_PADDING - scroll_gutter
    button_width = (_tools_panel_width(plotter) - 2 * TOOLS_PANEL_PADDING - scroll_gutter - COMMAND_BUTTON_GAP) // 2

    section_headers = (
        ("Session", layout["session_header"]),
        ("Camera", layout["camera_header"]),
    )
    for title, y_pos in section_headers:
        if _tools_row_visible(plotter, y_pos, TOOLS_SECTION_HEADER_HEIGHT):
            _add_tools_section_header(
                plotter,
                session.command_button_actors,
                title=title,
                x=inner_x,
                y=y_pos,
                width=inner_width,
            )

    render_view_layout_controls(plotter, session)

    session_rows = (
        (layout["session_file"], (("Import", "import", (0.19, 0.26, 0.34)), ("Close", "close", (0.20, 0.24, 0.30)))),
        (
            layout["session_navigation"],
            (("< (Prev)", "previous", (0.15, 0.22, 0.31)), ("> (Next)", "next", (0.15, 0.22, 0.31))),
        ),
    )
    for y_pos, row in session_rows:
        if not _tools_row_visible(plotter, y_pos):
            continue
        for column, (label, action, background) in enumerate(row):
            x_pos = inner_x + column * (button_width + COMMAND_BUTTON_GAP)
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

    sync_button_y = layout["camera_sync"]
    sync_button_background = (0.10, 0.45, 0.31) if session.camera_sync_enabled else (0.19, 0.26, 0.34)
    if _tools_row_visible(plotter, sync_button_y):
        _add_ui_button(
            plotter,
            session.command_button_actors,
            session.command_hitboxes,
            label="Sync Camera",
            action="toggle-camera-sync",
            x=inner_x,
            y=sync_button_y,
            width=inner_width,
            background=sync_button_background,
        )

    view_button_y = layout["camera_view"]
    view_row = (("Reset View", "reset-view", (0.05, 0.28, 0.68)), ("Fit Preview", "fit-preview", (0.70, 0.08, 0.09)))
    if _tools_row_visible(plotter, view_button_y):
        for column, (label, action, background) in enumerate(view_row):
            x_pos = inner_x + column * (button_width + COMMAND_BUTTON_GAP)
            _add_ui_button(
                plotter,
                session.command_button_actors,
                session.command_hitboxes,
                label=label,
                action=action,
                x=x_pos,
                y=view_button_y,
                width=button_width,
                background=background,
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


def _appearance_slider_bounds(option: Literal["node", "edge"]) -> tuple[float, float]:
    return NODE_SIZE_RANGE if option == "node" else EDGE_THICKNESS_RANGE


def _appearance_slider_value(session: GraphViewerSession, option: Literal["node", "edge"]) -> float:
    value = session.preview_node_size if option == "node" else session.preview_edge_thickness
    bounds = _appearance_slider_bounds(option)
    return _clamp_preview_value(float(value if value is not None else bounds[0]), bounds)


def _render_appearance_slider_row(
    plotter: Any,
    session: GraphViewerSession,
    *,
    title: str,
    option: Literal["node", "edge"],
    center_y: int,
    x: int,
    width: int,
    enabled: bool,
) -> None:
    visible_y = int(center_y - APPEARANCE_SLIDER_RESERVED_HEIGHT // 2)
    if not _tools_row_visible(plotter, visible_y, APPEARANCE_SLIDER_RESERVED_HEIGHT):
        return

    bounds = _appearance_slider_bounds(option)
    value = _appearance_slider_value(session, option)
    fraction = (value - bounds[0]) / max(bounds[1] - bounds[0], 1e-9)
    fraction = min(max(float(fraction), 0.0), 1.0)
    title_color = "#d7dde5" if enabled else "#7d8590"
    track_color = (0.30, 0.36, 0.43) if enabled else (0.28, 0.30, 0.33)
    fill_color = (0.55, 0.64, 0.74) if enabled else (0.34, 0.36, 0.39)
    knob_color = (0.86, 0.89, 0.93) if enabled else (0.45, 0.47, 0.50)

    label_y = int(center_y + 14)
    track_x = x + 6
    track_width = max(40, width - 12)
    track_y = int(center_y - 10)
    track_height = 6
    knob_size = 14
    knob_x = int(round(track_x + fraction * track_width - knob_size / 2))
    knob_x = min(max(knob_x, track_x - knob_size // 2), track_x + track_width - knob_size // 2)

    session.command_button_actors.append(
        _add_overlay_text(plotter, title, x=x, y=label_y, font_size=TOOLS_TEXT_FONT_SIZE, color=title_color)
    )
    session.command_button_actors.append(
        _add_overlay_text(
            plotter,
            f"{value:.2g}",
            x=x + width - 34,
            y=label_y,
            font_size=TOOLS_TEXT_FONT_SIZE,
            color=title_color,
        )
    )
    session.command_button_actors.append(
        _add_overlay_rect(
            plotter,
            x=track_x,
            y=track_y,
            width=track_width,
            height=track_height,
            color=track_color,
            opacity=0.96,
        )
    )
    session.command_button_actors.append(
        _add_overlay_rect(
            plotter,
            x=track_x,
            y=track_y,
            width=max(1, int(round(track_width * fraction))),
            height=track_height,
            color=fill_color,
            opacity=0.98,
        )
    )
    session.command_button_actors.append(
        _add_overlay_rect(
            plotter,
            x=knob_x,
            y=track_y - 4,
            width=knob_size,
            height=knob_size,
            color=knob_color,
            opacity=0.98,
        )
    )
    if enabled:
        session.command_hitboxes.append(
            UIHitbox(
                name=f"appearance-slider-{option}",
                x=track_x,
                y=track_y - 10,
                width=track_width,
                height=track_height + 20,
                action="appearance-slider",
                value=option,
            )
        )


def render_graph_sliders(plotter: Any, session: GraphViewerSession, *, pv_module: Any | None = None) -> None:
    """Show GraphML appearance sliders only while the Tools panel is visible."""
    should_show = session.tools_panel_visible
    if not should_show:
        _remove_graph_sliders(plotter, session)
        return

    panel_x, _panel_top, _panel_bottom = _tools_panel_geometry(plotter)
    layout = _tools_panel_layout(plotter, session)
    scroll_gutter = TOOLS_SCROLLBAR_GUTTER if _tools_scroll_max(plotter) > 0 else 0
    inner_x = panel_x + TOOLS_PANEL_PADDING
    inner_width = _tools_panel_width(plotter) - 2 * TOOLS_PANEL_PADDING - scroll_gutter
    appearance_header_y = layout["appearance_header"]
    node_y_abs = layout["node_slider"]
    edge_y_abs = layout["edge_slider"]

    if _tools_row_visible(plotter, appearance_header_y, TOOLS_SECTION_HEADER_HEIGHT):
        _add_tools_section_header(
            plotter,
            session.command_button_actors,
            title="Apperance",
            x=inner_x,
            y=appearance_header_y,
            width=inner_width,
        )

    _remove_graph_sliders(plotter, session)
    enabled = session.active_kind == "graphml"
    _render_appearance_slider_row(
        plotter,
        session,
        title="Node Size",
        option="node",
        center_y=node_y_abs,
        x=inner_x,
        width=inner_width,
        enabled=enabled,
    )
    _render_appearance_slider_row(
        plotter,
        session,
        title="Edge Thickness",
        option="edge",
        center_y=edge_y_abs,
        x=inner_x,
        width=inner_width,
        enabled=enabled,
    )


def _graph_preview_slider_callback(
    plotter: Any,
    session: GraphViewerSession,
    *,
    option: Literal["node", "edge"],
    pv_module: Any | None = None,
) -> tuple[Any, dict[str, bool]]:
    state = {"enabled": False}

    def _callback(value: float) -> None:
        if not state["enabled"]:
            return
        _commit_graph_preview_value(plotter, session, option=option, value=value, pv_module=pv_module)

    return _callback, state


def _commit_graph_preview_value(
    plotter: Any,
    session: GraphViewerSession,
    *,
    option: Literal["node", "edge"],
    value: float,
    pv_module: Any | None = None,
) -> bool:
    if session.active_kind != "graphml":
        return False
    if option == "node":
        next_value = _clamp_preview_value(float(value), NODE_SIZE_RANGE)
        if np.isclose(float(session.preview_node_size), next_value):
            return False
        session.set_preview_node_size(next_value)
    else:
        next_value = _clamp_preview_value(float(value), EDGE_THICKNESS_RANGE)
        if np.isclose(float(session.preview_edge_thickness), next_value):
            return False
        session.set_preview_edge_thickness(next_value)
    refresh_active_graph(plotter, session, pv_module=pv_module)
    return True


def render_tools_scrollbar(plotter: Any, session: GraphViewerSession) -> None:
    geometry = _tools_scrollbar_geometry(plotter, session)
    if geometry is None:
        return
    panel_x, panel_top, panel_bottom = _tools_panel_geometry(plotter)
    track_x = panel_x + _tools_panel_width(plotter) - TOOLS_PANEL_PADDING - TOOLS_SCROLLBAR_WIDTH
    track_y = panel_bottom + TOOLS_PANEL_PADDING
    track_height = panel_top - panel_bottom - 2 * TOOLS_PANEL_PADDING
    session.tools_panel_actors.append(
        _add_overlay_rect(
            plotter,
            x=track_x,
            y=track_y,
            width=TOOLS_SCROLLBAR_WIDTH,
            height=track_height,
            color=(0.08, 0.11, 0.15),
            opacity=0.74,
        )
    )
    thumb_x, thumb_y, thumb_width, thumb_height = geometry
    session.tools_panel_actors.append(
        _add_overlay_rect(
            plotter,
            x=thumb_x,
            y=thumb_y,
            width=thumb_width,
            height=thumb_height,
            color=(0.55, 0.62, 0.70),
            opacity=0.98,
        )
    )


def _clamp_preview_value(value: float, bounds: tuple[float, float]) -> float:
    return float(round(min(max(value, bounds[0]), bounds[1]), 10))


def render_tools_panel(plotter: Any, session: GraphViewerSession, *, include_sliders: bool = True) -> None:
    """Render the always-visible right-side tool panel and its current controls."""
    _clamp_tools_scroll(plotter, session)
    _remove_actor_list(plotter, session.tools_panel_actors)

    panel_x, panel_top, panel_bottom = _tools_panel_geometry(plotter)
    _window_width, window_height = _plotter_window_size(plotter)
    session.tools_panel_actors.append(
        _add_overlay_rect(
            plotter,
            x=panel_x,
            y=0,
            width=_tools_panel_width(plotter),
            height=window_height,
            color=(0.12, 0.16, 0.21),
            opacity=1.0,
        )
    )
    render_command_buttons(plotter, session)
    render_interactive_controls(plotter, session)
    _remove_graph_sliders(plotter, session)
    if include_sliders:
        render_graph_sliders(plotter, session)
    render_tools_scrollbar(plotter, session)
    render_open_dropdown_menus(plotter, session)


def add_graph_viewer_controls(plotter: Any, session: GraphViewerSession, *, pv_module: Any | None = None) -> None:
    """Add pure-PyVista controls for file/session management and appearance preview."""
    _ensure_overlay_renderer(plotter, session)
    apply_view_layout(plotter, session)
    render_view_headers(plotter, session)
    render_tools_panel(plotter, session)
    render_file_panel(plotter, session)
    install_ui_mouse_observers(plotter, session, pv_module=pv_module)


def _show_interactive_plotter(plotter: Any, session: GraphViewerSession) -> None:
    """Map the desktop window before placing right-aligned overlay controls."""
    plotter.show(interactive_update=True, auto_close=False)
    interactor = getattr(plotter, "iren", None)
    if interactor is not None and hasattr(interactor, "process_events"):
        interactor.process_events()
    render_tools_panel(plotter, session)
    render_file_panel(plotter, session)
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
