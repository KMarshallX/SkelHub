"""EDT Heat tab: foreground distance or local EDT ratio sampled on a skeleton, shown in 3D."""
from __future__ import annotations

from functools import partial
import os
from pathlib import Path
from typing import Callable

import numpy as np
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QSlider, QSpinBox, QStyle, QToolButton, QVBoxLayout, QWidget,
)

from skelhub.evaluation.centeredness import ALPHA_RANGE, CONNECTIVITY, DEFAULT_ALPHA
from skelhub.postprocessing.edt import DISTANCE_METHOD_LABELS, METRIC_LABELS, EdtHeatResult, compute_edt_heat
from skelhub.postprocessing.surface_distance import SURFACE_PARAMETERS, SurfaceCache
from skelhub.visualization.heatmap import (
    BAND_COUNT_RANGE, COLOR_PRESETS, DEFAULT_BAND_COUNT, DEFAULT_PRESET, HeatLegend, format_value,
)


NIFTI_FILTER = "NIfTI (*.nii *.nii.gz);;All files (*)"
SKELETON_FILTER = "Skeleton NIfTI or GraphML (*.nii *.nii.gz *.graphml);;All files (*)"
NODE_SLIDER_STEP = 0.5
EDGE_SLIDER_STEP = 0.1
CLICK_DRAG_TOLERANCE = 4
MAIN_AREA_MIN_HEIGHT = 300
OUTDATED_COLOR = "#a15c00"
METHOD_HELP = (
    "<b>Voxel EDT</b>: Distance to background voxel centers, interpolated at graph nodes.<br>"
    "<b>Surface distance</b>: Shortest distance to the foreground’s unsmoothed 0.5 isosurface.<br>"
    "Surface distance currently supports GraphML skeletons only; NIfTI skeletons use Voxel EDT."
)
ALPHA_STEP = 0.1
ALPHA_DECIMALS = 2
ALPHA_HELP = (
    "<p>Controls the neighbourhood searched for the maximum EDT. "
    "At each point, search radius = α × EDT at that point, measured in physical units. "
    "Only foreground voxels in the same 26-connected component are included. "
    "Larger α searches farther, may include wider neighbouring sections of the same component, "
    f"and can take longer. Allowed range: {ALPHA_RANGE[0]:.1f}–{ALPHA_RANGE[1]:.1f}. Default: {DEFAULT_ALPHA:g}.</p>"
)
METRIC_HELP = (
    "<p><b>Distance</b>: physical distance to the foreground boundary, using the distance method.<br>"
    "<b>Local EDT ratio</b>: EDT at the point ÷ largest EDT within α × EDT in the same component "
    "(0–1; 1 = no larger EDT nearby). Uses Voxel EDT.</p>"
)
RATIO_METHOD_TIP = "Local EDT ratio uses Voxel EDT. Set Colour by to Distance to choose another method."
NIFTI_METHOD_TIP = "NIfTI skeletons use Voxel EDT."
ALPHA_DISABLED_TIP = "α applies to Local EDT ratio only."
INTERACTION_HINT = "Drag: rotate · Shift+drag: pan · Wheel or right-drag: zoom · Click: inspect a voxel or node"
Launch = Callable[[str, Callable, Callable[[object], None]], None]
# What Calculate applies: (metric, distance method, alpha or None for distances).
Config = tuple[str, str, float | None]


def config_label(config: Config) -> str:
    """Display name of a calculation config, e.g. "Voxel EDT" or "Local EDT ratio (α = 1.5)"."""
    metric, method, alpha = config
    if metric == "local_edt_ratio":
        return f"{METRIC_LABELS[metric]} (α = {alpha:g})"
    return DISTANCE_METHOD_LABELS[method]


def result_config(result: EdtHeatResult) -> Config:
    """The config a result was calculated with."""
    return (result.metric, result.distance_method, result.alpha if result.is_ratio else None)


