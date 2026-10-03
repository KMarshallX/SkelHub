"""Evaluate tab: compare a predicted skeleton NIfTI with a reference using the evaluation API.

An optional shared foreground mask adds the foreground EDT-sum agreement.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from skelhub.api import evaluate_prediction_path
from skelhub.core import EvaluationResult
from skelhub.core import ForegroundEdtAgreement
from skelhub.evaluation import write_evaluation_json
from skelhub.evaluation.reporting import FOREGROUND_EDT_NOT_COMPUTED, FOREGROUND_EDT_TITLE
from skelhub.evaluation.validation import (
    HEADER_SPATIAL_UNITS, SELECTABLE_SPATIAL_UNITS, UNKNOWN_SPATIAL_UNITS, normalize_tolerances, resolve_spatial_unit,
    unit_factor_to_um,
)

from .edt_tab import NIFTI_FILTER, OUTDATED_COLOR, HelpIcon
from .services import NiftiHeaderPreview, file_identity, inspect_nifti_header


Launch = Callable[[str, Callable, Callable[[object], None]], None]

# Display labels for declarable units and for known header units; "micron" headers map onto the µm entry.
UNIT_LABELS = {"cm": "cm", "mm": "mm", "um": "µm", "nm": "nm", "meter": "metres"}
SPATIAL_UNIT_CHOICES = tuple((UNIT_LABELS[unit], unit) for unit in SELECTABLE_SPATIAL_UNITS)
TOLERANCE_UNIT_CHOICES = (("µm", "um"), ("voxels", "voxels"))
UNIT_PLACEHOLDER = "Select spatial unit…"
FROM_HEADER = "From NIfTI header."
USER_SUPPLIED = "User supplied; header unit is unknown."
UNKNOWN_UNIT_MESSAGE = "The NIfTI spatial unit is unknown. Select the unit of the stored spacing and coordinates."
UNIT_HELP = (
    "<p>A spatial-unit selection labels the existing spacing and coordinate values. "
    "It does not change the voxel spacing.</p>"
    "<p>Stored spacing 0.05, selected mm → 50 µm<br>Stored spacing 50, selected µm → 50 µm<br>"
    "Stored spacing 1, selected µm → 1 µm<br>Stored spacing 0.005, selected cm → 50 µm</p>"
    "<p>Known header units (metres, mm, µm) are used as they are and cannot be changed here. "
    "The input files are never modified.</p>"
)
FOREGROUND_TITLE = "Shared foreground mask"
FOREGROUND_OPTIONAL = "Optional. Adds the foreground EDT-sum agreement; leave empty to skip it."
FOREGROUND_HELP = (
    "<p>One binary mask (0/1) for both skeletons, on the same grid. One Euclidean distance transform of the "
    "whole mask is sampled at every prediction and reference skeleton voxel and summed, in µm. Voxels outside "
    "the mask count as zero.</p>"
    "<p>Matching sums do not show spatial or topological agreement: voxel count and clearance can compensate. "
    "Sampling, orientation and resolution change the sum; it is not a branch-length integral.</p>"
)
TOLERANCE_PLACEHOLDER = "e.g. 50, 100"
TOLERANCE_RULE = "Each tolerance is reported separately. The first is primary."
TOLERANCE_HELP = (
    "<p>Maximum distance between voxel centres for a voxel to count as matched. "
    "Separate values with commas and/or spaces; their order is kept. Zero means exact voxel-centre matching.</p>"
    "<p>Voxel tolerances need isotropic spacing; on anisotropic grids enter the tolerance in µm.</p>"
)
BETTI_HELP = (
    "<p>Counts of components, cycles and cavities agree. This does not show that the same branches are "
    "connected, and it is not a pass/fail result.</p>"
)
ENDPOINT_HELP = "<p>Voxels with exactly one 26-neighbour. Diagnostics only: matching counts do not show matching endpoints.</p>"
OUTDATED_TEXT = "Results are outdated — run evaluation again."
RUNNING_TEXT = "Evaluation running — the results below are from the previous run."
FAILED_RUN_TEXT = "Evaluation rejected or failed. Review the warning and run log."
FAILED_TEXT = "The last evaluation failed. The results shown are from an earlier run and are outdated."
FLAG_NOTE = ("(--pred-spatial-unit, --ref-spatial-unit and --foreground-spatial-unit in these warnings are the "
             "Spatial unit selections above.)")
NOT_AVAILABLE = "N/A"
PREVIEW_DELAY_MS = 400
STATUS_LABELS = {
    "ok": "Evaluated",
    "empty_prediction": "Empty prediction",
    "empty_reference": "Empty reference",
    "both_empty": "Both skeletons empty",
}
METRICS_LINK = "Metric definitions: docs/evaluation.md"
_NUMBER = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?")


def parse_tolerances(text: str) -> tuple[float, ...]:
    """Parse tolerance text: numbers separated by commas and/or whitespace, order kept.

    The evaluation backend's own rules then reject negative, nonfinite and duplicate values.
    """
    tokens = [token for token in re.split(r"[,\s]+", text.strip()) if token]
    if not tokens:
        raise ValueError("Enter at least one tolerance.")
    for token in tokens:
        if not _NUMBER.fullmatch(token):
            raise ValueError(f"'{token}' is not a number.")
    values = tuple(float(token) for token in tokens)
    normalize_tolerances(values, "um", (1.0, 1.0, 1.0))
    return values


def _nifti_stem(path: str) -> str:
    name = Path(path).name
    for suffix in (".nii.gz", ".nii"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return Path(path).stem


@dataclass(frozen=True, slots=True)
class EvaluationRequest:
    """Everything one evaluation run uses, captured when Evaluate is pressed."""

    pred_path: str
    ref_path: str
    pred_key: tuple[str, int, int]
    ref_key: tuple[str, int, int]
    pred_spatial_unit: str | None
    ref_spatial_unit: str | None
    tolerances: tuple[float, ...]
    tolerance_unit: str
    foreground_path: str | None = None
    foreground_key: tuple[str, int, int] | None = None
    foreground_spatial_unit: str | None = None


def run_evaluation(request: EvaluationRequest, progress: Callable[[int | None, str], None]) -> EvaluationResult:
    """Background-job body: call the public evaluation API with the captured settings."""
    return evaluate_prediction_path(
        request.pred_path,
        request.ref_path,
        buffer_radius=list(request.tolerances),
        buffer_radius_unit=request.tolerance_unit,
        pred_spatial_unit=request.pred_spatial_unit,
        ref_spatial_unit=request.ref_spatial_unit,
        foreground_path=request.foreground_path,
        foreground_spatial_unit=request.foreground_spatial_unit,
        log=lambda message: progress(None, f"Evaluate: {message}"),
    )


class InputSide:
    """One input file row with its spatial-unit selector and header preview.

    An ``optional`` input with an empty path is ready and is not evaluated.
    """

    def __init__(self, role: str, title: str, row: QWidget, on_change: Callable[[], None], *, optional: bool = False):
        self.role, self.title, self.row, self.optional = role, title, row, optional
        self._on_change = on_change
        self.preview: NiftiHeaderPreview | None = None
        self.unit_combo = QComboBox()
        self.unit_combo.setPlaceholderText(UNIT_PLACEHOLDER)
        for label, value in SPATIAL_UNIT_CHOICES:
            self.unit_combo.addItem(label, value)
        self.unit_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.unit_combo.setMinimumWidth(170)
        self.unit_combo.setCurrentIndex(-1)
        self.unit_combo.setEnabled(False)
        self.unit_combo.currentIndexChanged.connect(lambda _index: self._on_change())
        self.unit_help = HelpIcon(UNIT_HELP)
        self.unit_note = QLabel()
        self.unit_note.setObjectName("sectionDescription")
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setObjectName("sectionDescription")
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.setInterval(PREVIEW_DELAY_MS)
        self.timer.timeout.connect(self.inspect)
        row.changed.connect(self.path_changed)
        row.edit.editingFinished.connect(self.inspect_if_due)
        self.clear(self._empty_message())

    def _empty_message(self) -> str:
        return FOREGROUND_OPTIONAL if self.optional else "Select a .nii or .nii.gz file."

    def unit_row(self) -> QWidget:
        """Unit selector, its note and the header details on one line (details wrap when narrow)."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.unit_combo, 0, Qt.AlignTop)
        layout.addWidget(self.unit_help, 0, Qt.AlignTop)
        layout.addWidget(self.unit_note, 0, Qt.AlignVCenter)
        layout.addSpacing(6)
        layout.addWidget(self.details, 1, Qt.AlignVCenter)
        return widget

    # ----- metadata --------------------------------------------------------------
    def path(self) -> str:
        return self.row.value()

    def path_changed(self) -> None:
        """Forget the old file's metadata and unit choice at once, then re-read after a pause."""
        self.clear("Reading header…" if self.path() else self._empty_message())
        self.timer.start()
        self._on_change()

    def inspect_if_due(self) -> None:
        if self.timer.isActive():
            self.timer.stop()
            self.inspect()

    def inspect(self) -> None:
        """Read the current path's header (not its voxels) and apply it."""
        path = self.path()
        self.apply_preview(inspect_nifti_header(path) if path else None)

    def apply_preview(self, preview: NiftiHeaderPreview | None) -> None:
        """Apply a header preview, ignoring one for a path that is no longer selected."""
        if preview is not None and preview.path != self.path():
            return
        self.preview = preview
        self.unit_combo.blockSignals(True)
        self.unit_combo.setCurrentIndex(-1)
        self.unit_combo.setEnabled(False)
        self.unit_combo.setPlaceholderText(UNIT_PLACEHOLDER)
        known = self.known_header_unit()
        if known is not None:
            index = self.unit_combo.findData(known)
            self.unit_combo.setCurrentIndex(index)
            if index < 0:  # a known header unit that is not a declaration choice, such as metres
                self.unit_combo.setPlaceholderText(UNIT_LABELS.get(known, known))
        elif self.header_is_unknown():
            self.unit_combo.setEnabled(True)
        self.unit_combo.blockSignals(False)
        self.update_labels()
        self._on_change()

    def clear(self, message: str) -> None:
        self.preview = None
        self.unit_combo.blockSignals(True)
        self.unit_combo.setCurrentIndex(-1)
        self.unit_combo.setEnabled(False)
        self.unit_combo.setPlaceholderText(UNIT_PLACEHOLDER)
        self.unit_combo.blockSignals(False)
        self.unit_note.setText("")
        self.unit_note.setStyleSheet("")
        self.details.setText(message)
        self.details.setStyleSheet("")

    def is_stale_on_disk(self) -> bool:
        """True when the inspected file has since changed or disappeared."""
        return self.preview is not None and self.preview.error is None and file_identity(self.path()) != self.preview.file_key

    # ----- units -----------------------------------------------------------------
    def known_header_unit(self) -> str | None:
        if self.preview is None or self.preview.error is not None:
            return None
        return HEADER_SPATIAL_UNITS.get(self.preview.header_unit)

    def header_is_unknown(self) -> bool:
        return (self.preview is not None and self.preview.error is None
                and self.preview.header_unit in UNKNOWN_SPATIAL_UNITS)

    def selected_unit(self) -> str | None:
        return None if self.unit_combo.currentIndex() < 0 else str(self.unit_combo.currentData())

    def supplied_unit(self) -> str | None:
        """Unit to pass to the backend: only a user choice for an unknown header."""
        return self.selected_unit() if self.header_is_unknown() else None

    def problem(self) -> str | None:
        """Why this input cannot be evaluated yet, or None when it is ready."""
        if not self.path():
            return None if self.optional else f"Select the {self.title.lower()}."
        if self.preview is None:
            return f"Reading the {self.title.lower()} header…"
        if self.preview.error is not None:
            return f"{self.title}: {self.preview.error}"
        if self.header_is_unknown() and self.selected_unit() is None:
            return f"Select the {self.title.lower()} spatial unit."
        try:
            resolve_spatial_unit(self.preview.header_unit, self.supplied_unit(), label=self.title, role=self.role)
        except ValueError as exc:
            return str(exc)
        return None

    def effective_unit(self) -> str | None:
        known = self.known_header_unit()
        return known if known is not None else (self.selected_unit() if self.header_is_unknown() else None)

    def spacing_um(self) -> tuple[float, float, float] | None:
        unit = self.effective_unit()
        if unit is None or self.preview is None or self.preview.stored_spacing is None:
            return None
        factor = unit_factor_to_um(unit)
        return tuple(value * factor for value in self.preview.stored_spacing)  # type: ignore[return-value]

    def update_labels(self) -> None:
        preview = self.preview
        if preview is None:
            return
        if preview.error is not None:
            self.unit_note.setText("")
            self.details.setText(preview.error)
            self.details.setStyleSheet("color: #8a3c32;")
            return
        problem = None
        if self.known_header_unit() is not None:
            self.unit_note.setText(FROM_HEADER)
            self.unit_note.setStyleSheet("")
        elif self.header_is_unknown():
            chosen = self.selected_unit() is not None
            self.unit_note.setText(USER_SUPPLIED if chosen else "Required")
            self.unit_note.setStyleSheet("" if chosen else f"color: {OUTDATED_COLOR}; font-weight: 600;")
        else:
            self.unit_note.setText("")
            problem = self.problem()
        effective = self.effective_unit()
        spacing = self.spacing_um()
        parts = [
            "Shape " + " × ".join(str(size) for size in preview.shape),
            f"header unit: {preview.header_unit}",
            f"effective unit: {self._unit_label(effective) if effective else 'not set'}",
        ]
        if spacing is not None:
            parts.append("spacing " + " × ".join(f"{value:.6g}" for value in spacing) + " µm")
        elif preview.stored_spacing is not None:
            parts.append("stored spacing " + " × ".join(f"{value:.6g}" for value in preview.stored_spacing))
        text = " · ".join(parts)
        if problem:
            text += f"\n{problem}"
        elif self.header_is_unknown() and self.selected_unit() is None:
            text += f"\n{UNKNOWN_UNIT_MESSAGE}"
        self.details.setText(text)
        self.details.setStyleSheet("color: #8a3c32;" if problem else "")

    @staticmethod
    def _unit_label(value: str) -> str:
        return UNIT_LABELS.get(value, value)


