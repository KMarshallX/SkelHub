"""PySide6-based GraphML viewer for 3D vessel graphs."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import importlib.util
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Sequence

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


@dataclass(slots=True)
class GraphVisualizationOptions:
    """User-configurable graph appearance."""

    edge_thickness: float = 2.0
    node_size: float = 6.0
    window_title: str = "SkelHub Graph Viewer"


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


@dataclass(slots=True)
class _QtModules:
    QtCore: Any
    QtGui: Any
    QtWidgets: Any
    QEntity: Any
    QTransform: Any
    QPointLight: Any
    QOrbitCameraController: Any
    QPhongMaterial: Any
    QSphereMesh: Any
    QCylinderMesh: Any
    Qt3DWindow: Any


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
        QOrbitCameraController = _resolve_qt_symbol(Qt3DExtras, "Qt3DExtras", "QOrbitCameraController")
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
        QEntity=QEntity,
        QTransform=QTransform,
        QPointLight=QPointLight,
        QOrbitCameraController=QOrbitCameraController,
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
    return GraphVisualizationData(
        node_positions=node_positions,
        edge_positions=edge_positions,
        node_count=graph.vcount(),
        edge_count=graph.ecount(),
        source_path=str(graph_path),
    )


def _graph_span(node_positions: np.ndarray) -> float:
    if node_positions.size == 0:
        return 1.0
    span = float(np.ptp(node_positions, axis=0).max())
    return span if span > 0 else 1.0


def _graph_center(node_positions: np.ndarray) -> np.ndarray:
    if node_positions.size == 0:
        return np.zeros(3, dtype=float)
    return np.asarray(node_positions.mean(axis=0), dtype=float)


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
) -> _SceneMetrics:
    center = _graph_center(node_positions)
    span = _graph_span(node_positions)
    bounding_radius = _graph_bounding_radius(node_positions, center)
    scene_radius = max(bounding_radius, span * 0.5, 1.0)
    camera_distance = scene_radius * 3.2
    near_plane = max(scene_radius * 0.05, 0.1)
    far_plane = max(scene_radius * 12.0, near_plane + 100.0)

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


def _qvector3d_from_array(QtGui: Any, values: Sequence[float]) -> Any:
    return QtGui.QVector3D(float(values[0]), float(values[1]), float(values[2]))


def _add_light(root_entity: Any, qt: _QtModules, center: np.ndarray, distance: float) -> None:
    light_entity = qt.QEntity(root_entity)
    point_light = qt.QPointLight(light_entity)
    point_light.setColor(qt.QtGui.QColor(255, 255, 255))
    point_light.setIntensity(1.6)

    light_transform = qt.QTransform()
    light_transform.setTranslation(
        qt.QtGui.QVector3D(
            float(center[0] + distance),
            float(center[1] + distance),
            float(center[2] + distance),
        )
    )

    light_entity.addComponent(point_light)
    light_entity.addComponent(light_transform)


def _build_scene(window: Any, graph_data: GraphVisualizationData, options: GraphVisualizationOptions, qt: _QtModules) -> Any:
    root_entity = qt.QEntity()
    frame_graph = window.defaultFrameGraph()
    frame_graph.setClearColor(qt.QtGui.QColor(255, 255, 255))

    metrics = _compute_scene_metrics(
        graph_data.node_positions,
        node_size=options.node_size,
        edge_thickness=options.edge_thickness,
    )

    camera = window.camera()
    lens = camera.lens()
    lens.setPerspectiveProjection(45.0, 16.0 / 9.0, metrics.near_plane, metrics.far_plane)

    camera.setPosition(
        qt.QtGui.QVector3D(
            float(metrics.center[0] + metrics.camera_distance),
            float(metrics.center[1] + metrics.camera_distance * 0.6),
            float(metrics.center[2] + metrics.camera_distance),
        )
    )
    camera.setViewCenter(_qvector3d_from_array(qt.QtGui, metrics.center))

    controller = qt.QOrbitCameraController(root_entity)
    controller.setCamera(camera)
    controller.setLinearSpeed(max(metrics.bounding_radius * 2.5, 12.0))
    controller.setLookSpeed(180.0)

    _add_light(root_entity, qt, metrics.center, metrics.camera_distance)

    node_material = qt.QPhongMaterial(root_entity)
    node_material.setDiffuse(qt.QtGui.QColor(220, 20, 60))
    node_material.setAmbient(qt.QtGui.QColor(180, 35, 70))
    node_material.setSpecular(qt.QtGui.QColor(255, 220, 220))
    node_material.setShininess(32.0)

    node_mesh = qt.QSphereMesh()
    node_mesh.setRadius(1.0)
    node_mesh.setRings(12)
    node_mesh.setSlices(16)

    for position in graph_data.node_positions:
        node_entity = qt.QEntity(root_entity)
        node_transform = qt.QTransform()
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

        edge_mesh = qt.QCylinderMesh()
        edge_mesh.setRadius(1.0)
        edge_mesh.setLength(1.0)
        edge_mesh.setRings(8)
        edge_mesh.setSlices(12)

        y_axis = qt.QtGui.QVector3D(0.0, 1.0, 0.0)
        for edge_index in range(0, graph_data.edge_positions.shape[0], 2):
            start = graph_data.edge_positions[edge_index]
            end = graph_data.edge_positions[edge_index + 1]
            delta = end - start
            length = float(np.linalg.norm(delta))
            if length <= 0:
                continue

            edge_entity = qt.QEntity(root_entity)
            edge_transform = qt.QTransform()
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
    input_path: str | Path,
    *,
    edge_thickness: float = 2.0,
    node_size: float = 6.0,
) -> int:
    """Launch an interactive Qt window that renders a GraphML file in 3D."""
    if edge_thickness <= 0:
        raise GraphVisualizationError("--edge_thickness must be greater than zero.")
    if node_size <= 0:
        raise GraphVisualizationError("--node_size must be greater than zero.")

    graph_data = load_graph_visualization_data(input_path)
    options = GraphVisualizationOptions(edge_thickness=edge_thickness, node_size=node_size)
    qt = _import_qt_modules()

    if hasattr(qt.QtCore.Qt, "ApplicationAttribute"):
        share_contexts = qt.QtCore.Qt.ApplicationAttribute.AA_ShareOpenGLContexts
    else:  # pragma: no cover - compatibility fallback
        share_contexts = qt.QtCore.Qt.AA_ShareOpenGLContexts

    app = qt.QtWidgets.QApplication.instance()
    owns_app = app is None
    if app is None:
        qt.QtCore.QCoreApplication.setAttribute(share_contexts)
        app = qt.QtWidgets.QApplication([])

    window = qt.Qt3DWindow()
    window.setTitle(options.window_title)
    window.resize(1200, 800)
    root_entity = _build_scene(window, graph_data, options, qt)
    window.setRootEntity(root_entity)
    window.show()

    if owns_app:
        return int(app.exec())

    return 0