def _input_kind(path: str) -> str | None:
    name = path.strip().lower()
    if name.endswith(".graphml"):
        return "graphml"
    if name.endswith(".nii") or name.endswith(".nii.gz"):
        return "nifti"
    return None


def _file_key(path: str) -> tuple[str, int, int] | None:
    try:
        resolved = Path(path).resolve()
        stat = resolved.stat()
    except OSError:
        return None
    return str(resolved), int(stat.st_mtime_ns), int(stat.st_size)


def import_qt_interactor():
    """Import pyvistaqt bound to PySide6, the binding this GUI uses."""
    os.environ["QT_API"] = "pyside6"
    import qtpy

    if qtpy.API_NAME != "PySide6":
        raise ImportError(f"qtpy is already bound to {qtpy.API_NAME}; the SkelHub GUI requires PySide6.")
    from pyvistaqt import QtInteractor

    return QtInteractor


def legend_labels(legend: HeatLegend, top: float, bottom: float, min_gap: float) -> list[tuple[float, str]]:
    """Value labels for a vertical legend (minimum at the bottom) that do not overlap.

    The minimum and maximum are always labelled; inner labels are dropped when
    closer than ``min_gap`` pixels to a kept one.
    """
    if legend.constant:
        return [((top + bottom) / 2.0, format_value(legend.vmin))]
    if legend.scheme == "bands":
        values = list(legend.boundaries)
    else:
        values = list(np.linspace(legend.vmin, legend.vmax, 5))
    span = legend.vmax - legend.vmin

    def y_of(value: float) -> float:
        return bottom - (value - legend.vmin) / span * (bottom - top)

    kept = [(y_of(values[0]), format_value(values[0]))]
    last = (y_of(values[-1]), format_value(values[-1]))
    for value in values[1:-1]:
        y = y_of(value)
        if abs(kept[-1][0] - y) >= min_gap and abs(y - last[0]) >= min_gap:
            kept.append((y, format_value(value)))
    kept.append(last)
    return kept


class HeatLegendWidget(QWidget):
    """Vertical colour legend with the physical unit in its title."""

    BAR_WIDTH = 18

    def __init__(self) -> None:
        super().__init__()
        self.legend: HeatLegend | None = None
        self.setFixedWidth(112)
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

    def set_legend(self, legend: HeatLegend | None) -> None:
        self.legend = legend
        self.update()

    def _geometry(self) -> tuple[QRectF, QRectF]:
        metrics = QFontMetrics(self._title_font())
        title = QRectF(6, 6, self.width() - 12, metrics.height() * 2 + 4)
        bar = QRectF(10, title.bottom() + 10, self.BAR_WIDTH, max(40.0, self.height() - title.bottom() - 22))
        return title, bar

    def _title_font(self) -> QFont:
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSizeF(max(8.0, font.pointSizeF()))
        return font

    def current_labels(self) -> list[tuple[float, str]]:
        """Labels as currently drawn; empty when no legend is set."""
        if self.legend is None:
            return []
        _title, bar = self._geometry()
        return legend_labels(self.legend, bar.top(), bar.bottom(), QFontMetrics(self.font()).height() + 2)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        title_rect, bar = self._geometry()
        painter.setPen(QColor("#607c87"))
        if self.legend is None:
            painter.drawText(self.rect().adjusted(8, 8, -8, -8), Qt.AlignCenter | Qt.TextWordWrap, "Legend appears after Calculate")
            return
        legend = self.legend
        painter.setFont(self._title_font())
        painter.setPen(QColor("#173743"))
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, legend.title)
        painter.setFont(self.font())
        colors = [QColor(*(int(channel) for channel in rgb)) for rgb in legend.colors]
        if legend.constant:
            painter.fillRect(bar, colors[0])
        elif legend.scheme == "bands":
            height = bar.height() / len(colors)
            for index, color in enumerate(colors):
                painter.fillRect(QRectF(bar.left(), bar.bottom() - (index + 1) * height, bar.width(), height), color)
        else:
            gradient = QLinearGradient(0, bar.bottom(), 0, bar.top())
            for position in np.linspace(0.0, 1.0, 17):
                gradient.setColorAt(float(position), colors[int(round(position * (len(colors) - 1)))])
            painter.fillRect(bar, gradient)
        painter.setPen(QPen(QColor("#9fb3ba"), 1))
        painter.drawRect(bar)
        painter.setPen(QColor("#244b58"))
        text_height = QFontMetrics(self.font()).height()
        for y, text in self.current_labels():
            painter.drawLine(int(bar.right()), int(y), int(bar.right() + 4), int(y))
            painter.drawText(QRectF(bar.right() + 7, y - text_height / 2, self.width() - bar.right() - 9, text_height),
                             Qt.AlignLeft | Qt.AlignVCenter, text)
        if legend.constant:
            painter.drawText(QRectF(bar.right() + 7, (bar.top() + bar.bottom()) / 2 + text_height / 2,
                                    self.width() - bar.right() - 9, text_height), Qt.AlignLeft | Qt.AlignVCenter, "all equal")


