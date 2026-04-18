"""PySide6-based GraphML viewer for 3D vessel graphs."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import importlib.util
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Callable, Sequence

import igraph as ig
import numpy as np


class GraphVisualizationError(RuntimeError):
    """Raised when a graph cannot be prepared or displayed."""


@dataclass(slots=True)
class GraphVisualizationData:
    """Prepared 3D graph data ready for rendering."""

    node_positions: np.ndarray
    edge_positions: np.ndarray
    node_count: int
    edge_count: int
    source_path: str
    render_warnings: tuple[str, ...] = ()


@dataclass(slots=True)
class GraphVisualizationOptions:
    """User-configurable graph appearance."""

    edge_thickness: float = 2.0
    node_size: float = 6.0
    window_title: str = "SkelHub Graph Viewer"


@dataclass(slots=True)
class GraphViewerSessionEntry:
    """One loaded GraphML file tracked in the current viewer session."""

    file_key: str
    source_path: str
    graph_data: GraphVisualizationData


@dataclass(slots=True)
class _SceneMetrics:
    center: np.ndarray
    span: float
    bounding_radius: float
    camera_distance: float
    near_plane: float
    far_plane: float
    node_radius: float
    edge_radius: float


class _MouseCameraControllerProtocol:
    """Minimal protocol for scene-specific camera interaction."""

    def set_scene_metrics(self, metrics: _SceneMetrics) -> None:
        raise NotImplementedError


@dataclass(slots=True)
class GraphSceneDiagnostics:
    """Diagnostics describing how a graph was fit into the viewer scene."""

    source_path: str
    node_count: int
    edge_count: int
    coordinate_min: np.ndarray
    coordinate_max: np.ndarray
    centroid: np.ndarray
    fit_center: np.ndarray
    bounding_radius: float
    camera_position: np.ndarray
    near_plane: float
    far_plane: float
    aspect_ratio: float
    warnings: tuple[str, ...]


@dataclass(slots=True)
class GraphSceneBuildStats:
    """Stats describing the actual renderable entities created for the active scene."""

    source_path: str
    node_count: int
    edge_count: int
    node_entities_built: int
    edge_entities_built: int


@dataclass(slots=True)
class _QtModules:
    QtCore: Any
    QtGui: Any
    QtWidgets: Any
    Qt3DCore: Any
    Qt3DExtras: Any
    Qt3DRender: Any
    QEntity: Any
    QTransform: Any
    QPointLight: Any
    QPhongMaterial: Any
    QSphereMesh: Any
    QCylinderMesh: Any
    Qt3DWindow: Any


class GraphViewerSession:
    """Session state for loaded GraphML files and the active display."""

    def __init__(
        self,
        loader: Callable[[str | Path], GraphVisualizationData] | None = None,
    ) -> None:
        self._loader = load_graph_visualization_data if loader is None else loader
        self._entries: dict[str, GraphViewerSessionEntry] = {}
        self._active_file_key: str | None = None

    @staticmethod
    def _normalize_path(path: str | Path) -> str:
        return str(Path(path).expanduser().resolve())

    @property
    def entries(self) -> list[GraphViewerSessionEntry]:
        return list(self._entries.values())

    @property
    def active_entry(self) -> GraphViewerSessionEntry | None:
        if self._active_file_key is None:
            return None
        return self._entries.get(self._active_file_key)

    def contains_path(self, path: str | Path) -> bool:
        return self._normalize_path(path) in self._entries

    def load_file(self, path: str | Path) -> tuple[GraphViewerSessionEntry, bool]:
        file_key = self._normalize_path(path)
        existing = self._entries.get(file_key)
        if existing is not None:
            self._active_file_key = file_key
            return existing, False

        graph_data = self._loader(file_key)
        entry = GraphViewerSessionEntry(
            file_key=file_key,
            source_path=file_key,
            graph_data=graph_data,
        )
        self._entries[file_key] = entry
        self._active_file_key = file_key
        return entry, True

    def set_active_file(self, file_key: str) -> GraphViewerSessionEntry:
        if file_key not in self._entries:
            raise GraphVisualizationError(f"GraphML file is not loaded in this session: {file_key}")
        self._active_file_key = file_key
        return self._entries[file_key]

    def unload_active_file(self) -> GraphViewerSessionEntry | None:
        if self._active_file_key is None:
            return None

        active_keys = list(self._entries)
        active_index = active_keys.index(self._active_file_key)
        removed = self._entries.pop(self._active_file_key)

        if self._entries:
            remaining_keys = list(self._entries)
            next_index = min(active_index, len(remaining_keys) - 1)
            self._active_file_key = remaining_keys[next_index]
        else:
            self._active_file_key = None

        return removed


class _GraphSceneController:
    """Handle scene creation and active graph display switching."""

    def __init__(self, window: Any, qt: _QtModules, options: GraphVisualizationOptions) -> None:
        self._window = window
        self._qt = qt
        self._options = options
        self._root_entity: Any | None = None

    def show_graph(
        self,
        graph_data: GraphVisualizationData | None,
    ) -> tuple[GraphSceneDiagnostics | None, GraphSceneBuildStats | None]:
        if graph_data is None:
            root_entity = _build_empty_scene(self._window, self._qt, self._options)
            diagnostics = None
            build_stats = None
        else:
            root_entity = _build_scene(self._window, graph_data, self._options, self._qt)
            diagnostics = _build_scene_diagnostics(self._window, graph_data, self._options)
            build_stats = _build_scene_build_stats(graph_data)

        previous_root = self._root_entity
        self._window.setRootEntity(root_entity)
        self._root_entity = root_entity

        if previous_root is not None and previous_root is not root_entity:
            previous_root.setParent(None)
            if hasattr(previous_root, "deleteLater"):
                previous_root.deleteLater()

        return diagnostics, build_stats

    def refit_graph(
        self,
        graph_data: GraphVisualizationData | None,
    ) -> tuple[GraphSceneDiagnostics | None, GraphSceneBuildStats | None]:
        if graph_data is None:
            metrics = _compute_scene_metrics(
                np.empty((0, 3), dtype=float),
                node_size=self._options.node_size,
                edge_thickness=self._options.edge_thickness,
                aspect_ratio=_camera_aspect_ratio(self._window),
            )
            _configure_camera(self._window, self._qt, np.zeros(3, dtype=float), metrics)
            return None, None

        metrics = _compute_scene_metrics(
            graph_data.node_positions,
            node_size=self._options.node_size,
            edge_thickness=self._options.edge_thickness,
            aspect_ratio=_camera_aspect_ratio(self._window),
        )
        _configure_camera(self._window, self._qt, np.zeros(3, dtype=float), metrics)
        diagnostics = _build_scene_diagnostics(self._window, graph_data, self._options)
        build_stats = _build_scene_build_stats(graph_data)
        return diagnostics, build_stats

class _GraphViewerWindow:
    """Qt main window for the interactive graph viewer."""

    def __init__(
        self,
        *,
        qt: _QtModules,
        session: GraphViewerSession,
        options: GraphVisualizationOptions,
    ) -> None:
        self._qt = qt
        self._session = session
        self._options = options
        self._main_window = qt.QtWidgets.QMainWindow()
        self._main_window.resize(1200, 800)

        self._scene_window = qt.Qt3DWindow()
        _configure_frame_graph(self._scene_window, qt)
        self._scene_container = qt.QtWidgets.QWidget.createWindowContainer(self._scene_window)
        self._scene_container.setFocusPolicy(qt.QtCore.Qt.FocusPolicy.StrongFocus)
        self._main_window.setCentralWidget(self._scene_container)
        self._status_bar = self._main_window.statusBar()
        self._file_menu = qt.QtWidgets.QMenu("File", self._main_window)
        self._install_toolbar()
        self._stabilization_timer = qt.QtCore.QTimer(self._main_window)
        self._stabilization_timer.setSingleShot(True)
        self._stabilization_timer.timeout.connect(self._stabilize_scene_after_load)
        self._mouse_camera_controller = _create_mouse_camera_controller(
            container=self._scene_container,
            window=self._scene_window,
            qt=qt,
        )

        self._scene_controller = _GraphSceneController(self._scene_window, qt, options)
        self._sync_view_from_session(status_message=None)

    def _install_toolbar(self) -> None:
        toolbar = self._main_window.addToolBar("File")
        toolbar.setMovable(False)

        file_button = self._qt.QtWidgets.QToolButton(self._main_window)
        file_button.setText("File")
        if hasattr(self._qt.QtWidgets.QToolButton, "ToolButtonPopupMode"):
            popup_mode = self._qt.QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup
        else:  # pragma: no cover - compatibility fallback
            popup_mode = self._qt.QtWidgets.QToolButton.InstantPopup
        file_button.setPopupMode(popup_mode)
        file_button.setMenu(self._file_menu)
        toolbar.addWidget(file_button)

        fit_action = toolbar.addAction("Fit Graph")
        fit_action.triggered.connect(self._fit_active_graph)

    def _loaded_file_action_label(self, entry: GraphViewerSessionEntry) -> str:
        path = Path(entry.source_path)
        return f"{path.name} - {path.parent}"

    def _set_window_title(self) -> None:
        active_entry = self._session.active_entry
        if active_entry is None:
            title = f"{self._options.window_title} - No file loaded"
            self._main_window.setWindowTitle(title)
            return

        active_name = Path(active_entry.source_path).name
        title = f"{self._options.window_title} - {active_name}"
        self._main_window.setWindowTitle(title)

    def _show_status(self, message: str | None) -> None:
        if message:
            self._status_bar.showMessage(message, 5000)
        else:
            self._status_bar.clearMessage()

    def _refresh_file_menu(self) -> None:
        self._file_menu.clear()

        load_action = self._file_menu.addAction("Load GraphML...")
        load_action.triggered.connect(self._choose_graph_file)

        unload_action = self._file_menu.addAction("Unload Current")
        unload_action.setEnabled(self._session.active_entry is not None)
        unload_action.triggered.connect(self._unload_active_graph)

        fit_action = self._file_menu.addAction("Fit Graph")
        fit_action.setEnabled(self._session.active_entry is not None)
        fit_action.triggered.connect(self._fit_active_graph)

        self._file_menu.addSeparator()
        entries = self._session.entries
        if not entries:
            empty_action = self._file_menu.addAction("No loaded files")
            empty_action.setEnabled(False)
            return

        for entry in entries:
            action = self._file_menu.addAction(self._loaded_file_action_label(entry))
            action.setCheckable(True)
            action.setChecked(self._session.active_entry is not None and entry.file_key == self._session.active_entry.file_key)
            action.setToolTip(entry.source_path)
            action.triggered.connect(
                lambda checked=False, file_key=entry.file_key: self._activate_loaded_graph(file_key)
            )

    def _sync_view_from_session(self, *, status_message: str | None, rebuild_scene: bool = True) -> None:
        active_entry = self._session.active_entry
        active_graph = None if active_entry is None else active_entry.graph_data
        if rebuild_scene:
            diagnostics, build_stats = self._scene_controller.show_graph(active_graph)
        else:
            diagnostics, build_stats = self._scene_controller.refit_graph(active_graph)
        metrics = _compute_scene_metrics(
            np.empty((0, 3), dtype=float) if active_graph is None else active_graph.node_positions,
            node_size=self._options.node_size,
            edge_thickness=self._options.edge_thickness,
            aspect_ratio=_camera_aspect_ratio(self._scene_window),
        )
        self._mouse_camera_controller.set_scene_metrics(metrics)
        self._set_window_title()
        self._refresh_file_menu()
        if diagnostics is None:
            self._show_status(status_message)
            return

        print(_format_scene_diagnostics(diagnostics))
        if build_stats is not None:
            print(_format_scene_build_stats(build_stats))
        self._show_status(_format_scene_status(diagnostics, build_stats=build_stats, prefix=status_message))

    def _schedule_scene_stabilization(self) -> None:
        if self._session.active_entry is None:
            self._stabilization_timer.stop()
            return
        self._stabilization_timer.start(0)

    def _stabilize_scene_after_load(self) -> None:
        active_entry = self._session.active_entry
        if active_entry is None:
            return

        # Rebuild once after the event loop starts so Qt3D can realize the complete scene
        # with the final window size and renderer state.
        self._sync_view_from_session(
            status_message=f"Graph view stabilized: {Path(active_entry.source_path).name}",
            rebuild_scene=True,
        )

    def _choose_graph_file(self) -> None:
        selected_path, _ = self._qt.QtWidgets.QFileDialog.getOpenFileName(
            self._main_window,
            "Load GraphML File",
            "",
            "GraphML Files (*.graphml);;All Files (*)",
        )
        if not selected_path:
            return
        self._load_graph_file(selected_path)

    def _show_error(self, error: GraphVisualizationError) -> None:
        self._qt.QtWidgets.QMessageBox.critical(self._main_window, "SkelHub Graph Viewer", str(error))

    def _show_renderability_warning(self, graph_data: GraphVisualizationData) -> None:
        if not graph_data.render_warnings:
            return

        warning_text = "\n".join(f"- {warning}" for warning in graph_data.render_warnings)
        self._qt.QtWidgets.QMessageBox.warning(
            self._main_window,
            "SkelHub Graph Viewer Warning",
            f"GraphML file loaded with renderability warnings:\n{warning_text}",
        )

    def _load_graph_file(self, path: str | Path) -> None:
        try:
            entry, is_new_file = self._session.load_file(path)
        except GraphVisualizationError as exc:
            self._show_error(exc)
            return

        file_name = Path(entry.source_path).name
        if is_new_file:
            status_message = f"Loaded GraphML file: {file_name}"
        else:
            status_message = f"GraphML file already loaded; switched to: {file_name}"
        self._sync_view_from_session(status_message=status_message)
        self._schedule_scene_stabilization()
        self._show_renderability_warning(entry.graph_data)

    def _unload_active_graph(self) -> None:
        removed = self._session.unload_active_file()
        if removed is None:
            self._sync_view_from_session(status_message="No GraphML file is currently loaded.")
            return

        next_active = self._session.active_entry
        if next_active is None:
            status_message = f"Unloaded {Path(removed.source_path).name}; no GraphML files remain loaded."
        else:
            status_message = (
                f"Unloaded {Path(removed.source_path).name}; now showing {Path(next_active.source_path).name}."
            )
        self._sync_view_from_session(status_message=status_message)
        if next_active is not None:
            self._schedule_scene_stabilization()

    def _activate_loaded_graph(self, file_key: str) -> None:
        try:
            entry = self._session.set_active_file(file_key)
        except GraphVisualizationError as exc:
            self._show_error(exc)
            return

        self._sync_view_from_session(
            status_message=f"Now showing GraphML file: {Path(entry.source_path).name}"
        )
        self._schedule_scene_stabilization()
        self._show_renderability_warning(entry.graph_data)

    def _fit_active_graph(self) -> None:
        active_entry = self._session.active_entry
        if active_entry is None:
            self._show_status("No GraphML file is currently loaded.")
            return

        self._sync_view_from_session(
            status_message=f"Re-fit graph view: {Path(active_entry.source_path).name}",
            rebuild_scene=False,
        )

    def show(self) -> None:
        self._main_window.show()
        self._schedule_scene_stabilization()
        active_entry = self._session.active_entry
        if active_entry is not None:
            self._show_renderability_warning(active_entry.graph_data)


def _is_module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _missing_optional_dependency_names() -> list[str]:
    dependency_specs = {
        "PySide6": "PySide6",
    }
    missing: list[str] = []
    for package_name, module_name in dependency_specs.items():
        if not _is_module_available(module_name):
            missing.append(package_name)
    return missing


def _skelhub_launch_hint() -> str | None:
    argv0 = Path(sys.argv[0]).name if sys.argv else ""
    if argv0.startswith("skelhub"):
        return str(Path(sys.argv[0]).resolve())

    console_script = shutil.which("skelhub")
    if console_script:
        return console_script
    return None


def _looks_like_qt_runtime_conflict(exc: BaseException) -> bool:
    message = str(exc)
    return any(
        marker in message
        for marker in (
            "Qt_6_PRIVATE_API",
            "undefined symbol",
            "libQt6",
            "could not load Qt platform plugin",
        )
    )


def _build_optional_dependency_error(exc: ImportError | OSError) -> GraphVisualizationError:
    missing = _missing_optional_dependency_names()
    launch_path = _skelhub_launch_hint()
    message_parts = [
        "PySide6 graph visualization could not be initialized.",
        f"Active interpreter: {sys.executable}.",
    ]

    if launch_path:
        message_parts.append(f"Detected `skelhub` launch path: {launch_path}.")

    if missing:
        message_parts.append(
            "Missing optional packages: "
            f"{', '.join(missing)}. Install them into this same interpreter with "
            "`python -m pip install -e .[graphviz]`."
        )
    else:
        message_parts.append(
            "The optional graph viewer packages appear discoverable, but importing Qt failed at runtime."
        )
        if _looks_like_qt_runtime_conflict(exc):
            message_parts.append(
                "This looks like a Qt binary/library mismatch. "
                "Errors mentioning `Qt_6_PRIVATE_API`, `undefined symbol`, or `libQt6*.so` usually mean "
                "that `LD_LIBRARY_PATH` or environment modules are forcing incompatible Qt shared libraries."
            )
            ld_library_path = os.environ.get("LD_LIBRARY_PATH")
            if ld_library_path:
                message_parts.append(f"Current LD_LIBRARY_PATH: {ld_library_path}.")
        else:
            message_parts.append(
                "Check that `python -m pip install -e .[graphviz]` and "
                "`python -m skelhub graphviz ...` use the same `python` interpreter."
            )

    message_parts.append(f"Original import error: {exc}")
    return GraphVisualizationError(" ".join(message_parts))


def _viewer_troubleshooting_enabled() -> bool:
    return os.environ.get("SKELHUB_GRAPH_VIEWER_TROUBLESHOOT", "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_gl_string(gl_get_string: Callable[[int], Any] | None, enum_value: int) -> str | None:
    if gl_get_string is None:
        return None
    try:
        raw_value = gl_get_string(enum_value)
    except Exception:  # pragma: no cover - backend-specific runtime failure
        return None
    if raw_value is None:
        return None
    if isinstance(raw_value, bytes):
        return raw_value.decode("utf-8", errors="replace")
    return str(raw_value)


def _collect_runtime_diagnostics(qt: _QtModules, window: Any | None = None) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "python_executable": sys.executable,
        "qt_version": qt.QtCore.qVersion() if hasattr(qt.QtCore, "qVersion") else "unknown",
        "pyside_version": getattr(qt.QtCore, "__version__", "unknown"),
        "qt_opengl_env": os.environ.get("QT_OPENGL", ""),
        "qsg_rhi_backend_env": os.environ.get("QSG_RHI_BACKEND", ""),
        "qt_quick_backend_env": os.environ.get("QT_QUICK_BACKEND", ""),
        "qt_xcb_gl_integration_env": os.environ.get("QT_XCB_GL_INTEGRATION", ""),
        "ld_library_path": os.environ.get("LD_LIBRARY_PATH", ""),
        "rhi_opengl_fallback_hint": bool(
            os.environ.get("QT_OPENGL", "").strip()
            or os.environ.get("QSG_RHI_BACKEND", "").strip()
        ),
    }

    current_context = None
    qopengl_context = getattr(qt.QtGui, "QOpenGLContext", None)
    if qopengl_context is not None and hasattr(qopengl_context, "currentContext"):
        try:
            current_context = qopengl_context.currentContext()
        except Exception:  # pragma: no cover - backend-specific runtime failure
            current_context = None

    diagnostics["current_context_available"] = current_context is not None

    if current_context is not None:
        functions = getattr(current_context, "functions", lambda: None)()
        gl_get_string = getattr(functions, "glGetString", None) if functions is not None else None
        diagnostics["opengl_vendor"] = _safe_gl_string(gl_get_string, 0x1F00)
        diagnostics["opengl_renderer"] = _safe_gl_string(gl_get_string, 0x1F01)
        diagnostics["opengl_version"] = _safe_gl_string(gl_get_string, 0x1F02)
    else:
        diagnostics["opengl_vendor"] = None
        diagnostics["opengl_renderer"] = None
        diagnostics["opengl_version"] = None

    if window is not None:
        diagnostics["window_aspect_ratio"] = _camera_aspect_ratio(window)

    return diagnostics


def _format_runtime_diagnostics(diagnostics: dict[str, Any], *, phase: str) -> str:
    return (
        f"graph viewer runtime diagnostics ({phase}): "
        f"python={diagnostics.get('python_executable')}, "
        f"qt_version={diagnostics.get('qt_version')}, "
        f"pyside_version={diagnostics.get('pyside_version')}, "
        f"current_context_available={diagnostics.get('current_context_available')}, "
        f"opengl_vendor={diagnostics.get('opengl_vendor')}, "
        f"opengl_renderer={diagnostics.get('opengl_renderer')}, "
        f"opengl_version={diagnostics.get('opengl_version')}, "
        f"rhi_opengl_fallback_hint={diagnostics.get('rhi_opengl_fallback_hint')}, "
        f"qt_opengl_env={diagnostics.get('qt_opengl_env')}, "
        f"qsg_rhi_backend_env={diagnostics.get('qsg_rhi_backend_env')}, "
        f"qt_quick_backend_env={diagnostics.get('qt_quick_backend_env')}, "
        f"qt_xcb_gl_integration_env={diagnostics.get('qt_xcb_gl_integration_env')}, "
        f"window_aspect_ratio={diagnostics.get('window_aspect_ratio')}, "
        f"ld_library_path={diagnostics.get('ld_library_path')}"
    )


def _resolve_qt_symbol(module: Any, namespace_name: str, symbol_name: str) -> Any:
    symbol = getattr(module, symbol_name, None)
    if symbol is not None:
        return symbol

    namespace = getattr(module, namespace_name, None)
    if namespace is not None:
        symbol = getattr(namespace, symbol_name, None)
        if symbol is not None:
            return symbol

    raise AttributeError(
        f"module '{module.__name__}' has no attribute '{symbol_name}'"
    )


def _import_qt_modules() -> _QtModules:
    try:
        QtCore = importlib.import_module("PySide6.QtCore")
        QtGui = importlib.import_module("PySide6.QtGui")
        QtWidgets = importlib.import_module("PySide6.QtWidgets")
        Qt3DCore = importlib.import_module("PySide6.Qt3DCore")
        Qt3DExtras = importlib.import_module("PySide6.Qt3DExtras")
        Qt3DRender = importlib.import_module("PySide6.Qt3DRender")
    except (ImportError, OSError) as exc:
        raise _build_optional_dependency_error(exc) from exc
    try:
        QEntity = _resolve_qt_symbol(Qt3DCore, "Qt3DCore", "QEntity")
        QTransform = _resolve_qt_symbol(Qt3DCore, "Qt3DCore", "QTransform")
        QPointLight = _resolve_qt_symbol(Qt3DRender, "Qt3DRender", "QPointLight")
        QPhongMaterial = _resolve_qt_symbol(Qt3DExtras, "Qt3DExtras", "QPhongMaterial")
        QSphereMesh = _resolve_qt_symbol(Qt3DExtras, "Qt3DExtras", "QSphereMesh")
        QCylinderMesh = _resolve_qt_symbol(Qt3DExtras, "Qt3DExtras", "QCylinderMesh")
        Qt3DWindow = _resolve_qt_symbol(Qt3DExtras, "Qt3DExtras", "Qt3DWindow")
    except AttributeError as exc:
        raise _build_optional_dependency_error(ImportError(str(exc))) from exc

    return _QtModules(
        QtCore=QtCore,
        QtGui=QtGui,
        QtWidgets=QtWidgets,
        Qt3DCore=Qt3DCore,
        Qt3DExtras=Qt3DExtras,
        Qt3DRender=Qt3DRender,
        QEntity=QEntity,
        QTransform=QTransform,
        QPointLight=QPointLight,
        QPhongMaterial=QPhongMaterial,
        QSphereMesh=QSphereMesh,
        QCylinderMesh=QCylinderMesh,
        Qt3DWindow=Qt3DWindow,
    )


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


def _positions_from_v_coords(graph: ig.Graph) -> np.ndarray | None:
    if "v_coords" not in graph.vs.attribute_names():
        return None

    try:
        coords = np.asarray(graph.vs["v_coords"], dtype=float)
    except (TypeError, ValueError) as exc:
        raise GraphVisualizationError("GraphML node attribute 'v_coords' must contain numeric coordinates.") from exc

    if coords.shape != (graph.vcount(), 3):
        raise GraphVisualizationError(
            "GraphML node attribute 'v_coords' must contain one 3D coordinate triplet per node."
        )

    return coords


def _extract_node_positions(graph: ig.Graph) -> np.ndarray:
    for attribute_names in (("X", "Y", "Z"), ("x", "y", "z")):
        positions = _positions_from_xyz(graph, attribute_names)
        if positions is not None:
            return positions

    positions = _positions_from_v_coords(graph)
    if positions is not None:
        return positions

    raise GraphVisualizationError(
        "GraphML file does not contain renderable 3D coordinates. "
        "Expected node attributes 'X', 'Y', 'Z' as written by SkelHub GraphML export."
    )


def _build_edge_positions(graph: ig.Graph, node_positions: np.ndarray) -> np.ndarray:
    if graph.ecount() == 0:
        return np.empty((0, 3), dtype=float)

    edge_positions = np.empty((graph.ecount() * 2, 3), dtype=float)
    for edge_index, edge in enumerate(graph.es):
        source_index, target_index = edge.tuple
        edge_positions[2 * edge_index] = node_positions[source_index]
        edge_positions[2 * edge_index + 1] = node_positions[target_index]
    return edge_positions


def _renderability_warnings(node_positions: np.ndarray, edge_count: int) -> tuple[str, ...]:
    if node_positions.shape[0] == 0:
        raise GraphVisualizationError("GraphML file does not contain any nodes to render.")

    positions = np.asarray(node_positions, dtype=float)
    if not np.isfinite(positions).all():
        raise GraphVisualizationError("GraphML file contains non-finite node coordinates and cannot be rendered.")

    warnings: list[str] = []
    raw_span = float(np.ptp(positions, axis=0).max()) if positions.size else 0.0
    max_abs_coordinate = float(np.abs(positions).max()) if positions.size else 0.0

    if edge_count == 0:
        warnings.append("Graph contains zero edges; only isolated nodes will be renderable.")
    if raw_span <= 1e-6:
        warnings.append("Graph spatial extent is near zero; geometry may collapse into an indistinguishable point.")
    if max_abs_coordinate >= 1e6:
        warnings.append("Graph coordinates are very large in magnitude; camera fitting may be difficult.")

    return tuple(warnings)


def load_graph_visualization_data(input_path: str | Path) -> GraphVisualizationData:
    """Load GraphML and prepare positions for rendering."""
    graph_path = Path(input_path)
    if not graph_path.is_file():
        raise GraphVisualizationError(f"GraphML input does not exist: {graph_path}")

    try:
        graph = ig.Graph.Read_GraphML(str(graph_path))
    except Exception as exc:  # pragma: no cover - igraph raises several concrete types
        raise GraphVisualizationError(f"Failed to load GraphML file '{graph_path}': {exc}") from exc

    node_positions = _extract_node_positions(graph)
    edge_positions = _build_edge_positions(graph, node_positions)
    render_warnings = _renderability_warnings(node_positions, graph.ecount())
    return GraphVisualizationData(
        node_positions=node_positions,
        edge_positions=edge_positions,
        node_count=graph.vcount(),
        edge_count=graph.ecount(),
        source_path=str(graph_path),
        render_warnings=render_warnings,
    )


def _graph_span(node_positions: np.ndarray) -> float:
    if node_positions.size == 0:
        return 1.0
    span = float(np.ptp(node_positions, axis=0).max())
    return span if span > 0 else 1.0


def _graph_bounds(node_positions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if node_positions.size == 0:
        zero = np.zeros(3, dtype=float)
        return zero, zero

    positions = np.asarray(node_positions, dtype=float)
    return positions.min(axis=0), positions.max(axis=0)


def _graph_centroid(node_positions: np.ndarray) -> np.ndarray:
    if node_positions.size == 0:
        return np.zeros(3, dtype=float)
    return np.asarray(node_positions.mean(axis=0), dtype=float)


def _graph_center(node_positions: np.ndarray) -> np.ndarray:
    if node_positions.size == 0:
        return np.zeros(3, dtype=float)
    coordinate_min, coordinate_max = _graph_bounds(node_positions)
    return np.asarray((coordinate_min + coordinate_max) * 0.5, dtype=float)


def _graph_bounding_radius(node_positions: np.ndarray, center: np.ndarray) -> float:
    if node_positions.size == 0:
        return 1.0
    offsets = np.asarray(node_positions, dtype=float) - center
    radius = float(np.linalg.norm(offsets, axis=1).max())
    return radius if radius > 0 else 1.0


def _size_to_world_radius(span: float, size: float) -> float:
    return max(size * 0.12, span * 0.025, 0.35)


def _edge_radius(span: float, thickness: float) -> float:
    return max(thickness * 0.08, span * 0.0125, 0.14)


def _compute_scene_metrics(
    node_positions: np.ndarray,
    *,
    node_size: float,
    edge_thickness: float,
    aspect_ratio: float,
) -> _SceneMetrics:
    center = _graph_center(node_positions)
    span = _graph_span(node_positions)
    bounding_radius = _graph_bounding_radius(node_positions, center)
    scene_radius = max(bounding_radius, span * 0.5, 1.0)
    half_vertical_fov = np.deg2rad(45.0 * 0.5)
    half_horizontal_fov = np.arctan(np.tan(half_vertical_fov) * max(aspect_ratio, 0.1))
    limiting_half_fov = min(half_vertical_fov, half_horizontal_fov)
    camera_distance = max(scene_radius / np.sin(limiting_half_fov) * 1.15, scene_radius * 2.6)
    near_plane = max(scene_radius * 0.05, 0.1)
    far_plane = max(camera_distance + scene_radius * 6.0, near_plane + 100.0)

    return _SceneMetrics(
        center=center,
        span=span,
        bounding_radius=bounding_radius,
        camera_distance=camera_distance,
        near_plane=near_plane,
        far_plane=far_plane,
        node_radius=_size_to_world_radius(span, node_size),
        edge_radius=_edge_radius(span, edge_thickness),
    )


def _scene_entity_counts(graph_data: GraphVisualizationData) -> tuple[int, int]:
    return graph_data.node_count, graph_data.edge_count


def _built_scene_entity_counts(graph_data: GraphVisualizationData) -> tuple[int, int]:
    node_entities_built = int(graph_data.node_positions.shape[0])
    edge_entities_built = 0
    for edge_index in range(0, graph_data.edge_positions.shape[0], 2):
        start = graph_data.edge_positions[edge_index]
        end = graph_data.edge_positions[edge_index + 1]
        if float(np.linalg.norm(end - start)) > 0.0:
            edge_entities_built += 1
    return node_entities_built, edge_entities_built


def _center_graph_positions(
    graph_data: GraphVisualizationData,
    center: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    if graph_data.node_positions.size == 0:
        centered_nodes = np.empty((0, 3), dtype=float)
    else:
        centered_nodes = np.asarray(graph_data.node_positions, dtype=float) - center

    if graph_data.edge_positions.size == 0:
        centered_edges = np.empty((0, 3), dtype=float)
    else:
        centered_edges = np.asarray(graph_data.edge_positions, dtype=float) - center

    return centered_nodes, centered_edges


def _qvector3d_from_array(QtGui: Any, values: Sequence[float]) -> Any:
    return QtGui.QVector3D(float(values[0]), float(values[1]), float(values[2]))


def _camera_aspect_ratio(window: Any) -> float:
    width = 0
    height = 0

    for getter_name in ("width",):
        getter = getattr(window, getter_name, None)
        if callable(getter):
            width = int(getter())
            break

    for getter_name in ("height",):
        getter = getattr(window, getter_name, None)
        if callable(getter):
            height = int(getter())
            break

    if width <= 0 or height <= 0:
        size_getter = getattr(window, "size", None)
        if callable(size_getter):
            size = size_getter()
            width_method = getattr(size, "width", None)
            height_method = getattr(size, "height", None)
            if callable(width_method):
                width = int(width_method())
            if callable(height_method):
                height = int(height_method())

    if width <= 0 or height <= 0:
        return 16.0 / 9.0

    return max(float(width) / float(height), 0.1)


def _camera_position(center: np.ndarray, metrics: _SceneMetrics) -> np.ndarray:
    view_direction = np.asarray([1.0, 0.6, 1.0], dtype=float)
    view_direction /= np.linalg.norm(view_direction)
    return np.asarray(
        center + (view_direction * metrics.camera_distance),
        dtype=float,
    )


def _build_scene_diagnostics(
    window: Any,
    graph_data: GraphVisualizationData,
    options: GraphVisualizationOptions,
) -> GraphSceneDiagnostics:
    coordinate_min, coordinate_max = _graph_bounds(graph_data.node_positions)
    centroid = _graph_centroid(graph_data.node_positions)
    metrics = _compute_scene_metrics(
        graph_data.node_positions,
        node_size=options.node_size,
        edge_thickness=options.edge_thickness,
        aspect_ratio=_camera_aspect_ratio(window),
    )
    origin = np.zeros(3, dtype=float)
    return GraphSceneDiagnostics(
        source_path=graph_data.source_path,
        node_count=graph_data.node_count,
        edge_count=graph_data.edge_count,
        coordinate_min=coordinate_min,
        coordinate_max=coordinate_max,
        centroid=centroid,
        fit_center=np.asarray(metrics.center, dtype=float),
        bounding_radius=metrics.bounding_radius,
        camera_position=_camera_position(origin, metrics),
        near_plane=metrics.near_plane,
        far_plane=metrics.far_plane,
        aspect_ratio=_camera_aspect_ratio(window),
        warnings=graph_data.render_warnings,
    )


def _build_scene_build_stats(graph_data: GraphVisualizationData) -> GraphSceneBuildStats:
    node_entities_built, edge_entities_built = _built_scene_entity_counts(graph_data)
    return GraphSceneBuildStats(
        source_path=graph_data.source_path,
        node_count=graph_data.node_count,
        edge_count=graph_data.edge_count,
        node_entities_built=node_entities_built,
        edge_entities_built=edge_entities_built,
    )


def _format_scene_status(
    diagnostics: GraphSceneDiagnostics,
    *,
    build_stats: GraphSceneBuildStats | None = None,
    prefix: str | None = None,
) -> str:
    message = (
        f"nodes={diagnostics.node_count}, edges={diagnostics.edge_count}, "
        f"radius={diagnostics.bounding_radius:.3f}, "
        f"clip=({diagnostics.near_plane:.3f}, {diagnostics.far_plane:.3f})"
    )
    if build_stats is not None:
        message = (
            f"{message}, node_entities={build_stats.node_entities_built}, "
            f"edge_entities={build_stats.edge_entities_built}"
        )
    if diagnostics.warnings:
        message = f"{message}, warnings={len(diagnostics.warnings)}"
    if prefix:
        return f"{prefix} | {message}"
    return message


def _format_scene_diagnostics(diagnostics: GraphSceneDiagnostics) -> str:
    return (
        f"graph scene diagnostics: file={diagnostics.source_path}, "
        f"nodes={diagnostics.node_count}, edges={diagnostics.edge_count}, "
        f"min={diagnostics.coordinate_min.tolist()}, max={diagnostics.coordinate_max.tolist()}, "
        f"centroid={diagnostics.centroid.tolist()}, fit_center={diagnostics.fit_center.tolist()}, "
        f"bounding_radius={diagnostics.bounding_radius:.6f}, "
        f"camera_position={diagnostics.camera_position.tolist()}, "
        f"near_plane={diagnostics.near_plane:.6f}, far_plane={diagnostics.far_plane:.6f}, "
        f"aspect_ratio={diagnostics.aspect_ratio:.6f}, "
        f"warnings={list(diagnostics.warnings)}"
    )


def _format_scene_build_stats(build_stats: GraphSceneBuildStats) -> str:
    return (
        f"graph scene build stats: file={build_stats.source_path}, "
        f"nodes={build_stats.node_count}, edges={build_stats.edge_count}, "
        f"node_entities_built={build_stats.node_entities_built}, "
        f"edge_entities_built={build_stats.edge_entities_built}"
    )


def _configure_camera(window: Any, qt: _QtModules, center: np.ndarray, metrics: _SceneMetrics) -> None:
    camera = window.camera()
    lens = camera.lens()
    lens.setPerspectiveProjection(45.0, _camera_aspect_ratio(window), metrics.near_plane, metrics.far_plane)
    camera.setPosition(_qvector3d_from_array(qt.QtGui, _camera_position(center, metrics)))
    camera.setViewCenter(_qvector3d_from_array(qt.QtGui, center))


def _configure_frame_graph(window: Any, qt: _QtModules) -> None:
    frame_graph = window.defaultFrameGraph()
    if hasattr(frame_graph, "setClearColor"):
        frame_graph.setClearColor(qt.QtGui.QColor(255, 255, 255))
    if hasattr(frame_graph, "setFrustumCullingEnabled"):
        frame_graph.setFrustumCullingEnabled(False)


def _configure_default_surface_format(qt: _QtModules) -> None:
    surface_format = qt.QtGui.QSurfaceFormat()
    if hasattr(qt.QtGui.QSurfaceFormat, "OpenGLContextProfile"):
        surface_format.setProfile(qt.QtGui.QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    elif hasattr(qt.QtGui.QSurfaceFormat, "CoreProfile"):  # pragma: no cover - compatibility fallback
        surface_format.setProfile(qt.QtGui.QSurfaceFormat.CoreProfile)
    surface_format.setVersion(3, 3)
    surface_format.setDepthBufferSize(24)
    surface_format.setStencilBufferSize(8)
    surface_format.setSamples(4)
    qt.QtGui.QSurfaceFormat.setDefaultFormat(surface_format)


def _create_mouse_camera_controller(container: Any, window: Any, qt: _QtModules) -> _MouseCameraControllerProtocol:
    class _MouseCameraController(qt.QtCore.QObject):
        """Single-source mouse interaction controller for the 3D camera."""

        _ROTATE_DEGREES_PER_PIXEL = 0.45
        _ZOOM_STEP_SCALE = 0.88

        def __init__(self) -> None:
            super().__init__(container)
            self._container = container
            self._window = window
            self._qt = qt
            self._active_button: Any | None = None
            self._last_pointer_pos: Any | None = None
            self._metrics = _compute_scene_metrics(
                np.empty((0, 3), dtype=float),
                node_size=6.0,
                edge_thickness=2.0,
                aspect_ratio=_camera_aspect_ratio(self._window),
            )

            self._container.installEventFilter(self)
            self._window.installEventFilter(self)

        def set_scene_metrics(self, metrics: _SceneMetrics) -> None:
            self._metrics = metrics

        def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802 - Qt API name
            event_type = event.type()
            mouse_button = self._qt.QtCore.Qt.MouseButton
            event_enum = self._qt.QtCore.QEvent.Type

            if event_type == event_enum.MouseButtonPress:
                if event.button() in (mouse_button.LeftButton, mouse_button.MiddleButton):
                    self._active_button = event.button()
                    self._last_pointer_pos = event.position()
                    event.accept()
                    return True

            if event_type == event_enum.MouseMove and self._active_button is not None and self._last_pointer_pos is not None:
                position = event.position()
                delta = position - self._last_pointer_pos
                self._last_pointer_pos = position

                if self._active_button == mouse_button.LeftButton:
                    self._rotate_camera(delta)
                    event.accept()
                    return True
                if self._active_button == mouse_button.MiddleButton:
                    self._pan_camera(delta)
                    event.accept()
                    return True

            if event_type == event_enum.MouseButtonRelease:
                if event.button() == self._active_button:
                    self._active_button = None
                    self._last_pointer_pos = None
                    event.accept()
                    return True

            if event_type == event_enum.Wheel:
                self._zoom_camera(event.angleDelta().y())
                event.accept()
                return True

            return super().eventFilter(watched, event)

        def _camera_basis(self) -> tuple[Any, Any, Any, float]:
            camera = self._window.camera()
            position = camera.position()
            view_center = camera.viewCenter()
            up_vector = camera.upVector().normalized()
            camera_offset = position - view_center
            distance = max(camera_offset.length(), self._minimum_camera_distance())
            forward = (view_center - position).normalized()
            right = self._qt.QtGui.QVector3D.crossProduct(forward, up_vector).normalized()
            return forward, right, up_vector, distance

        def _minimum_camera_distance(self) -> float:
            return max(self._metrics.bounding_radius * 0.15, self._metrics.span * 0.08, 0.25)

        def _rotate_camera(self, delta: Any) -> None:
            camera = self._window.camera()
            camera.panAboutViewCenter(-float(delta.x()) * self._ROTATE_DEGREES_PER_PIXEL)
            camera.tiltAboutViewCenter(-float(delta.y()) * self._ROTATE_DEGREES_PER_PIXEL)

        def _pan_camera(self, delta: Any) -> None:
            _, right, up_vector, distance = self._camera_basis()
            height = max(float(self._container.height()), 1.0)
            width = max(float(self._container.width()), 1.0)
            half_fov_radians = np.deg2rad(45.0 * 0.5)
            vertical_span = 2.0 * distance * float(np.tan(half_fov_radians))
            horizontal_span = vertical_span * (width / height)

            horizontal_shift = right * float(delta.x() * (horizontal_span / width))
            vertical_shift = up_vector * float(delta.y() * (vertical_span / height))
            translation = horizontal_shift + vertical_shift

            camera = self._window.camera()
            camera.setPosition(camera.position() + translation)
            camera.setViewCenter(camera.viewCenter() + translation)

        def _zoom_camera(self, wheel_delta_y: int) -> None:
            if wheel_delta_y == 0:
                return

            steps = float(wheel_delta_y) / 120.0
            scale = self._ZOOM_STEP_SCALE ** (-steps)

            camera = self._window.camera()
            view_center = camera.viewCenter()
            offset = camera.position() - view_center
            distance = max(offset.length(), self._minimum_camera_distance())
            direction = offset.normalized() if offset.lengthSquared() > 0 else self._qt.QtGui.QVector3D(1.0, 0.0, 0.0)
            new_distance = max(distance * scale, self._minimum_camera_distance())
            camera.setPosition(view_center + (direction * new_distance))

    return _MouseCameraController()


def _add_light(root_entity: Any, qt: _QtModules, center: np.ndarray, distance: float) -> None:
    light_entity = qt.QEntity(root_entity)
    point_light = qt.QPointLight(light_entity)
    point_light.setColor(qt.QtGui.QColor(255, 255, 255))
    point_light.setIntensity(1.6)

    light_transform = qt.QTransform(light_entity)
    light_transform.setTranslation(
        qt.QtGui.QVector3D(
            float(center[0] + distance),
            float(center[1] + distance),
            float(center[2] + distance),
        )
    )

    light_entity.addComponent(point_light)
    light_entity.addComponent(light_transform)


def _build_empty_scene(window: Any, qt: _QtModules, options: GraphVisualizationOptions) -> Any:
    root_entity = qt.QEntity()

    metrics = _compute_scene_metrics(
        np.empty((0, 3), dtype=float),
        node_size=options.node_size,
        edge_thickness=options.edge_thickness,
        aspect_ratio=_camera_aspect_ratio(window),
    )
    _configure_camera(window, qt, np.zeros(3, dtype=float), metrics)
    _add_light(root_entity, qt, np.zeros(3, dtype=float), metrics.camera_distance)
    return root_entity


def _build_scene(window: Any, graph_data: GraphVisualizationData, options: GraphVisualizationOptions, qt: _QtModules) -> Any:
    root_entity = qt.QEntity()

    metrics = _compute_scene_metrics(
        graph_data.node_positions,
        node_size=options.node_size,
        edge_thickness=options.edge_thickness,
        aspect_ratio=_camera_aspect_ratio(window),
    )

    centered_node_positions, centered_edge_positions = _center_graph_positions(graph_data, metrics.center)
    origin = np.zeros(3, dtype=float)
    _configure_camera(window, qt, origin, metrics)

    _add_light(root_entity, qt, origin, metrics.camera_distance)

    node_material = qt.QPhongMaterial(root_entity)
    node_material.setDiffuse(qt.QtGui.QColor(220, 20, 60))
    node_material.setAmbient(qt.QtGui.QColor(180, 35, 70))
    node_material.setSpecular(qt.QtGui.QColor(255, 220, 220))
    node_material.setShininess(32.0)

    for position in centered_node_positions:
        node_entity = qt.QEntity(root_entity)
        node_mesh = qt.QSphereMesh(node_entity)
        node_mesh.setRadius(1.0)
        node_mesh.setRings(12)
        node_mesh.setSlices(16)
        node_transform = qt.QTransform(node_entity)
        node_transform.setTranslation(_qvector3d_from_array(qt.QtGui, position))
        node_transform.setScale(metrics.node_radius)
        node_entity.addComponent(node_mesh)
        node_entity.addComponent(node_material)
        node_entity.addComponent(node_transform)

    if graph_data.edge_count > 0:
        edge_material = qt.QPhongMaterial(root_entity)
        edge_material.setDiffuse(qt.QtGui.QColor(34, 139, 34))
        edge_material.setAmbient(qt.QtGui.QColor(40, 160, 70))
        edge_material.setSpecular(qt.QtGui.QColor(220, 255, 220))
        edge_material.setShininess(24.0)

        y_axis = qt.QtGui.QVector3D(0.0, 1.0, 0.0)
        for edge_index in range(0, centered_edge_positions.shape[0], 2):
            start = centered_edge_positions[edge_index]
            end = centered_edge_positions[edge_index + 1]
            delta = end - start
            length = float(np.linalg.norm(delta))
            if length <= 0:
                continue

            edge_entity = qt.QEntity(root_entity)
            edge_mesh = qt.QCylinderMesh(edge_entity)
            edge_mesh.setRadius(1.0)
            edge_mesh.setLength(1.0)
            edge_mesh.setRings(8)
            edge_mesh.setSlices(12)
            edge_transform = qt.QTransform(edge_entity)
            edge_transform.setTranslation(_qvector3d_from_array(qt.QtGui, (start + end) * 0.5))

            direction = qt.QtGui.QVector3D(float(delta[0]), float(delta[1]), float(delta[2]))
            direction.normalize()
            edge_transform.setRotation(qt.QtGui.QQuaternion.rotationTo(y_axis, direction))
            edge_transform.setScale3D(qt.QtGui.QVector3D(metrics.edge_radius, length, metrics.edge_radius))

            edge_entity.addComponent(edge_mesh)
            edge_entity.addComponent(edge_material)
            edge_entity.addComponent(edge_transform)

    return root_entity


def launch_graph_viewer(
    input_path: str | Path | None = None,
    *,
    edge_thickness: float = 2.0,
    node_size: float = 6.0,
) -> int:
    """Launch an interactive Qt window that renders zero or more GraphML files in 3D."""
    if edge_thickness <= 0:
        raise GraphVisualizationError("--edge_thickness must be greater than zero.")
    if node_size <= 0:
        raise GraphVisualizationError("--node_size must be greater than zero.")

    session = GraphViewerSession()
    if input_path is not None:
        session.load_file(input_path)

    options = GraphVisualizationOptions(edge_thickness=edge_thickness, node_size=node_size)
    qt = _import_qt_modules()
    _configure_default_surface_format(qt)

    if hasattr(qt.QtCore.Qt, "ApplicationAttribute"):
        share_contexts = qt.QtCore.Qt.ApplicationAttribute.AA_ShareOpenGLContexts
    else:  # pragma: no cover - compatibility fallback
        share_contexts = qt.QtCore.Qt.AA_ShareOpenGLContexts

    app = qt.QtWidgets.QApplication.instance()
    owns_app = app is None
    if app is None:
        qt.QtCore.QCoreApplication.setAttribute(share_contexts)
        app = qt.QtWidgets.QApplication([])

    viewer = _GraphViewerWindow(qt=qt, session=session, options=options)
    viewer.show()

    if _viewer_troubleshooting_enabled():
        print(_format_runtime_diagnostics(_collect_runtime_diagnostics(qt, viewer._scene_window), phase="startup"))

        def _print_post_show_diagnostics() -> None:
            print(_format_runtime_diagnostics(_collect_runtime_diagnostics(qt, viewer._scene_window), phase="post-show"))

        qt.QtCore.QTimer.singleShot(0, _print_post_show_diagnostics)

    if owns_app:
        return int(app.exec())

    return 0
