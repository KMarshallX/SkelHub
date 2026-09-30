"""EDT Heat tab: foreground distance transform sampled on a skeleton, shown in 3D."""
from __future__ import annotations

from functools import partial
import os
from pathlib import Path
from typing import Callable

import numpy as np
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QSlider, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from skelhub.postprocessing.edt import EdtHeatResult, compute_edt_heat
from skelhub.visualization.heatmap import (
    BAND_COUNT_RANGE, COLOR_PRESETS, DEFAULT_BAND_COUNT, DEFAULT_PRESET, HeatLegend, format_value,
)


NIFTI_FILTER = "NIfTI (*.nii *.nii.gz);;All files (*)"
SKELETON_FILTER = "Skeleton NIfTI or GraphML (*.nii *.nii.gz *.graphml);;All files (*)"
NODE_SLIDER_STEP = 0.5
EDGE_SLIDER_STEP = 0.1
CLICK_DRAG_TOLERANCE = 4
MAIN_AREA_MIN_HEIGHT = 300
INTERACTION_HINT = "Drag: rotate · Shift+drag: pan · Wheel or right-drag: zoom · Click: inspect a voxel or node"
Launch = Callable[[str, Callable, Callable[[object], None]], None]


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
        self._cache: tuple[tuple, EdtHeatResult] | None = None
        self._generation = 0
        self._pending: tuple[int, tuple | None] | None = None
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
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        title = QLabel("EDT Heat")
        title.setObjectName("sectionLabel")
        layout.addWidget(title)
        description = QLabel("Colour a skeleton by the foreground's Euclidean distance to background, in physical units.")
        description.setObjectName("sectionDescription")
        layout.addWidget(description)
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        self.foreground_row = path_row(file_filter=NIFTI_FILTER)
        self.skeleton_row = path_row(file_filter=SKELETON_FILTER)
        form.addRow("Foreground NIfTI", self.foreground_row)
        form.addRow("Skeleton NIfTI or GraphML", self.skeleton_row)
        layout.addLayout(form)

        actions = QHBoxLayout()
        self.calculate_button = QPushButton("Calculate")
        self.calculate_button.clicked.connect(self.calculate)
        actions.addWidget(self.calculate_button)
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
        self.details.setText("Click a voxel or node to see its EDT and position.")

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

    # ----- state ------------------------------------------------------------------
    def _current_kind(self) -> str | None:
        return self.result.kind if self.result is not None else _input_kind(self.skeleton_row.value())

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

    def invalidate(self) -> None:
        """Inputs changed: drop the result and cache so nothing stale looks current."""
        self._generation += 1
        self._cache = None
        had_result = self.result is not None
        self.result = None
        if self.scene is not None:
            self.scene.clear()
        self.legend.set_legend(None)
        self._reset_details()
        self._set_status("Inputs changed. Calculate to refresh." if had_result or self._pending else
                            "Select a foreground and a skeleton, then Calculate.")
        self.refresh_controls()

    def calculate(self) -> None:
        foreground, skeleton = self.foreground_row.value(), self.skeleton_row.value()
        if not foreground or not skeleton:
            self._error("Select both a foreground NIfTI and a skeleton NIfTI or GraphML.")
            return
        if not self.ensure_viewer():
            self._error("The 3D viewer is unavailable:\n" + str(self.viewer_error))
            return
        key = (_file_key(foreground), _file_key(skeleton))
        if None in key:
            key = None
        if key is not None and self._cache is not None and self._cache[0] == key:
            self._log("EDT Heat: inputs unchanged; reusing the cached EDT samples")
            self.display(self._cache[1])
            return
        self._pending = (self._generation, key)
        self._set_status("Calculating…")
        self._launch("EDT Heat", partial(compute_edt_heat, foreground, skeleton), self._on_result)

    def job_finished(self) -> None:
        """Called after any background job; resets state if an EDT job ended without a result."""
        if self._pending is not None:
            self._pending = None
            self._set_status("Calculation rejected or failed. Review the warning and run log.")
        self.refresh_controls()

    def _on_result(self, value: object) -> None:
        assert isinstance(value, EdtHeatResult)
        pending, self._pending = self._pending, None
        if pending is None or pending[0] != self._generation:
            self._log("EDT Heat: inputs changed during calculation; result discarded")
            return
        if pending[1] is not None:
            self._cache = (pending[1], value)
        self.display(value)

    def display(self, result: EdtHeatResult) -> None:
        """Show a result in the viewer (GUI thread only)."""
        if self.scene is None:
            return
        self.result = result
        self.scene.preset = self.preset_combo.currentText()
        self.scene.band_count = self.band_spin.value()
        self.scene.node_size = self.node_slider.value() * NODE_SLIDER_STEP
        self.scene.edge_thickness = self.edge_slider.value() * EDGE_SLIDER_STEP
        self.scene.show(result)
        self.legend.set_legend(self.scene.legend)
        self._reset_details()
        what = "skeleton voxels" if result.kind == "nifti" else "graph nodes"
        self._set_status(
            f"{result.sample_count} {what} · EDT {format_value(float(result.values.min()))}–"
            f"{format_value(float(result.values.max()))} {result.unit_label} · spatial checks passed"
        )
        self._log(f"EDT Heat: {result.sample_count} {what}; spacing {', '.join(f'{s:g}' for s in result.spacing)} {result.unit_label}")
        self._log("EDT Heat: shape/affine/containment checks passed; they cannot prove both files come from the same source")
        for warning in result.warnings:
            self._log(f"EDT Heat warning: {warning}")
        self.refresh_controls()
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
