"""Standalone Linux Graph Tools window."""
from __future__ import annotations

from datetime import datetime
from functools import partial
import json
from pathlib import Path
import sys
from typing import Callable

from PySide6.QtCore import QElapsedTimer, QObject, QProcess, QThread, QTimer, Signal, Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from .charting import draw_histogram
from .report import export_report, report_paths
from .services import check_graph, clean_graph, crop_graph, existing_crop_outputs
from .topology import TopologyResult


class Worker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(int, str)
    done = Signal()

    def __init__(self, function: Callable[[Callable[[int | None, str], None]], object]):
        super().__init__()
        self.function = function

    def run(self) -> None:
        try:
            self.finished.emit(self.function(
                lambda percent, message: self.progress.emit(-1 if percent is None else percent, message)
            ))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.done.emit()


class PathRow(QWidget):
    changed = Signal()

    def __init__(self, *, directory: bool = False, output: bool = False):
        super().__init__()
        self.directory, self.output = directory, output
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.textChanged.connect(self.changed)
        button = QPushButton("Browse…")
        button.clicked.connect(self.browse)
        layout.addWidget(self.edit, 1)
        layout.addWidget(button)

    def browse(self) -> None:
        current = self.edit.text() or str(Path.home())
        if self.directory:
            value = QFileDialog.getExistingDirectory(self, "Select directory", current)
        elif self.output:
            value, _ = QFileDialog.getSaveFileName(self, "Select output", current, "GraphML (*.graphml);;All files (*)")
        else:
            value, _ = QFileDialog.getOpenFileName(self, "Select input", current, "GraphML and NIfTI (*.graphml *.nii *.nii.gz);;All files (*)")
        if value:
            self.edit.setText(value)

    def value(self) -> str:
        return self.edit.text().strip()