class EvaluateTab(QWidget):
    """Inputs, tolerance settings, structured results and JSON export for skeleton evaluation."""

    def __init__(self, path_row: Callable[..., QWidget], launch: Launch, log: Callable[[str], None],
                 error: Callable[[str], None], confirm_outputs: Callable[[list[Path]], bool]):
        super().__init__()
        self._launch, self._log, self._error, self._confirm_outputs = launch, log, error, confirm_outputs
        self.result: EvaluationResult | None = None
        self.result_request: EvaluationRequest | None = None
        self._pending: EvaluationRequest | None = None
        self._superseded = False
        self._last_failed = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        page = QWidget()
        scroll.setWidget(page)
        outer.addWidget(scroll)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 10, 16, 14)
        layout.setSpacing(8)
        title = QLabel("Evaluate")
        title.setObjectName("sectionLabel")
        layout.addWidget(title)
        description = QLabel("Compare a predicted skeleton NIfTI with a reference skeleton on the same voxel grid.")
        description.setObjectName("sectionDescription")
        layout.addWidget(description)

        layout.addWidget(self._build_inputs(path_row))
        layout.addWidget(self._build_settings())
        layout.addWidget(self._build_results())
        layout.addStretch(1)
        self.refresh_controls()

    # ----- layout -----------------------------------------------------------------
    def _build_inputs(self, path_row: Callable[..., QWidget]) -> QGroupBox:
        box = QGroupBox("Inputs")
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.pred = InputSide("pred", "Prediction skeleton", path_row(file_filter=NIFTI_FILTER), self._inputs_changed)
        self.ref = InputSide("ref", "Reference skeleton", path_row(file_filter=NIFTI_FILTER), self._inputs_changed)
        self.foreground = InputSide("foreground", FOREGROUND_TITLE, path_row(file_filter=NIFTI_FILTER),
                                    self._inputs_changed, optional=True)
        self.sides = (self.pred, self.ref, self.foreground)
        for side in (self.pred, self.ref):
            form.addRow(f"{side.title} NIfTI", side.row)
            form.addRow("Spatial unit", side.unit_row())
        foreground_row = QWidget()
        row_layout = QHBoxLayout(foreground_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        row_layout.addWidget(self.foreground.row, 1)
        self.foreground_clear = QPushButton("Clear")
        self.foreground_clear.setToolTip("Remove the foreground mask; the EDT-sum agreement is then not computed.")
        self.foreground_clear.clicked.connect(self.foreground.row.edit.clear)
        row_layout.addWidget(self.foreground_clear)
        row_layout.addWidget(HelpIcon(FOREGROUND_HELP))
        form.addRow(f"{FOREGROUND_TITLE} NIfTI", foreground_row)
        form.addRow("Spatial unit", self.foreground.unit_row())
        return box

    def _build_settings(self) -> QGroupBox:
        box = QGroupBox("Evaluation settings")
        column = QVBoxLayout(box)
        column.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(QLabel("Tolerances"))
        self.tolerance_edit = QLineEdit()
        self.tolerance_edit.setPlaceholderText(TOLERANCE_PLACEHOLDER)
        self.tolerance_edit.setMinimumWidth(180)
        self.tolerance_edit.textChanged.connect(self._settings_changed)
        row.addWidget(self.tolerance_edit, 1)
        row.addSpacing(12)
        row.addWidget(QLabel("Tolerance unit"))
        self.tolerance_unit_combo = QComboBox()
        for label, value in TOLERANCE_UNIT_CHOICES:
            self.tolerance_unit_combo.addItem(label, value)
        self.tolerance_unit_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.tolerance_unit_combo.currentIndexChanged.connect(self._settings_changed)
        row.addWidget(self.tolerance_unit_combo)
        self.tolerance_help = HelpIcon(TOLERANCE_HELP)
        row.addWidget(self.tolerance_help)
        column.addLayout(row)
        self.tolerance_status = QLabel(TOLERANCE_RULE)
        self.tolerance_status.setObjectName("sectionDescription")
        self.tolerance_status.setWordWrap(True)
        column.addWidget(self.tolerance_status)
        actions = QHBoxLayout()
        self.evaluate_button = QPushButton("Evaluate")
        self.evaluate_button.clicked.connect(self.evaluate)
        actions.addWidget(self.evaluate_button)
        actions.addSpacing(6)
        self.readiness = QLabel()
        self.readiness.setObjectName("sectionDescription")
        self.readiness.setWordWrap(True)
        actions.addWidget(self.readiness, 1)
        column.addLayout(actions)
        return box

    def _build_results(self) -> QGroupBox:
        box = QGroupBox("Results")
        column = QVBoxLayout(box)
        column.setSpacing(8)
        self.outdated_label = QLabel()
        self.outdated_label.setWordWrap(True)
        self.outdated_label.setStyleSheet(f"color: {OUTDATED_COLOR}; font-weight: 600;")
        self.outdated_label.hide()
        column.addWidget(self.outdated_label)

        summary = QHBoxLayout()
        summary.setSpacing(8)
        self.status_card, self.status_value = self._card("Status")
        self.tolerance_card, self.tolerance_value = self._card("Primary tolerance")
        self.f1_card, self.f1_value = self._card("F1 at primary tolerance")
        for card in (self.status_card, self.tolerance_card, self.f1_card):
            summary.addWidget(card, 1)
        export_column = QVBoxLayout()
        export_column.addStretch(1)
        self.export_button = QPushButton("Export JSON…")
        self.export_button.clicked.connect(self.export_json)
        export_column.addWidget(self.export_button)
        summary.addLayout(export_column)
        column.addLayout(summary)
        self.run_label = QLabel("Run an evaluation to see results.")
        self.run_label.setObjectName("sectionDescription")
        self.run_label.setWordWrap(True)
        column.addWidget(self.run_label)

        self.warnings_label = QLabel()
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.warnings_label.setStyleSheet(f"color: {OUTDATED_COLOR};")
        self.warnings_label.hide()
        column.addWidget(self.warnings_label)

        self.coverage_table = self._table(["Primary", "Tolerance (µm)", "Precision", "Recall", "F1"])
        column.addWidget(self._section("Geometry coverage", self.coverage_table))
        self.counts_table = self._table([
            "Tolerance (µm)", "Matched prediction voxels", "Unmatched prediction voxels",
            "Matched reference voxels", "Unmatched reference voxels",
        ])
        column.addWidget(self._section("Supporting voxel counts", self.counts_table))
        self.distance_table = self._table(["Distance", "Value (µm)"])
        column.addWidget(self._section("Geometry displacement", self.distance_table))
        column.addWidget(self._build_foreground_results())
        self.topology_table = self._table(["Measure", "Reference", "Prediction", "Signed difference", "Absolute error"])
        self.betti_label = QLabel("Betti-count agreement: —")
        self.betti_help = HelpIcon(BETTI_HELP)
        betti_row = QHBoxLayout()
        betti_row.addWidget(self.betti_label)
        betti_row.addWidget(self.betti_help)
        betti_row.addStretch(1)
        self.euler_label = QLabel()
        self.euler_label.setObjectName("sectionDescription")
        column.addWidget(self._section("Topology", self.topology_table, betti_row, self.euler_label))
        self.endpoint_table = self._table(["Diagnostic", "Reference", "Prediction", "Signed difference", "Absolute error"])
        endpoint_note = QHBoxLayout()
        note = QLabel("Diagnostics, not a quality score.")
        note.setObjectName("sectionDescription")
        endpoint_note.addWidget(note)
        endpoint_note.addWidget(HelpIcon(ENDPOINT_HELP))
        endpoint_note.addStretch(1)
        column.addWidget(self._section("Endpoint diagnostics", self.endpoint_table, endpoint_note))
        link = QLabel(METRICS_LINK)
        link.setObjectName("sectionDescription")
        column.addWidget(link)
        return box

    def _build_foreground_results(self) -> QGroupBox:
        self.foreground_status = QLabel(FOREGROUND_EDT_NOT_COMPUTED)
        self.foreground_status.setObjectName("sectionDescription")
        self.foreground_status.setWordWrap(True)
        status_row = QHBoxLayout()
        status_row.addWidget(self.foreground_status, 1)
        self.foreground_help = HelpIcon(FOREGROUND_HELP)
        status_row.addWidget(self.foreground_help)
        self.foreground_table = self._table([
            "Skeleton", "EDT sum (µm)", "Mean EDT (µm)", "Voxels", "Outside mask", "Outside fraction",
        ])
        self.foreground_table.hide()
        self.foreground_difference = QLabel()
        self.foreground_difference.setWordWrap(True)
        self.foreground_difference.hide()
        self.foreground_notes = QLabel()
        self.foreground_notes.setWordWrap(True)
        self.foreground_notes.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.foreground_notes.setStyleSheet(f"color: {OUTDATED_COLOR};")
        self.foreground_notes.hide()
        return self._section(FOREGROUND_EDT_TITLE, status_row, self.foreground_table, self.foreground_difference,
                             self.foreground_notes)

    @staticmethod
    def _card(caption: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("metricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 6, 10, 6)
        label = QLabel(caption)
        label.setObjectName("sectionDescription")
        layout.addWidget(label)
        value = QLabel("—")
        value.setStyleSheet("font-size: 19px; font-weight: bold")
        value.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(value)
        return card, value

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().hide()
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.setFocusPolicy(Qt.NoFocus)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setMinimumSectionSize(70)
        EvaluateTab._fit_height(table)
        return table

    @staticmethod
    def _fit_height(table: QTableWidget) -> None:
        rows = max(table.rowCount(), 1)
        height = table.horizontalHeader().sizeHint().height() + rows * table.verticalHeader().defaultSectionSize()
        table.setFixedHeight(height + 2 * table.frameWidth() + 2)

    @staticmethod
    def _section(title: str, *parts) -> QGroupBox:
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.setSpacing(4)
        for part in parts:
            if isinstance(part, QWidget):
                layout.addWidget(part)
            else:
                layout.addLayout(part)
        return box

    # ----- state ------------------------------------------------------------------
    def _inputs_changed(self) -> None:
        self.refresh_controls()

    def _settings_changed(self, *_args) -> None:
        self.refresh_controls()

    def flush_previews(self) -> None:
        """Read any header whose debounce timer is still pending (used before running)."""
        for side in self.sides:
            side.inspect_if_due()

    def tolerance_values(self) -> tuple[tuple[float, ...] | None, str | None]:
        """Parsed tolerances and an error message (one of them is None)."""
        try:
            values = parse_tolerances(self.tolerance_edit.text())
        except ValueError as exc:
            return None, str(exc)
        unit = self.tolerance_unit()
        if unit == "voxels":
            for side in (self.ref, self.pred):
                spacing = side.spacing_um()
                if spacing is None:
                    continue
                try:
                    normalize_tolerances(values, unit, spacing)
                except ValueError:
                    return None, (f"The {side.title.lower()} has anisotropic spacing ("
                                  + " × ".join(f"{value:.6g}" for value in spacing)
                                  + " µm), so voxel tolerances are ambiguous. Choose µm and enter the tolerance in µm.")
        return values, None

    def tolerance_unit(self) -> str:
        return str(self.tolerance_unit_combo.currentData())

    def readiness_problem(self) -> str | None:
        for side in self.sides:
            problem = side.problem()
            if problem is not None:
                return problem
        _values, error = self.tolerance_values()
        return error

    def current_request(self) -> EvaluationRequest | None:
        """The run the current controls describe, with live file identities; None when not ready."""
        if self.readiness_problem() is not None:
            return None
        values, _error = self.tolerance_values()
        pred_key, ref_key = file_identity(self.pred.path()), file_identity(self.ref.path())
        foreground_path = self.foreground.path() or None
        foreground_key = file_identity(foreground_path) if foreground_path else None
        if pred_key is None or ref_key is None or values is None or (foreground_path and foreground_key is None):
            return None
        return EvaluationRequest(
            pred_path=self.pred.path(), ref_path=self.ref.path(), pred_key=pred_key, ref_key=ref_key,
            pred_spatial_unit=self.pred.supplied_unit(), ref_spatial_unit=self.ref.supplied_unit(),
            tolerances=values, tolerance_unit=self.tolerance_unit(),
            foreground_path=foreground_path, foreground_key=foreground_key,
            foreground_spatial_unit=self.foreground.supplied_unit() if foreground_path else None,
        )

    def result_is_current(self) -> bool:
        """A completed result exists, no run replaced it, and it matches the inputs and files on disk."""
        if self.result is None or self._superseded or self._pending is not None:
            return False
        return self.current_request() == self.result_request

    def refresh_controls(self) -> None:
        for side in self.sides:
            side.update_labels()
        self.foreground_clear.setEnabled(bool(self.foreground.row.edit.text()))
        values, error = self.tolerance_values()
        if self.tolerance_edit.text().strip() and error:
            self.tolerance_status.setText(error)
            self.tolerance_status.setStyleSheet("color: #8a3c32;")
        elif values:
            unit = "µm" if self.tolerance_unit() == "um" else "voxels"
            listed = ", ".join(f"{value:g}" for value in values)
            self.tolerance_status.setText(f"{TOLERANCE_RULE} Primary: {values[0]:g} {unit}. In order: {listed} {unit}.")
            self.tolerance_status.setStyleSheet("")
        else:
            self.tolerance_status.setText(TOLERANCE_RULE)
            self.tolerance_status.setStyleSheet("")

        problem = self.readiness_problem()
        self.evaluate_button.setEnabled(problem is None and self._pending is None)
        if problem is not None:
            self.readiness.setText(problem)
        else:
            self.readiness.setText(self._shape_note())
        self._update_freshness()

    def _shape_note(self) -> str:
        sides = [side for side in self.sides if side.path() and side.preview is not None]
        shapes = [side.preview.shape for side in sides]  # type: ignore[union-attr]
        if len(set(shapes)) <= 1:
            return "Ready to evaluate."
        listed = "; ".join(f"{side.title.lower()} {' × '.join(map(str, side.preview.shape))}"  # type: ignore[union-attr]
                           for side in sides)
        return f"Shapes differ ({listed}); evaluation will be rejected."

    def _update_freshness(self) -> None:
        current = self.result_is_current()
        self.export_button.setEnabled(current)
        if self.result is None:
            self.outdated_label.hide()
            return
        if current:
            self.outdated_label.hide()
            return
        self.outdated_label.setText(
            RUNNING_TEXT if self._pending is not None else FAILED_TEXT if self._last_failed else OUTDATED_TEXT)
        self.outdated_label.show()

    # ----- running ----------------------------------------------------------------
    def _refresh_changed_files(self) -> bool:
        """Re-read headers of files that changed on disk; True when anything was re-read."""
        changed = False
        for side in self.sides:
            if side.is_stale_on_disk():
                self._log(f"Evaluate: {side.title} changed on disk; header re-read")
                side.inspect()
                changed = True
        return changed

    def evaluate(self) -> None:
        self.flush_previews()
        if self._refresh_changed_files():
            self.refresh_controls()
        request = self.current_request()
        if request is None:
            self._error(self.readiness_problem() or "Inputs are not ready.")
            return
        self._pending = request
        self._superseded = self.result is not None
        tolerances = ", ".join(f"{value:g}" for value in request.tolerances)
        self._log(f"Evaluate: {Path(request.pred_path).name} vs {Path(request.ref_path).name}; "
                  f"tolerances {tolerances} {request.tolerance_unit}")
        if request.foreground_path:
            self._log(f"Evaluate: {FOREGROUND_TITLE.lower()} {Path(request.foreground_path).name}")
        for side, supplied in ((self.pred, request.pred_spatial_unit), (self.ref, request.ref_spatial_unit),
                               (self.foreground, request.foreground_spatial_unit)):
            if supplied is not None:
                self._log(f"Evaluate: {side.title} unit supplied as {supplied} (header unit unknown)")
        self.refresh_controls()
        self._launch("Evaluate", lambda progress: run_evaluation(request, progress), self._on_result)

    def job_finished(self) -> None:
        """Called after any background job; a pending evaluation that produced no result failed."""
        failed = self._pending is not None
        if failed:
            self._pending = None
            self._last_failed = self.result is not None
        self.refresh_controls()
        if failed:
            self.readiness.setText(FAILED_RUN_TEXT)

    def _on_result(self, value: object) -> None:
        assert isinstance(value, EvaluationResult)
        request, self._pending = self._pending, None
        if request is None:
            return
        self.result, self.result_request = value, request
        self._superseded = False
        self._last_failed = False
        self.display(value, request)
        self._log(f"Evaluate: {value.message}")
        for warning in value.warnings:
            self._log(f"Evaluate warning: {warning}")
        self.refresh_controls()

    # ----- results ----------------------------------------------------------------
    def display(self, result: EvaluationResult, request: EvaluationRequest) -> None:
        """Render a result's own values (GUI thread only); nothing is recomputed here."""
        geometry, topology = result.geometry, result.topology
        primary = geometry.primary
        self.status_value.setText(STATUS_LABELS.get(result.status, result.status))
        self.status_value.setStyleSheet(
            "font-size: 19px; font-weight: bold" + ("" if result.status == "ok" else f"; color: {OUTDATED_COLOR}"))
        self.tolerance_value.setText(self._tolerance_text(primary.tolerance_um, primary.requested_value,
                                                          primary.requested_unit))
        self.f1_value.setText(self._score(primary.f1))
        self.f1_value.setToolTip(geometry.coverage_unavailable_reason or "")
        self.run_label.setText(f"Prediction: {Path(request.pred_path).name}  ·  Reference: {Path(request.ref_path).name}"
                               f"  ·  schema {result.schema_version}")
        self.run_label.setToolTip(f"{request.pred_path}\n{request.ref_path}")
        if result.warnings:
            text = "Warnings:\n" + "\n".join(f"• {warning}" for warning in result.warnings)
            if request.pred_spatial_unit or request.ref_spatial_unit or request.foreground_spatial_unit:
                text += f"\n{FLAG_NOTE}"
            self.warnings_label.setText(text)
            self.warnings_label.show()
        else:
            self.warnings_label.hide()

        coverage_reason = geometry.coverage_unavailable_reason
        self._fill(self.coverage_table, [
            ["Primary" if match.is_primary else "",
             (f"{match.tolerance_um:g}", None),
             (self._score(match.precision), coverage_reason if match.precision is None else repr(match.precision)),
             (self._score(match.recall), coverage_reason if match.recall is None else repr(match.recall)),
             (self._score(match.f1), coverage_reason if match.f1 is None else repr(match.f1))]
            for match in geometry.tolerances
        ])
        self._fill(self.counts_table, [
            [f"{match.tolerance_um:g}"] + [
                (NOT_AVAILABLE if count is None else str(count), coverage_reason if count is None else None)
                for count in (match.matched_prediction_voxels, match.unmatched_prediction_voxels,
                              match.matched_reference_voxels, match.unmatched_reference_voxels)
            ]
            for match in geometry.tolerances
        ])
        distances = geometry.distances
        names = (("Mean, prediction → reference", "mean_pred_to_ref_um"),
                 ("Mean, reference → prediction", "mean_ref_to_pred_um"),
                 ("Symmetric mean", "symmetric_mean_um"),
                 ("Symmetric P95", "symmetric_p95_um"),
                 ("Hausdorff (maximum)", "hausdorff_um"))
        self._fill(self.distance_table, [
            [label, (NOT_AVAILABLE, geometry.distances_unavailable_reason) if distances is None else
             (f"{getattr(distances, field):.3f}", repr(getattr(distances, field)))]
            for label, field in names
        ])
        self._display_foreground(result.foreground_edt)
        rows = []
        for k, name in ((0, "Connected components, β₀"), (1, "Independent cycles, β₁"), (2, "Enclosed cavities, β₂")):
            comparison = topology.comparison(k)
            rows.append([name, str(comparison.reference), str(comparison.prediction),
                         f"{comparison.signed_difference:+d}", str(comparison.absolute_error)])
        self._fill(self.topology_table, rows)
        self.betti_label.setText(f"Betti-count agreement: {'yes' if topology.betti_count_agreement else 'no'}")
        self.euler_label.setText(f"Euler characteristic: reference {topology.reference.euler_characteristic}, "
                                 f"prediction {topology.prediction.euler_characteristic}")
        endpoints = result.endpoints
        self._fill(self.endpoint_table, [[
            "Endpoints", str(endpoints.reference), str(endpoints.prediction),
            f"{endpoints.signed_difference:+d}", str(endpoints.absolute_error),
        ]])

    def _display_foreground(self, agreement: ForegroundEdtAgreement | None) -> None:
        """Show the foreground EDT-sum agreement exactly as the result holds it."""
        computed = agreement is not None
        for widget in (self.foreground_table, self.foreground_difference):
            widget.setVisible(computed)
        if agreement is None:
            self.foreground_status.setText(FOREGROUND_EDT_NOT_COMPUTED)
            self.foreground_notes.hide()
            return
        mask = agreement.mask
        source = "from header" if mask.spatial_unit_source == "header" else "user supplied"
        self.foreground_status.setText(
            f"Mask: {Path(mask.path).name if mask.path else 'in-memory array'}  ·  "
            f"units {UNIT_LABELS.get(mask.effective_spatial_unit, mask.effective_spatial_unit)} ({source})  ·  "
            f"{mask.foreground_voxels} foreground voxels  ·  "
            f"touches image boundary: {'yes' if mask.touches_image_boundary else 'no'}")
        self.foreground_status.setToolTip(mask.path or "")
        rows = []
        for name, summary in (("Reference", agreement.reference), ("Prediction", agreement.prediction)):
            reason = summary.unavailable_reason
            rows.append([
                name,
                (f"{summary.edt_sum_um:.6g}", repr(summary.edt_sum_um)),
                (NOT_AVAILABLE, reason) if summary.mean_edt_um is None else
                (f"{summary.mean_edt_um:.3f}", repr(summary.mean_edt_um)),
                str(summary.skeleton_voxels),
                str(summary.outside_mask_voxels),
                (NOT_AVAILABLE, reason) if summary.outside_mask_fraction is None else
                (self._percent(summary.outside_mask_fraction), repr(summary.outside_mask_fraction)),
            ])
        self._fill(self.foreground_table, rows)
        if agreement.signed_relative_difference is None:
            self.foreground_difference.setText(
                f"Relative difference: {NOT_AVAILABLE} — {agreement.relative_difference_unavailable_reason}")
            self.foreground_difference.setToolTip("")
        else:
            self.foreground_difference.setText(
                "Relative difference (prediction − reference) / reference: "
                f"{self._percent(agreement.signed_relative_difference, signed=True)}  ·  "
                f"absolute {self._percent(agreement.absolute_relative_difference)}")
            self.foreground_difference.setToolTip(
                f"signed {agreement.signed_relative_difference!r}\nabsolute {agreement.absolute_relative_difference!r}")
        notes = [summary.unavailable_reason for summary in (agreement.reference, agreement.prediction)
                 if summary.unavailable_reason]
        notes += agreement.warnings
        self.foreground_notes.setText("\n".join(f"• {note}" for note in notes))
        self.foreground_notes.setVisible(bool(notes))

    @staticmethod
    def _percent(fraction: float | None, *, signed: bool = False) -> str:
        if fraction is None:
            return NOT_AVAILABLE
        return f"{100.0 * fraction:{'+' if signed else ''}.2f}%"

    @staticmethod
    def _tolerance_text(tolerance_um: float, requested: float, unit: str) -> str:
        text = f"{tolerance_um:g} µm"
        return text + (f" ({requested:g} voxels)" if unit == "voxels" else "")

    @staticmethod
    def _score(value: float | None) -> str:
        return NOT_AVAILABLE if value is None else f"{value:.4f}"

    def _fill(self, table: QTableWidget, rows: list[list]) -> None:
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column, cell in enumerate(row):
                text, tip = cell if isinstance(cell, tuple) else (cell, None)
                item = QTableWidgetItem(text)
                if tip:
                    item.setToolTip(tip)
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row_index, column, item)
        self._fit_height(table)

    # ----- export -----------------------------------------------------------------
    def export_json(self) -> None:
        """Write the canonical JSON report for the current result."""
        if self._refresh_changed_files():
            self.refresh_controls()
        if not self.result_is_current() or self.result is None or self.result_request is None:
            self._error(OUTDATED_TEXT)
            self.refresh_controls()
            return
        request = self.result_request
        default = Path(request.pred_path).with_name(f"{_nifti_stem(request.pred_path)}_evaluation.json")
        path, _selected = QFileDialog.getSaveFileName(
            self, "Export evaluation JSON", str(default), "JSON (*.json);;All files (*)",
            options=QFileDialog.DontConfirmOverwrite,
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        if not self._confirm_outputs([Path(path)]):
            return
        try:
            written = write_evaluation_json(self.result, path)
        except (OSError, ValueError) as exc:
            self._log(f"Evaluate: JSON export failed: {exc}")
            self._error(f"Could not write the evaluation JSON:\n{exc}")
            return
        self._log(f"Evaluate: JSON report written to {written}")
        self.readiness.setText(f"JSON exported to {written}")
