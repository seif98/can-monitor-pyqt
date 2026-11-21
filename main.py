"""CAN Monitor - a small PyQt6 tool to view, plot, filter and log CAN traffic.

Runs without hardware: a built-in simulator produces realistic traffic.
Start it with:  python main.py
"""
from __future__ import annotations

import sys
import time
from collections import deque

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QFileDialog, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QPushButton, QSplitter, QTableView, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from core import (CanSimulator, CsvLogger, DEFAULT_SIGNALS, Frame, FrameFilter,
                  decode_frame)

PLOT_WINDOW_S = 10.0
TICK_MS = 30
COLORS = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#008080"]


class TraceModel(QAbstractTableModel):
    """Rolling list of the most recent frames (keeps the UI fast)."""
    HEADERS = ["Time (s)", "ID", "DLC", "Data"]

    def __init__(self, max_rows: int = 1000):
        super().__init__()
        self.max_rows = max_rows
        self._rows: list[Frame] = []
        self._mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        f = self._rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return (f"{f.timestamp:.4f}", f"{f.arbitration_id:03X}", str(f.dlc), f.data_hex())[index.column()]
        if role == Qt.ItemDataRole.FontRole:
            return self._mono
        return None

    def append(self, frames: list[Frame]) -> None:
        if not frames:
            return
        frames = frames[-self.max_rows:]
        first = len(self._rows)
        self.beginInsertRows(QModelIndex(), first, first + len(frames) - 1)
        self._rows.extend(frames)
        self.endInsertRows()
        overflow = len(self._rows) - self.max_rows
        if overflow > 0:
            self.beginRemoveRows(QModelIndex(), 0, overflow - 1)
            del self._rows[:overflow]
            self.endRemoveRows()

    def clear(self) -> None:
        self.beginResetModel()
        self._rows.clear()
        self.endResetModel()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CAN Monitor")
        self.resize(1100, 750)

        self.signals = DEFAULT_SIGNALS
        self.sim = CanSimulator(seed=1)
        self.filter = FrameFilter()
        self.logger: CsvLogger | None = None

        self._elapsed = 0.0          # simulated bus time, seconds
        self._last_wall = None       # wall clock of previous tick
        self._total = 0
        self._rate_count = 0
        self._rate_t0 = time.perf_counter()
        self._row_of_id: dict[int, int] = {}
        self._count_of_id: dict[int, int] = {}
        self._last_ts_of_id: dict[int, float] = {}
        self._buffers = {s.name: (deque(maxlen=1500), deque(maxlen=1500)) for s in self.signals}
        self._curves: dict[str, pg.PlotDataItem] = {}

        self._build_ui()
        self._rebuild_curves()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.start_btn.setChecked(True)
        self._set_running(True)

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        controls = QHBoxLayout()
        self.start_btn = QPushButton("Pause")
        self.start_btn.setCheckable(True)
        self.start_btn.clicked.connect(self._set_running)
        self.record_btn = QPushButton("Record to CSV")
        self.record_btn.setCheckable(True)
        self.record_btn.clicked.connect(self._toggle_record)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter IDs (hex, comma separated), e.g. 100, 300")
        self.filter_edit.textChanged.connect(self._filter_changed)
        self.autoscroll = QCheckBox("Auto-scroll trace")
        self.autoscroll.setChecked(True)
        for w in (self.start_btn, self.record_btn, clear_btn):
            controls.addWidget(w)
        controls.addWidget(self.filter_edit, 1)
        controls.addWidget(self.autoscroll)
        layout.addLayout(controls)

        # --- plot area: signal picker + plot
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True)
        self.plot.addLegend()
        self.plot.setLabel("bottom", "Time", units="s")
        self.signal_list = QListWidget()
        self.signal_list.setMaximumWidth(220)
        for s in self.signals:
            unit = f" [{s.unit}]" if s.unit else ""
            item = QListWidgetItem(f"{s.name}{unit}")
            item.setData(Qt.ItemDataRole.UserRole, s.name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            on = s.name in ("EngineSpeed", "VehicleSpeed")
            item.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
            self.signal_list.addItem(item)
        self.signal_list.itemChanged.connect(lambda _item: self._rebuild_curves())
        top = QSplitter(Qt.Orientation.Horizontal)
        top.addWidget(self.signal_list)
        top.addWidget(self.plot)
        top.setStretchFactor(1, 1)

        # --- tabs: monitor (latest per ID) and trace (rolling log)
        self.monitor = QTableWidget(0, 6)
        self.monitor.setHorizontalHeaderLabels(["ID", "DLC", "Data", "Count", "Period (ms)", "Decoded"])
        self.monitor.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.monitor.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.monitor.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.monitor.verticalHeader().hide()

        self.trace_model = TraceModel()
        self.trace = QTableView()
        self.trace.setModel(self.trace_model)
        self.trace.verticalHeader().hide()
        self.trace.horizontalHeader().setStretchLastSection(True)
        self.trace.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        tabs = QTabWidget()
        tabs.addTab(self.monitor, "Monitor (latest per ID)")
        tabs.addTab(self.trace, "Trace (last 1000 frames)")

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(top)
        splitter.addWidget(tabs)
        splitter.setSizes([420, 280])
        layout.addWidget(splitter, 1)

        self.status = QLabel("")
        self.statusBar().addWidget(self.status)

    # ------------------------------------------------------------ controls
    def _set_running(self, running: bool):
        self.start_btn.setText("Pause" if running else "Resume")
        if running:
            self._last_wall = time.perf_counter()
            self.timer.start(TICK_MS)
        else:
            self.timer.stop()

    def _toggle_record(self, checked: bool):
        if checked:
            path, _ = QFileDialog.getSaveFileName(self, "Save CAN log", "can_log.csv", "CSV files (*.csv)")
            if not path:
                self.record_btn.setChecked(False)
                return
            try:
                self.logger = CsvLogger(path)
                self.logger.__enter__()
            except OSError as exc:
                self.logger = None
                self.record_btn.setChecked(False)
                self.statusBar().showMessage(f"Cannot open log file: {exc}", 5000)
                return
            self.record_btn.setText("Stop recording")
        else:
            self._stop_recording()

    def _stop_recording(self):
        if self.logger is not None:
            n = self.logger.count
            self.logger.__exit__(None, None, None)
            self.logger = None
            self.statusBar().showMessage(f"Saved {n} frames", 5000)
        self.record_btn.setText("Record to CSV")
        self.record_btn.setChecked(False)

    def _clear(self):
        self.trace_model.clear()
        self.monitor.setRowCount(0)
        self._row_of_id.clear()
        self._count_of_id.clear()
        self._last_ts_of_id.clear()
        for t, v in self._buffers.values():
            t.clear()
            v.clear()
        self._total = 0

    def _filter_changed(self, text: str):
        ids: set[int] = set()
        for tok in text.replace(",", " ").split():
            try:
                ids.add(int(tok, 16))
            except ValueError:
                self.filter_edit.setStyleSheet("background-color: #ffd6d6;")
                return
        self.filter_edit.setStyleSheet("")
        self.filter = FrameFilter(ids=ids)

    def _rebuild_curves(self):
        self.plot.clear()
        self._curves.clear()
        for i in range(self.signal_list.count()):
            item = self.signal_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                name = item.data(Qt.ItemDataRole.UserRole)
                color = COLORS[i % len(COLORS)]
                self._curves[name] = self.plot.plot(pen=pg.mkPen(color, width=2), name=name)

    # ----------------------------------------------------------------- tick
    def _tick(self):
        wall = time.perf_counter()
        self._elapsed += wall - self._last_wall
        self._last_wall = wall

        frames = self.sim.poll(self._elapsed)
        if not frames:
            return
        self._total += len(frames)
        self._rate_count += len(frames)

        # plots use all frames, regardless of the display filter
        for f in frames:
            for name, value in decode_frame(f, self.signals).items():
                t, v = self._buffers[name]
                t.append(f.timestamp)
                v.append(value)
        self._update_plot()

        shown = self.filter.apply(frames)
        self.trace_model.append(shown)
        if self.autoscroll.isChecked() and shown:
            self.trace.scrollToBottom()
        self._update_monitor(shown)
        if self.logger is not None:
            self.logger.write_many(shown)
        self._update_status(wall)

    def _update_plot(self):
        for name, curve in self._curves.items():
            t, v = self._buffers[name]
            if t:
                curve.setData(np.fromiter(t, float, len(t)), np.fromiter(v, float, len(v)))
        self.plot.setXRange(self._elapsed - PLOT_WINDOW_S, self._elapsed, padding=0)

    def _update_monitor(self, frames: list[Frame]):
        latest: dict[int, Frame] = {}
        for f in frames:
            self._count_of_id[f.arbitration_id] = self._count_of_id.get(f.arbitration_id, 0) + 1
            latest[f.arbitration_id] = f
        for mid, f in latest.items():
            row = self._row_of_id.get(mid)
            if row is None:
                row = self.monitor.rowCount()
                self.monitor.insertRow(row)
                self._row_of_id[mid] = row
            prev = self._last_ts_of_id.get(mid)
            period = f"{(f.timestamp - prev) * 1000:.1f}" if prev is not None else "-"
            self._last_ts_of_id[mid] = f.timestamp
            decoded = "  ".join(f"{k}={val:.1f}" for k, val in decode_frame(f, self.signals).items())
            cells = (f"{mid:03X}", str(f.dlc), f.data_hex(), str(self._count_of_id[mid]), period, decoded)
            for col, text in enumerate(cells):
                self.monitor.setItem(row, col, QTableWidgetItem(text))

    def _update_status(self, wall: float):
        dt = wall - self._rate_t0
        if dt >= 1.0:
            rate = self._rate_count / dt
            rec = f" | recording: {self.logger.count} frames" if self.logger else ""
            self.status.setText(f"Simulator | {rate:.0f} frames/s | total {self._total}{rec}")
            self._rate_count = 0
            self._rate_t0 = wall

    def closeEvent(self, event):
        self._stop_recording()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