class EdtHeatTab(QWidget):
    """Inputs, embedded 3D viewer, legend, and controls for EDT heatmaps."""

    result_shown = Signal()

    def __init__(self, path_row: Callable[..., QWidget], launch: Launch, log: Callable[[str], None],
                 error: Callable[[str], None]):
        super().__init__()
        self._launch, self._log, self._error = launch, log, error
        self.result: EdtHeatResult | None = None
        self.scene = None
        self.plotter = None
        self.viewer_error: str | None = None
        self._creating_viewer = False
        self._cache: dict[tuple, EdtHeatResult] = {}
        self._surface_cache = SurfaceCache()
        self._graph_method = "voxel_edt"
        self._result_status = ""
        self._generation = 0
        self._pending: tuple[int, tuple | None, Config] | None = None
        self._press_position: tuple[int, int] | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        page_scroll = QScrollArea()
        page_scroll.setWidgetResizable(True)
        page_scroll.setFrameShape(QFrame.NoFrame)
        page = QWidget()
        page_scroll.setWidget(page)
        outer.addWidget(page_scroll)
        layout = QVBoxLayout(page)
        # Tight vertical spacing keeps the page from scrolling at 1366 x 768 with two control rows.
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(6)
        title = QLabel("EDT Heat")
        title.setObjectName("sectionLabel")
        layout.addWidget(title)
        description = QLabel("Colour a skeleton by its physical distance to the foreground boundary, or by the local EDT ratio.")
        description.setObjectName("sectionDescription")
        layout.addWidget(description)
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        self.foreground_row = path_row(file_filter=NIFTI_FILTER)
        self.skeleton_row = path_row(file_filter=SKELETON_FILTER)
        form.addRow("Foreground NIfTI", self.foreground_row)
        form.addRow("Skeleton NIfTI or GraphML", self.skeleton_row)
        layout.addLayout(form)

        # Calculation settings on one row; Calculate, status, and the panel toggle on the next.
        settings = QHBoxLayout()
        settings.setSpacing(6)
        settings.addWidget(QLabel("Colour by"))
        self.metric_combo = QComboBox()
        for metric, label in METRIC_LABELS.items():
            self.metric_combo.addItem(label, metric)
        self.metric_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.metric_combo.setToolTip(METRIC_HELP)
        self.metric_combo.currentIndexChanged.connect(self._metric_changed)
        settings.addWidget(self.metric_combo)
        settings.addSpacing(12)
        settings.addWidget(QLabel("Distance method"))
        self.method_combo = QComboBox()
        for method, label in DISTANCE_METHOD_LABELS.items():
            self.method_combo.addItem(label, method)
        self.method_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.method_combo.currentIndexChanged.connect(self._method_changed)
        settings.addWidget(self.method_combo)
        self.method_info = self._help_icon(METHOD_HELP)
        settings.addWidget(self.method_info)
        settings.addSpacing(12)
        self.alpha_label = QLabel("Radius multiplier α")
        settings.addWidget(self.alpha_label)
        self.alpha_spin = QDoubleSpinBox()
        self.alpha_spin.setRange(*ALPHA_RANGE)
        self.alpha_spin.setDecimals(ALPHA_DECIMALS)
        self.alpha_spin.setSingleStep(ALPHA_STEP)
        self.alpha_spin.setValue(DEFAULT_ALPHA)
        self.alpha_spin.setKeyboardTracking(False)
        self.alpha_spin.valueChanged.connect(self._alpha_changed)
        self.alpha_label.setBuddy(self.alpha_spin)
        settings.addWidget(self.alpha_spin)
        self.alpha_info = self._help_icon(ALPHA_HELP)
        settings.addWidget(self.alpha_info)
        settings.addStretch(1)
        layout.addLayout(settings)

        actions = QHBoxLayout()
        self.calculate_button = QPushButton("Calculate")
        self.calculate_button.clicked.connect(self.calculate)
        actions.addWidget(self.calculate_button)
        actions.addSpacing(6)
        self.status = QLabel("Select a foreground and a skeleton, then Calculate.")
        self.status.setObjectName("sectionDescription")
        # One line that may clip: a wrapping label would make the page scroll at laptop heights.
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.status.setMinimumWidth(80)
        actions.addWidget(self.status, 1)
        self.panel_toggle = QToolButton()
        self.panel_toggle.setCheckable(True)
        self.panel_toggle.setChecked(True)
        self.panel_toggle.setText("Controls ▸")
        self.panel_toggle.setToolTip("Show or hide the viewer controls")
        self.panel_toggle.toggled.connect(self._toggle_panel)
        actions.addWidget(self.panel_toggle)
        layout.addLayout(actions)

        main_area = QWidget()
        main_area.setMinimumHeight(MAIN_AREA_MIN_HEIGHT)
        main = QHBoxLayout(main_area)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(8)
        self.viewer_frame = QFrame()
        self.viewer_frame.setObjectName("metricCard")
        self.viewer_frame.setMinimumSize(240, 160)
        self.viewer_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.viewer_frame.setToolTip(INTERACTION_HINT)
        self._viewer_layout = QVBoxLayout(self.viewer_frame)
        self._viewer_layout.setContentsMargins(1, 1, 1, 1)
        self.viewer_placeholder = QLabel("The 3D viewer opens with this tab.")
        self.viewer_placeholder.setAlignment(Qt.AlignCenter)
        self.viewer_placeholder.setWordWrap(True)
        self._viewer_layout.addWidget(self.viewer_placeholder)
        main.addWidget(self.viewer_frame, 1)
        self.legend = HeatLegendWidget()
        main.addWidget(self.legend)
        self.side_panel = self._build_side_panel()
        main.addWidget(self.side_panel)
        layout.addWidget(main_area, 1)

        for row in (self.foreground_row, self.skeleton_row):
            row.changed.connect(self.invalidate)
        self.foreground_row.changed.connect(self._surface_cache.clear)
        self.refresh_controls()

    # ----- layout -----------------------------------------------------------------
    def _build_side_panel(self) -> QScrollArea:
        panel = QWidget()
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 2, 4, 0)
        column.setSpacing(6)

        colour = QGroupBox("Color")
        colour_form = QFormLayout(colour)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(list(COLOR_PRESETS))
        self.preset_combo.setCurrentText(DEFAULT_PRESET)
        self.preset_combo.currentTextChanged.connect(self._preset_changed)
        colour_form.addRow("Color preset", self.preset_combo)
        self.band_spin = QSpinBox()
        self.band_spin.setRange(*BAND_COUNT_RANGE)
        self.band_spin.setValue(DEFAULT_BAND_COUNT)
        self.band_spin.valueChanged.connect(self._bands_changed)
        colour_form.addRow("Color bands", self.band_spin)
        column.addWidget(colour)

        graph = QGroupBox("Graph appearance")
        graph_form = QFormLayout(graph)
        from skelhub.visualization.edt_heat import DEFAULT_EDGE_THICKNESS, DEFAULT_NODE_SIZE
        from skelhub.visualization._graph_viewer_impl import EDGE_THICKNESS_RANGE, NODE_SIZE_RANGE
        self.node_slider, self.node_value = self._slider(NODE_SIZE_RANGE, NODE_SLIDER_STEP, DEFAULT_NODE_SIZE, self._node_size_changed)
        graph_form.addRow("Node size", self._slider_row(self.node_slider, self.node_value))
        self.edge_slider, self.edge_value = self._slider(EDGE_THICKNESS_RANGE, EDGE_SLIDER_STEP, DEFAULT_EDGE_THICKNESS, self._edge_thickness_changed)
        graph_form.addRow("Edge thickness", self._slider_row(self.edge_slider, self.edge_value))
        column.addWidget(graph)

        view = QGroupBox("View")
        view_layout = QVBoxLayout(view)
        self.reset_button = QPushButton("Reset / Fit view")
        self.reset_button.clicked.connect(self.reset_view)
        self.reset_button.setToolTip(INTERACTION_HINT)
        view_layout.addWidget(self.reset_button)
        column.addWidget(view)

        selection = QGroupBox("Selection")
        selection_layout = QVBoxLayout(selection)
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        selection_layout.addWidget(self.details)
        column.addWidget(selection)
        column.addStretch()
        self._reset_details()

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedWidth(250)
        return scroll

    def _help_icon(self, text: str) -> QLabel:
        """A question-mark icon whose hover tooltip holds ``text``."""
        icon = QLabel()
        icon.setPixmap(self.style().standardIcon(QStyle.SP_MessageBoxQuestion).pixmap(16, 16))
        icon.setToolTip(text)
        icon.setCursor(Qt.WhatsThisCursor)
        return icon

    @staticmethod
    def _slider(bounds: tuple[float, float], step: float, default: float, callback) -> tuple[QSlider, QLabel]:
        slider = QSlider(Qt.Horizontal)
        slider.setRange(int(round(bounds[0] / step)), int(round(bounds[1] / step)))
        slider.setValue(int(round(default / step)))
        value = QLabel(f"{default:g} px")
        value.setMinimumWidth(44)
        value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        slider.valueChanged.connect(lambda raw: (value.setText(f"{raw * step:g} px"), callback(raw * step)))
        return slider, value

    @staticmethod
    def _slider_row(slider: QSlider, value: QLabel) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(slider, 1)
        row_layout.addWidget(value)
        return row

    def _set_status(self, text: str) -> None:
        self.status.setText(text)
        self.status.setToolTip(text)

    def _toggle_panel(self, visible: bool) -> None:
        self.side_panel.setVisible(visible)
        self.panel_toggle.setText("Controls ▸" if visible else "◂ Controls")

    def _reset_details(self) -> None:
        self.details.setText("Click a voxel or node to see its value and position.")

    # ----- viewer lifecycle -------------------------------------------------------
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.ensure_viewer()

    def ensure_viewer(self) -> bool:
        """Create the embedded viewer once; returns whether it is available."""
        if self.scene is not None:
            return True
        if self.viewer_error is not None or self._creating_viewer:
            return False
        # Creating the VTK widget can deliver another show event; do not re-enter.
        self._creating_viewer = True
        try:
            QtInteractor = import_qt_interactor()
            from skelhub.visualization.edt_heat import EdtHeatScene

            plotter = QtInteractor(self.viewer_frame)
            scene = EdtHeatScene(plotter)
        except Exception as exc:
            self.viewer_error = f"{type(exc).__name__}: {exc}"
            self.viewer_placeholder.setText(
                "3D viewer unavailable. Install the GUI extras (pip install -e '.[gui]').\n" + self.viewer_error
            )
            self._log(f"EDT Heat viewer unavailable: {self.viewer_error}")
            self.refresh_controls()
            return False
        finally:
            self._creating_viewer = False
        self.plotter, self.scene = plotter, scene
        self.viewer_placeholder.hide()
        self._viewer_layout.addWidget(plotter)
        plotter.iren.add_observer("LeftButtonPressEvent", self._on_press)
        plotter.iren.add_observer("LeftButtonReleaseEvent", self._on_release)
        self.refresh_controls()
        return True

    def shutdown(self) -> None:
        """Release VTK resources before the window closes."""
        if self.scene is not None:
            self.scene.close()
        plotter, self.scene, self.plotter = self.plotter, None, None
        if plotter is not None:
            plotter.close()
            # Detach from the Qt parent so the wrapper is freed now, while pyvista
            # can still finalize it, rather than at interpreter exit.
            self._viewer_layout.removeWidget(plotter)
            plotter.setParent(None)
            plotter.deleteLater()
        self._surface_cache.clear()

    # ----- state ------------------------------------------------------------------
    def _current_kind(self) -> str | None:
        return self.result.kind if self.result is not None else _input_kind(self.skeleton_row.value())

    def selected_metric(self) -> str:
        """Metric Calculate would apply: ``distance`` or ``local_edt_ratio``."""
        return str(self.metric_combo.currentData())

    def selected_alpha(self) -> float | None:
        """Alpha Calculate would apply; None when colouring by distance."""
        if self.selected_metric() != "local_edt_ratio":
            return None
        return round(float(self.alpha_spin.value()), ALPHA_DECIMALS)

    def selected_method(self) -> str:
        """Method Calculate would apply: NIfTI skeletons and Local EDT ratio always use Voxel EDT."""
        if _input_kind(self.skeleton_row.value()) == "nifti" or self.selected_metric() == "local_edt_ratio":
            return "voxel_edt"
        return str(self.method_combo.currentData())

    def selected_config(self) -> Config:
        """Everything Calculate would apply, for cache keys and outdated checks."""
        return (self.selected_metric(), self.selected_method(), self.selected_alpha())

    def _sync_method_selector(self) -> None:
        nifti = _input_kind(self.skeleton_row.value()) == "nifti"
        ratio = self.selected_metric() == "local_edt_ratio"
        locked = nifti or ratio
        self.method_combo.blockSignals(True)
        self.method_combo.setCurrentIndex(self.method_combo.findData("voxel_edt" if locked else self._graph_method))
        self.method_combo.blockSignals(False)
        self.method_combo.setEnabled(not locked)
        self.method_combo.setToolTip(RATIO_METHOD_TIP if ratio else NIFTI_METHOD_TIP if nifti else "")
        for widget in (self.alpha_label, self.alpha_spin):
            widget.setEnabled(ratio)
            widget.setToolTip("" if ratio else ALPHA_DISABLED_TIP)

    def refresh_controls(self) -> None:
        kind = self._current_kind()
        self.band_spin.setEnabled(kind == "nifti")
        self.band_spin.setToolTip("" if kind == "nifti" else "Color bands apply to NIfTI skeletons only.")
        for widget in (self.node_slider, self.edge_slider, self.node_value, self.edge_value):
            widget.setEnabled(kind == "graphml")
            widget.setToolTip("" if kind == "graphml" else "Graph appearance applies to GraphML only; NIfTI voxels keep their physical size.")
        self.reset_button.setEnabled(self.result is not None and self.scene is not None)
        viewer_ok = self.viewer_error is None
        self.calculate_button.setEnabled(viewer_ok)
        self.calculate_button.setToolTip("" if viewer_ok else "The 3D viewer could not be created.")
        self._sync_method_selector()

    def _method_changed(self, _index: int) -> None:
        """User picked a distance method: remember it for GraphML and flag a displayed result that differs."""
        self._graph_method = str(self.method_combo.currentData())
        self._show_result_status()

    def _metric_changed(self, _index: int) -> None:
        """User picked what to colour by: lock or restore the method, enable alpha, flag the displayed result."""
        self._sync_method_selector()
        self._show_result_status()

    def _alpha_changed(self, _value: float) -> None:
        self._show_result_status()

    def _show_result_status(self) -> None:
        """Describe the displayed result; flag it in amber when Calculate would apply other settings."""
        if self.result is None:
            return
        selected = self.selected_config()
        outdated = selected != result_config(self.result)
        if outdated:
            self._set_status(f"Showing {self.result.settings_label} · {config_label(selected)} not yet applied")
            self.status.setToolTip(f"The view shows {self.result.settings_label}. Calculate to apply "
                                   f"{config_label(selected)}.")
        else:
            self._set_status(self._result_status)
            if self.result.warnings:
                self.status.setToolTip(self._result_status + "\n\n" + "\n".join(self.result.warnings))
        self.status.setStyleSheet(f"color: {OUTDATED_COLOR}; font-weight: 600;" if outdated else "")

    def invalidate(self) -> None:
        """Inputs changed: drop the result and cache so nothing stale looks current."""
        self._generation += 1
        self.status.setStyleSheet("")
        self._cache.clear()
        had_result = self.result is not None
        self.result = None
        if self.scene is not None:
            self.scene.clear()
        self.legend.set_legend(None)
        self._reset_details()
        self._set_status("Inputs changed. Calculate to refresh." if had_result or self._pending else
                            "Select a foreground and a skeleton, then Calculate.")
        self.refresh_controls()

    def _cache_key(self, foreground: str, skeleton: str, config: Config) -> tuple | None:
        """Both file identities plus every setting the result depends on; alpha only for the ratio."""
        files = (_file_key(foreground), _file_key(skeleton))
        if None in files:
            return None
        metric, method, alpha = config
        return (
            *files, metric, method,
            SURFACE_PARAMETERS if method == "surface" else (),
            (alpha, CONNECTIVITY) if metric == "local_edt_ratio" else (),
        )

    def calculate(self) -> None:
        foreground, skeleton = self.foreground_row.value(), self.skeleton_row.value()
        if not foreground or not skeleton:
            self._error("Select both a foreground NIfTI and a skeleton NIfTI or GraphML.")
            return
        if not self.ensure_viewer():
            self._error("The 3D viewer is unavailable:\n" + str(self.viewer_error))
            return
        config = self.selected_config()
        metric, method, alpha = config
        label = config_label(config)
        key = self._cache_key(foreground, skeleton, config)
        if key is not None and key in self._cache:
            self._log(f"EDT Heat: inputs unchanged; reusing cached {label} samples")
            self.display(self._cache[key])
            return
        self._pending = (self._generation, key, config)
        # While the job runs, the status keeps naming what is on screen.
        self._set_status(f"Showing {self.result.settings_label} · calculating {label}…" if self.result is not None
                         else f"Calculating {label}…")
        self._log(f"EDT Heat: calculating {label}")
        self._launch(f"EDT Heat ({label})",
                     partial(compute_edt_heat, foreground, skeleton, method=method, surface_cache=self._surface_cache,
                             metric=metric, alpha=alpha),
                     self._on_result)

    def job_finished(self) -> None:
        """Called after any background job; resets state if an EDT job ended without a result."""
        if self._pending is not None:
            label = config_label(self._pending[2])
            self._pending = None
            self._set_status(f"{label} calculation rejected or failed. Review the warning and run log.")
            self.status.setStyleSheet("")
        self.refresh_controls()

    def _on_result(self, value: object) -> None:
        assert isinstance(value, EdtHeatResult)
        pending, self._pending = self._pending, None
        if pending is None or pending[0] != self._generation or result_config(value) != pending[2]:
            self._log("EDT Heat: inputs changed during calculation; result discarded")
            self._show_result_status()
            return
        if pending[1] is not None:
            self._cache[pending[1]] = value
        if pending[2] != self.selected_config():
            self._log(f"EDT Heat: settings changed during calculation; {config_label(pending[2])} cached but not shown")
            if self.result is None:
                self._set_status(f"Settings changed. Calculate to apply {config_label(self.selected_config())}.")
            self._show_result_status()
            return
        self.display(value)

    def display(self, result: EdtHeatResult) -> None:
        """Show a result in the viewer (GUI thread only).

        Recalculating the same file pair (for example with another method)
        keeps the camera and re-selects the previously selected sample.
        """
        if self.scene is None:
            return
        previous = self.scene.result
        same_pair = previous is not None and (previous.foreground_path, previous.skeleton_path, previous.kind) == (
            result.foreground_path, result.skeleton_path, result.kind)
        reselect = self.scene.selected.index if same_pair and self.scene.selected is not None else None
        self.result = result
        self.scene.preset = self.preset_combo.currentText()
        self.scene.band_count = self.band_spin.value()
        self.scene.node_size = self.node_slider.value() * NODE_SLIDER_STEP
        self.scene.edge_thickness = self.edge_slider.value() * EDGE_SLIDER_STEP
        self.scene.show(result, reset_camera=not same_pair)
        self.legend.set_legend(self.scene.legend)
        if reselect is not None and reselect < result.sample_count:
            self.details.setText(self.scene.select(reselect).describe(result.unit_label))
        else:
            self._reset_details()
        what = "skeleton voxels" if result.kind == "nifti" else "graph nodes"
        value_range = f"{format_value(float(result.values.min()))}–{format_value(float(result.values.max()))}"
        unit = result.value_unit_label
        self._result_status = (
            f"{result.sample_count} {what} · {result.settings_label} {value_range}" + (f" {unit}" if unit else "")
            + " · spatial checks passed" + (" · warning: see run log" if result.warnings else "")
        )
        self._log(f"EDT Heat: {result.settings_label} for {result.sample_count} {what}; spacing "
                  f"{', '.join(f'{s:g}' for s in result.spacing)} {result.unit_label}")
        if result.is_ratio and result.search_radii is not None:
            self._log(f"EDT Heat: local EDT ratio searched {result.connectivity}-connected foreground components; "
                      f"search radius {format_value(float(result.search_radii.min()))}–"
                      f"{format_value(float(result.search_radii.max()))} {result.unit_label}")
        self._log("EDT Heat: shape/affine/containment checks passed; they cannot prove both files come from the same source")
        for warning in result.warnings:
            self._log(f"EDT Heat warning: {warning}")
        self.refresh_controls()
        self._show_result_status()
        self.result_shown.emit()

    # ----- appearance -------------------------------------------------------------
    def _preset_changed(self, preset: str) -> None:
        if self.scene is not None:
            self.scene.set_preset(preset)
            self.legend.set_legend(self.scene.legend)

    def _bands_changed(self, count: int) -> None:
        if self.scene is not None:
            self.scene.set_band_count(count)
            self.legend.set_legend(self.scene.legend)

    def _node_size_changed(self, size: float) -> None:
        if self.scene is not None:
            self.scene.set_node_size(size)

    def _edge_thickness_changed(self, thickness: float) -> None:
        if self.scene is not None:
            self.scene.set_edge_thickness(thickness)

    def reset_view(self) -> None:
        if self.scene is not None and self.result is not None:
            self.scene.reset_view()

    # ----- picking ----------------------------------------------------------------
    def _on_press(self, *_args) -> None:
        self._press_position = tuple(self.plotter.iren.get_event_position())

    def _on_release(self, *_args) -> None:
        start, self._press_position = self._press_position, None
        if start is None or self.plotter is None:
            return
        end = tuple(self.plotter.iren.get_event_position())
        if max(abs(end[0] - start[0]), abs(end[1] - start[1])) <= CLICK_DRAG_TOLERANCE:
            self.pick_at(*end)

    def pick_at(self, x_pos: float, y_pos: float) -> None:
        """Select the voxel or node at a VTK display position and show its details."""
        if self.scene is None or self.result is None:
            return
        picked = self.scene.pick(x_pos, y_pos)
        if picked is None:
            self._reset_details()
        else:
            self.details.setText(picked.describe(self.result.unit_label))