class Chart(FigureCanvasQTAgg):
    def __init__(self, title: str, xlabel: str, ylabel: str):
        self.figure = Figure(figsize=(4, 3), dpi=100)
        super().__init__(self.figure)
        self.axes = self.figure.subplots()
        self.title, self.xlabel, self.ylabel = title, xlabel, ylabel
        self.values: dict[int, int] = {}
        self.setMinimumHeight(155)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.update_values({})

    def update_values(self, values: dict[int, int]) -> None:
        self.values = dict(values)
        draw_histogram(self.axes, self.figure, self.values,
                       title=self.title, xlabel=self.xlabel, ylabel=self.ylabel)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if getattr(self, "values", None):
            draw_histogram(self.axes, self.figure, self.values,
                           title=self.title, xlabel=self.xlabel, ylabel=self.ylabel)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SkelHub — Graph Tools")
        self.resize(1180, 720)
        self.setMinimumSize(850, 560)
        self.result: TopologyResult | None = None
        self._thread: QThread | None = None
        self._worker: Worker | None = None
        self._process: QProcess | None = None
        self._process_buffer = b""
        self._process_result: TopologyResult | None = None
        self._process_error = ""
        self._process_cancelled = False
        self._process_stage = "Starting TopoStats process"
        self._last_heartbeat = -1
        self._elapsed = QElapsedTimer()
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._tick_topology_elapsed)
        self._busy = False
        self._after_job: Callable[[], None] | None = None
        self._auto_log_opened = False
        self._last_job_failed = False
        self._crop_arguments: list[str] = []
        self._settings: list[QWidget] = []
        root = QWidget()
        self.setCentralWidget(root)
        root.setObjectName("workspace")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 15, 20, 10)
        outer.setSpacing(9)
        header = QFrame()
        header.setObjectName("topHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(17, 10, 17, 10)
        brand = QLabel("SKELHUB")
        brand.setObjectName("brand")
        header_layout.addWidget(brand)
        divider = QFrame()
        divider.setObjectName("headerDivider")
        divider.setFixedSize(1, 38)
        header_layout.addWidget(divider)
        heading_block = QVBoxLayout()
        heading = QLabel("Graph Tools")
        heading.setObjectName("heading")
        heading_block.addWidget(heading)
        subtitle = QLabel("Development version — Linux only")
        subtitle.setObjectName("subtitle")
        heading_block.addWidget(subtitle)
        header_layout.addLayout(heading_block)
        header_layout.addStretch()
        # header_layout.addWidget(self._header_label("SINGLE DATASET  /  LINUX"))
        outer.addWidget(header)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        self._build_clean()
        self._build_check()
        self._build_crop()
        self._build_topology()

        progress_panel = QFrame()
        progress_panel.setObjectName("progressPanel")
        progress_layout = QVBoxLayout(progress_panel)
        progress_layout.setContentsMargins(13, 9, 13, 9)
        progress_layout.setSpacing(5)
        self.progress_label = QLabel("READY  ·  Select a tool and input files")
        self.progress_label.setObjectName("progressLabel")
        progress_layout.addWidget(self.progress_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        progress_layout.addWidget(self.progress_bar)
        self.cancel_button = QPushButton("Cancel TopoStats")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.clicked.connect(self._cancel_topology)
        self.cancel_button.hide()
        progress_layout.addWidget(self.cancel_button, alignment=Qt.AlignRight)
        outer.addWidget(progress_panel)
        self.log_toggle = QPushButton("▸ Run log")
        self.log_toggle.setCheckable(True)
        self.log_toggle.toggled.connect(self._toggle_log)
        outer.addWidget(self.log_toggle)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setObjectName("runLog")
        self.log.setMaximumHeight(116)
        self.log.setPlaceholderText("Processing details will appear here.")
        outer.addWidget(self.log)
        self.log.hide()
        self.statusBar().showMessage("Ready")
        self.setStyleSheet("""
            QMainWindow, QWidget#workspace { background: #f2f6f7; color: #172d39; }
            QFrame#topHeader { background: #172f3b; border-radius: 8px; }
            QLabel#brand { color: #e8f7f7; font-size: 17px; font-weight: 800; letter-spacing: 2px; }
            QFrame#headerDivider { background: #3a6470; border: none; }
            QLabel#heading { font-size: 21px; font-weight: 700; color: #ffffff; }
            QLabel#subtitle { color: #9fc8cb; font-size: 11px; }
            QLabel#headerMeta { color: #9fc8cb; font-size: 10px; font-weight: 700; letter-spacing: 1px; }
            QTabWidget::pane { border: 1px solid #cddde1; background: white; border-radius: 0 7px 7px 7px; }
            QTabBar::tab { min-width: 142px; padding: 10px 17px; margin-right: 5px; color: #43616c; background: #e6eff0; border: 1px solid #cddde1; border-bottom: none; border-radius: 7px 7px 0 0; font-size: 12px; font-weight: 600; }
            QTabBar::tab:hover { background: #d8ecec; color: #1b5960; }
            QTabBar::tab:selected { background: #ffffff; color: #086e73; border-top: 3px solid #21a4a5; padding-top: 8px; font-weight: 700; }
            QLabel#sectionLabel { color: #173743; font-size: 17px; font-weight: 700; }
            QLabel#sectionDescription { color: #607c87; font-size: 11px; }
            QFrame#metricCard { border: 1px solid #d5e2e6; border-radius: 8px; background: #ffffff; }
            QFrame#progressPanel { border: 1px solid #d3e2e5; border-radius: 7px; background: #eaf3f4; }
            QLabel#progressLabel { color: #244b58; font-size: 11px; font-weight: 600; }
            QProgressBar { background: #d1e4e5; border: none; border-radius: 4px; }
            QProgressBar::chunk { background: #168e91; border-radius: 4px; }
            QTextEdit#runLog { background: #112b38; color: #d5edec; border: 1px solid #264451; border-radius: 6px; padding: 6px; font-family: monospace; font-size: 11px; }
            QLineEdit, QComboBox { background: white; border: 1px solid #c4d5db; border-radius: 5px; padding: 7px; }
            QPushButton { padding: 7px 14px; border: 1px solid #b7cbd0; border-radius: 5px; background: #ffffff; color: #163643; }
            QPushButton:hover { background: #e3f2f2; border-color: #88b9bb; }
            QPushButton:disabled { color: #91a1a7; background: #ecf1f2; }
            QPushButton#cancelButton { color: #8a3c32; border-color: #d6aaa2; background: #fff8f5; }
        """)

    @staticmethod
    def _header_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("headerMeta")
        return label

    def _page(self, name: str) -> tuple[QWidget, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 14, 16, 14)
        if name != "TopoStats":
            title = QLabel(name)
            title.setObjectName("sectionLabel")
            layout.addWidget(title)
            descriptions = {
                "Clean": "Contract degree-two nodes while preserving ordered centreline paths.",
                "Check": "Validate skeleton or graph confinement against a foreground volume.",
                "Crop patches": "Extract affected components around escaping graph nodes.",
            }
            description = QLabel(descriptions[name])
            description.setObjectName("sectionDescription")
            layout.addWidget(description)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, name)
        return page, layout

    def _field(self, form: QFormLayout, label: str, *, directory: bool = False, output: bool = False, stale: bool = False) -> PathRow:
        row = PathRow(directory=directory, output=output)
        form.addRow(label, row)
        if stale:
            row.changed.connect(self._stale_topology)
        return row

    def _button(self, layout: QVBoxLayout, label: str, callback: Callable[[], None]) -> QPushButton:
        button = QPushButton(label)
        button.clicked.connect(callback)
        layout.addWidget(button, alignment=Qt.AlignLeft)
        self._settings.append(button)
        return button

    def _result_box(self, layout: QVBoxLayout) -> QTextEdit:
        box = QTextEdit()
        box.setReadOnly(True)
        box.setMinimumHeight(150)
        layout.addWidget(box, 1)
        return box

    def _build_clean(self) -> None:
        _, layout = self._page("Clean")
        form = QFormLayout()
        self.clean_input = self._field(form, "Input GraphML")
        self.clean_output = self._field(form, "Output GraphML", output=True)
        layout.addLayout(form)
        self._button(layout, "Run cleaner", self._run_clean)
        self.clean_result = self._result_box(layout)
        for row in (self.clean_input, self.clean_output):
            row.changed.connect(lambda: self.clean_result.setPlainText("Inputs changed. Run cleaner to refresh."))

    def _build_check(self) -> None:
        _, layout = self._page("Check")
        form = QFormLayout()
        self.check_foreground = self._field(form, "Foreground NIfTI")
        self.check_skeleton = self._field(form, "Skeleton NIfTI or GraphML")
        self.connectivity = QComboBox()
        self.connectivity.addItems(["26", "18", "6"])
        form.addRow("Connectivity", self.connectivity)
        layout.addLayout(form)
        self._button(layout, "Run check", self._run_check)
        self.check_result = self._result_box(layout)
        for row in (self.check_foreground, self.check_skeleton):
            row.changed.connect(lambda: self.check_result.setPlainText("Inputs changed. Run check to refresh."))
        self.connectivity.currentTextChanged.connect(lambda: self.check_result.setPlainText("Settings changed. Run check to refresh."))

    def _build_crop(self) -> None:
        _, layout = self._page("Crop patches")
        form = QFormLayout()
        self.crop_foreground = self._field(form, "Foreground NIfTI")
        self.crop_graph = self._field(form, "Primary GraphML")
        self.crop_nif_dir = self._field(form, "Foreground patch directory", directory=True)
        self.crop_graph_dir = self._field(form, "Graph patch directory", directory=True)
        self.crop_image = self._field(form, "Optional image NIfTI")
        self.crop_image_dir = self._field(form, "Image patch directory", directory=True)
        self.crop_graph2 = self._field(form, "Optional second GraphML")
        self.crop_raster = QCheckBox("Rasterize graph patches")
        form.addRow("Rasterization", self.crop_raster)
        self.crop_skel_dir = self._field(form, "Rasterized patch directory", directory=True)
        layout.addLayout(form)
        self._button(layout, "Crop patches", self._run_crop)
        self.crop_result = self._result_box(layout)
        for row in (self.crop_foreground, self.crop_graph, self.crop_nif_dir, self.crop_graph_dir,
                    self.crop_image, self.crop_image_dir, self.crop_graph2, self.crop_skel_dir):
            row.changed.connect(lambda: self.crop_result.setPlainText("Inputs changed. Crop again to refresh."))
        self.crop_raster.toggled.connect(lambda: self.crop_result.setPlainText("Settings changed. Crop again to refresh."))

    def _build_topology(self) -> None:
        _, layout = self._page("TopoStats")
        form = QFormLayout()
        self.topology_input = self._field(form, "Skeleton NIfTI or GraphML", stale=True)
        layout.addLayout(form)
        self.provenance = QLabel("Select an input to analyze. Input nodes are preserved.")
        layout.addWidget(self.provenance)
        buttons = QHBoxLayout()
        self.run_topology_button = QPushButton("Run TopoStats")
        self.run_topology_button.clicked.connect(self._run_topology)
        self.export_button = QPushButton("Export Report")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export)
        buttons.addWidget(self.run_topology_button)
        buttons.addWidget(self.export_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self._settings.append(self.run_topology_button)
        metrics = QHBoxLayout()
        self.metric_labels: dict[str, QLabel] = {}
        for name in ("Components", "Nodes", "Edges", "Independent cycles"):
            card = QFrame()
            card.setObjectName("metricCard")
            card_layout = QVBoxLayout(card)
            card_layout.addWidget(QLabel(name))
            value = QLabel("—")
            value.setStyleSheet("font-size: 23px; font-weight: bold")
            card_layout.addWidget(value)
            metrics.addWidget(card)
            self.metric_labels[name] = value
        layout.addLayout(metrics)
        charts = QVBoxLayout()
        charts.setSpacing(10)
        self.degree_chart = Chart("Node degree distribution", "Degree", "Nodes")
        self.cycle_chart = Chart("Vertices per cycle — minimum cycle basis", "Vertices", "Cycles")
        charts.addWidget(self.degree_chart)
        charts.addWidget(self.cycle_chart)
        layout.addLayout(charts, 1)

    def _toggle_log(self, visible: bool) -> None:
        self.log.setVisible(visible)
        self.log_toggle.setText("▾ Run log" if visible else "▸ Run log")

    def _stale_topology(self) -> None:
        self.result = None
        self.export_button.setEnabled(False)
        self.provenance.setText("Input changed. Run TopoStats to refresh.")
        for label in self.metric_labels.values():
            label.setText("—")
        self.degree_chart.update_values({})
        self.cycle_chart.update_values({})

    def _error(self, message: str) -> None:
        QMessageBox.warning(self, "SkelHub", message)

    def _require(self, *rows: PathRow) -> bool:
        missing = [row for row in rows if not row.value()]
        if missing:
            self._error("Select all required input and output paths.")
        return not missing

    def _confirm_outputs(self, paths: list[Path]) -> bool:
        existing = [path for path in paths if path.exists()]
        if not existing:
            return True
        preview = "\n".join(str(path) for path in existing[:6])
        if len(existing) > 6:
            preview += f"\n… and {len(existing) - 6} more"
        return QMessageBox.question(self, "Replace existing outputs?", f"These files already exist:\n{preview}\n\nReplace them?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes

    def _log(self, message: str) -> None:
        from PySide6.QtGui import QTextCursor
        for line in str(message).splitlines():
            cursor = self.log.textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.insertText(f"[{datetime.now().strftime('%H:%M:%S')}] {line}\n")
            self.log.setTextCursor(cursor)
        self.log.ensureCursorVisible()

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress_label.setText(message)
        if percent < 0:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(percent)
        self.statusBar().showMessage(message)
        self._log(message)

    def _progress_complete(self, _result: object) -> None:
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_label.setText("COMPLETE  ·  Results ready")

    def _begin_job(self, label: str) -> bool:
        if self._busy:
            return False
        self._busy = True
        self._last_job_failed = False
        for widget in self._settings:
            widget.setEnabled(False)
        self.tabs.setEnabled(False)
        self.export_button.setEnabled(False)
        self.statusBar().showMessage(f"{label} running…")
        self.progress_label.setText(f"{label.upper()}  ·  Starting")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        if not self.log_toggle.isChecked():
            self._auto_log_opened = True
            self.log_toggle.setChecked(True)
        self._log(f"{label} started")
        return True

    def _launch(
        self,
        label: str,
        function: Callable[[Callable[[int | None, str], None]], object],
        success: Callable[[object], None],
    ) -> None:
        if not self._begin_job(label):
            return
        thread = QThread(self)
        worker = Worker(function)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(success)
        worker.finished.connect(self._progress_complete)
        worker.progress.connect(self._on_progress)
        worker.failed.connect(self._failed)
        worker.done.connect(thread.quit)
        worker.done.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._job_done)
        self._thread, self._worker = thread, worker
        thread.start()

    def _failed(self, message: str) -> None:
        self._last_job_failed = True
        self._log(f"Failed: {message}")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_label.setText("FAILED  ·  Review the run log")
        self.statusBar().showMessage("Failed")
        self._error(message)

    def _job_done(self) -> None:
        self._busy = False
        self.tabs.setEnabled(True)
        for widget in self._settings:
            widget.setEnabled(True)
        self.export_button.setEnabled(self.result is not None)
        if self.statusBar().currentMessage().endswith("running…"):
            self.statusBar().showMessage("Ready")
        self._thread = self._worker = None
        if self._auto_log_opened and not self._last_job_failed:
            self.log_toggle.setChecked(False)
        self._auto_log_opened = False
        followup, self._after_job = self._after_job, None
        if followup is not None:
            followup()

    def _show_text(self, box: QTextEdit, result: object) -> None:
        box.setPlainText(str(result))
        self._log(str(result))

    def _run_clean(self) -> None:
        if not self._require(self.clean_input, self.clean_output):
            return
        source, output = self.clean_input.value(), self.clean_output.value()
        if not self._confirm_outputs([Path(output)]):
            return
        self._launch("Clean", partial(clean_graph, source, output), partial(self._show_text, self.clean_result))

    def _run_check(self) -> None:
        if not self._require(self.check_foreground, self.check_skeleton):
            return
        self._launch("Check", partial(check_graph, self.check_foreground.value(), self.check_skeleton.value(), int(self.connectivity.currentText())), partial(self._show_text, self.check_result))

    def _run_crop(self) -> None:
        if not self._require(self.crop_foreground, self.crop_graph, self.crop_nif_dir, self.crop_graph_dir):
            return
        if self.crop_image.value() and not self.crop_image_dir.value():
            self._error("Select an image patch directory for the optional image.")
            return
        if self.crop_image_dir.value() and not self.crop_image.value():
            self._error("Select an optional image NIfTI for the image patch directory.")
            return
        if self.crop_raster.isChecked() and not self.crop_skel_dir.value():
            self._error("Select a rasterized patch directory.")
            return
        args = ["--input-fore", self.crop_foreground.value(), "--input-graph", self.crop_graph.value(), "--nif-path", self.crop_nif_dir.value(), "--grapa-path", self.crop_graph_dir.value()]
        for flag, row in (("--input-img", self.crop_image), ("--img-path", self.crop_image_dir), ("--input-graph2", self.crop_graph2)):
            if row.value():
                args.extend((flag, row.value()))
        if self.crop_raster.isChecked():
            args.extend(("--rasterization", "--skel-path", self.crop_skel_dir.value()))
        self._crop_arguments = args
        self._launch("Scan crop outputs", partial(existing_crop_outputs, args), self._crop_preflight_ready)

    def _crop_preflight_ready(self, value: object) -> None:
        existing = value
        assert isinstance(existing, list)
        self._after_job = partial(self._finish_crop_preflight, existing)

    def _finish_crop_preflight(self, existing: list[Path]) -> None:
        if self._confirm_outputs(existing):
            self._launch("Crop", partial(crop_graph, self._crop_arguments), partial(self._show_text, self.crop_result))

    def _start_topology_process(self, source: str) -> None:
        if not self._begin_job("TopoStats"):
            return
        self._process_buffer = b""
        self._process_result = None
        self._process_error = ""
        self._process_cancelled = False
        self._process_stage = "Starting isolated TopoStats process"
        self._last_heartbeat = -1
        process = QProcess(self)
        self._process = process
        process.readyReadStandardOutput.connect(self._read_topology_stdout)
        process.readyReadStandardError.connect(self._read_topology_stderr)
        process.errorOccurred.connect(self._topology_process_error)
        process.finished.connect(self._topology_process_finished)
        self.cancel_button.show()
        self.cancel_button.setEnabled(True)
        self._elapsed.start()
        self._elapsed_timer.start()
        self._log(f"Isolated worker input: {source}")
        self._on_progress(-1, self._process_stage)
        process.start(sys.executable, ["-u", "-m", "skelhub.gui.topology_worker", "--input", source])

    def _read_topology_stdout(self) -> None:
        if self._process is None:
            return
        self._process_buffer += bytes(self._process.readAllStandardOutput())
        while b"\n" in self._process_buffer:
            line, self._process_buffer = self._process_buffer.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                kind = event["type"]
                if kind == "progress":
                    self._process_stage = str(event["message"])
                    percent = event.get("percent")
                    self._on_progress(-1 if percent is None else int(percent), self._process_stage)
                elif kind == "summary":
                    self._topology_partial(event["values"])
                elif kind == "result":
                    self._process_result = TopologyResult.from_report(event["values"])
                elif kind == "error":
                    self._process_error = str(event["message"])
                    self._log(f"Worker error: {self._process_error}")
            except (KeyError, TypeError, ValueError) as exc:
                self._log(f"Unrecognized TopoStats worker output: {exc}")

    def _read_topology_stderr(self) -> None:
        if self._process is None:
            return
        message = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace").strip()
        if message:
            self._log(f"Worker diagnostic: {message}")

    def _topology_partial(self, values: dict) -> None:
        for key, count in (("Components", values["components"]), ("Nodes", values["nodes"]),
                           ("Edges", values["edges"]), ("Independent cycles", values["independent_cycles"])):
            self.metric_labels[key].setText(str(count))
        degrees = {int(key): int(count) for key, count in values["degree_distribution"].items()}
        self.degree_chart.update_values(degrees)
        self.provenance.setText("Graph counts ready · Minimum cycle basis is still computing · Input nodes preserved")
        self._log("Counts and degree histogram are available while the cycle basis continues")

    def _tick_topology_elapsed(self) -> None:
        elapsed_seconds = max(0, self._elapsed.elapsed() // 1000)
        minutes, seconds = divmod(elapsed_seconds, 60)
        self.progress_label.setText(f"{self._process_stage}  ·  elapsed {minutes:02d}:{seconds:02d}")
        if elapsed_seconds >= 5 and elapsed_seconds % 5 == 0 and elapsed_seconds != self._last_heartbeat:
            self._last_heartbeat = elapsed_seconds
            self._log(f"Still working: {self._process_stage} (elapsed {minutes:02d}:{seconds:02d})")

    def _cancel_topology(self) -> None:
        if self._process is None:
            return
        self._process_cancelled = True
        self.cancel_button.setEnabled(False)
        self._log("Cancel requested; stopping the TopoStats worker")
        self._process.kill()

    def _topology_process_error(self, error: QProcess.ProcessError) -> None:
        if self._process is None or self._process_cancelled:
            return
        if error == QProcess.FailedToStart:
            self._elapsed_timer.stop()
            self.cancel_button.hide()
            process, self._process = self._process, None
            self._failed(f"Unable to start TopoStats worker: {process.errorString()}")
            process.deleteLater()
            self._job_done()
        else:
            self._log(f"Topostats worker process notice: {self._process.errorString()}")

    def _topology_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        if self._process is None:
            return
        self._elapsed_timer.stop()
        self._read_topology_stdout()
        self._read_topology_stderr()
        self.cancel_button.hide()
        process, self._process = self._process, None
        if self._process_cancelled:
            self._last_job_failed = True
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_label.setText("CANCELLED  ·  TopoStats stopped")
            self.statusBar().showMessage("TopoStats cancelled")
            self._log("TopoStats cancelled; no report is available")
        elif exit_status == QProcess.NormalExit and exit_code == 0 and self._process_result is not None:
            self._topology_ready(self._process_result)
            self._progress_complete(self._process_result)
        else:
            self._failed(self._process_error or f"TopoStats worker exited with code {exit_code}")
        process.deleteLater()
        self._job_done()

    def _run_topology(self) -> None:
        if not self._require(self.topology_input):
            return
        self._stale_topology()
        self._start_topology_process(self.topology_input.value())

    def _topology_ready(self, value: object) -> None:
        result = value
        assert isinstance(result, TopologyResult)
        self.result = result
        for key, count in (("Components", result.components), ("Nodes", result.nodes), ("Edges", result.edges), ("Independent cycles", result.independent_cycles)):
            self.metric_labels[key].setText(str(count))
        self.degree_chart.update_values(result.degree_distribution)
        self.cycle_chart.update_values(result.cycle_vertices_distribution)
        self.provenance.setText(f"Graph source: {result.graph_source}" + (" (cache hit)" if result.cache_hit else "") + " · Input nodes preserved")
        self.statusBar().showMessage("TopoStats ready")
        self._log(f"TopoStats: {result.nodes} nodes, {result.edges} edges, {result.independent_cycles} independent cycles")

    def _export(self) -> None:
        if self.result is None:
            return
        destination = QFileDialog.getExistingDirectory(self, "Select report directory", str(Path.home()))
        if not destination:
            return
        if not self._confirm_outputs(report_paths(destination)):
            return
        result = self.result
        self._launch("Export Report", lambda progress: export_report(result, destination, overwrite=True, progress=progress), self._export_ready)

    def _export_ready(self, value: object) -> None:
        paths = value
        self.statusBar().showMessage("Report exported")
        self._log("Report files:\n" + "\n".join(map(str, paths)))

    def closeEvent(self, event) -> None:
        if self._busy:
            self._error("Wait for the current operation to finish before closing.")
            event.ignore()
        else:
            event.accept()


def launch() -> int:
    """Launch the Graph Tools desktop application."""
    app = QApplication.instance() or QApplication(sys.argv)
    window = Window()
    window.show()
    return app.exec()
